import os
import time
import asyncio
from typing import Dict, Optional
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from app.video import download_video
from app.whatsapp import send_message, send_video
from app.cloud import async_upload_to_cloudinary
from app.utils import setup_cookies
from config import VERIFY_TOKEN, MESSAGE_CACHE_TTL

router = APIRouter()

# Pydantic models for API documentation
class TestDownloadRequest(BaseModel):
    url: str
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            }
        }
    }

class TestDownloadResponse(BaseModel):
    local_path: Optional[str]
    file_size_mb: Optional[float]
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "local_path": "downloads/video_123.mp4",
                "file_size_mb": 15.5
            }
        }
    }

class WebhookResponse(BaseModel):
    status: str
    message: Optional[str] = None

# Message cache to prevent duplicate processing
message_cache = {}

# Create cookies files at startup
youtube_cookies_path, facebook_cookies_path = setup_cookies()

async def handle_message_update(value):
    try:
        messages = value.get("messages", [])
        for message in messages:
            if message.get("type") == "text":
                from_number = message["from"]
                message_text = message["text"]["body"]
                if "http" in message_text.lower():
                    url = message_text.strip()
                    print(f"\nReceived URL: {url}")
                    # First validate URL
                    is_valid = (
                        url.startswith('https://www.youtube.com') or 
                        url.startswith('https://youtube.com') or 
                        url.startswith('https://youtu.be') or
                        url.startswith('https://www.facebook.com') or 
                        url.startswith('https://facebook.com') or
                        url.startswith('https://fb.watch') or
                        'facebook.com/share' in url
                    )
                    if not is_valid:
                        print(f"Invalid URL format: {url}")
                        send_message(from_number, "❌ Please send a valid YouTube or Facebook video URL")
                        return
                    send_message(from_number, "📥 Downloading video...")
                    try:
                        local_path, file_size = await download_video(url, youtube_cookies_path, facebook_cookies_path)
                        if not local_path or not os.path.exists(local_path):
                            print(f"Failed to download video from URL: {url}")
                            # Check if it's a Facebook checkpoint issue
                            if "checkpoint" in url.lower() or "facebook.com/checkpoint" in url.lower():
                                send_message(from_number, "❌ Facebook security checkpoint detected. This video requires authentication.\n\nPlease try:\n• Making sure the video is public\n• Using a direct video link instead of a share link\n• Checking if the video is still available")
                            else:
                                send_message(from_number, "❌ Could not download video. For Facebook videos, please make sure:\n\n1. The video is public\n2. You're sharing the direct video URL\n3. The video hasn't been deleted")
                            return
                        print(f"Downloaded file: {local_path} ({file_size:.2f} MB)")
                        cloudinary_url = None
                        video_sent_to_chat = False
                        
                        if file_size < 16:
                            print(f"Video is {file_size:.2f} MB - attempting to send directly to chat...")
                            # Upload to Cloudinary in parallel
                            upload_task = asyncio.create_task(async_upload_to_cloudinary(local_path))
                            try:
                                await send_video(from_number, local_path)
                                video_sent_to_chat = True
                                print(f"✅ Video sent successfully to chat!")
                                send_message(from_number, "🎥 Here's your video! Uploading to Cloudinary for a shareable link...")
                            except Exception as e:
                                print(f"❌ Error sending video directly: {str(e)}")
                                send_message(from_number, f"⚠️ Could not send video directly ({file_size:.2f} MB). Uploading to Cloudinary...")
                            
                            # Wait for Cloudinary upload to finish
                            try:
                                cloudinary_url, _ = await upload_task
                                print(f"Cloudinary upload complete: {cloudinary_url}")
                            except Exception as e:
                                print(f"Cloudinary upload failed: {str(e)}")
                                cloudinary_url = None
                        else:
                            print(f"Video is {file_size:.2f} MB - too large for direct chat, uploading to Cloudinary only...")
                            # Only upload to Cloudinary
                            try:
                                cloudinary_url, _ = await async_upload_to_cloudinary(local_path)
                                print(f"Cloudinary upload complete: {cloudinary_url}")
                                # Delete local file after upload
                                os.remove(local_path)
                            except Exception as e:
                                print(f"Cloudinary upload failed: {str(e)}")
                                cloudinary_url = None
                        
                        # Always send Cloudinary link if available
                        if cloudinary_url:
                            if video_sent_to_chat:
                                message = f"☁️ Cloudinary Link ({file_size:.2f} MB):\n{cloudinary_url}"
                            else:
                                message = f"☁️ Cloudinary Link ({file_size:.2f} MB):\n{cloudinary_url}\n\nNote: Video was too large to send directly in chat."
                            send_message(from_number, message)
                        else:
                            if video_sent_to_chat:
                                send_message(from_number, "✅ Video sent to chat! (Cloudinary upload failed)")
                            else:
                                send_message(from_number, "❌ Error: Could not upload to Cloudinary.")
                        return
                    except Exception as e:
                        print(f"Error downloading video: {str(e)}")
                        error_msg = str(e).lower()
                        if "checkpoint" in error_msg or "unsupported url" in error_msg:
                            send_message(from_number, "❌ Facebook security checkpoint detected. This video requires authentication.\n\nPlease try:\n• Making sure the video is public\n• Using a direct video link instead of a share link\n• Checking if the video is still available")
                        else:
                            send_message(from_number, "❌ Error downloading video. Please check if the video is accessible.")
                        return
                else:
                    help_message = """👋 Welcome to WA Video Downloader!
                    
Just send me a Facebook or YouTube video URL, and I'll download it for you.

Supported platforms:
• Facebook
• YouTube

Note: Videos under 16MB will be sent directly in chat. For all videos, you'll get a Cloudinary link."""
                    send_message(from_number, help_message)
    except Exception as e:
        print(f"Error in handle_message_update: {str(e)}")
        print(f"Full error details: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

@router.get("/", 
    response_model=Dict[str, str],
    summary="Health Check",
    description="Simple health check endpoint to verify the API is running.",
    tags=["Health"])
async def root():
    """
    Health check endpoint that returns a simple message indicating the API is running.
    
    Returns:
        dict: A simple message indicating the service status
    """
    return {"message": "WhatsApp Webhook is running!"}

@router.get("/privacy",
    summary="Privacy Policy",
    description="""
    Serves the Privacy Policy HTML page.
    
    This endpoint provides access to the service's privacy policy, which explains
    how user data is collected, used, and protected when using the WhatsApp Video Downloader.
    """,
    tags=["Legal"],
    responses={
        200: {
            "description": "Privacy Policy HTML page",
            "content": {
                "text/html": {
                    "example": "<!DOCTYPE html><html>...</html>"
                }
            }
        }
    })
async def privacy_policy():
    """
    Serve the Privacy Policy HTML page.
    
    Returns the privacy policy document that explains how user data is handled,
    including information collection, usage, retention, and security measures.
    
    Returns:
        HTMLResponse: The privacy policy HTML page
    """
    try:
        with open("legal/privacy.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Privacy Policy not found")

@router.get("/terms",
    summary="Terms and Conditions",
    description="""
    Serves the Terms and Conditions HTML page.
    
    This endpoint provides access to the service's terms and conditions, which outline
    the rules, responsibilities, and limitations of using the WhatsApp Video Downloader.
    """,
    tags=["Legal"],
    responses={
        200: {
            "description": "Terms and Conditions HTML page",
            "content": {
                "text/html": {
                    "example": "<!DOCTYPE html><html>...</html>"
                }
            }
        }
    })
async def terms_of_service():
    """
    Serve the Terms and Conditions HTML page.
    
    Returns the terms and conditions document that outlines user responsibilities,
    service limitations, and legal disclaimers for using the WhatsApp Video Downloader.
    
    Returns:
        HTMLResponse: The terms and conditions HTML page
    """
    try:
        with open("legal/terms.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Terms and Conditions not found")

@router.get("/webhook",
    summary="WhatsApp Webhook Verification",
    description="""
    Handles webhook verification from WhatsApp Business API.
    
    This endpoint is called by WhatsApp during the webhook setup process to verify
    that your server can receive webhooks. It validates the verification token and
    returns the challenge string if valid.
    """,
    tags=["WhatsApp Webhook"],
    responses={
        200: {
            "description": "Webhook verified successfully",
            "content": {
                "text/plain": {
                    "example": "challenge_string_here"
                }
            }
        },
        403: {
            "description": "Invalid verification token"
        }
    })
async def verify_webhook(request: Request):
    """
    Handle webhook verification from WhatsApp Business API.
    
    WhatsApp calls this endpoint during webhook setup to verify your server.
    It checks the verification token and returns the challenge string if valid.
    
    Args:
        request: FastAPI request object containing query parameters
        
    Returns:
        Response: Challenge string for successful verification or 403 for invalid token
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return Response(content=challenge, media_type="text/plain")
        else:
            return Response(status_code=403)

@router.post("/webhook",
    response_model=WebhookResponse,
    summary="Receive WhatsApp Messages",
    description="""
    Receives incoming webhooks from WhatsApp Business API containing messages.
    
    This endpoint processes incoming WhatsApp messages, validates URLs,
    downloads videos, and sends responses back to users. It includes duplicate
    message detection and comprehensive error handling.
    """,
    tags=["WhatsApp Webhook"],
    responses={
        200: {
            "description": "Webhook processed successfully",
            "model": WebhookResponse
        },
        400: {
            "description": "Invalid webhook payload"
        }
    })
async def receive_webhook(request: Request):
    """
    Handle incoming webhooks from WhatsApp Business API.
    
    Processes incoming messages, validates URLs, downloads videos from YouTube/Facebook,
    and sends responses back to users. Includes duplicate message detection and
    comprehensive error handling.
    
    Args:
        request: FastAPI request object containing the webhook payload
        
    Returns:
        WebhookResponse: Status of webhook processing
    """
    try:
        body = await request.json()
        print("Received webhook payload:", body)
        
        if body.get("object") == "whatsapp_business_account":
            entry = body.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            
            # Get the value object
            value = changes.get("value", {})
            
            # Check if this is a status update
            if "statuses" in value:
                print("Received status update")
                return WebhookResponse(status="ok")
                
            # Check if this is a message
            if "messages" in value:
                print("Received new message")
                # Check for duplicate messages
                message = value.get("messages", [{}])[0]
                message_id = message.get("id")
                
                if message_id:
                    # Check if we've seen this message recently
                    if message_id in message_cache:
                        last_processed = message_cache[message_id]
                        if time.time() - last_processed < MESSAGE_CACHE_TTL:
                            print(f"Duplicate message detected (ID: {message_id}). Skipping.")
                            return WebhookResponse(status="ok")
                    
                    # Update cache with current timestamp
                    message_cache[message_id] = time.time()
                    
                    # Clean old entries from cache
                    current_time = time.time()
                    message_cache.update({k: v for k, v in message_cache.items() 
                                       if current_time - v < MESSAGE_CACHE_TTL})
                
                await handle_message_update(value)
        
        return WebhookResponse(status="ok")
    except Exception as e:
        print(f"Error in webhook: {str(e)}")
        print(f"Full error details: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return WebhookResponse(status="error", message=str(e))

# Only enable test endpoint in development
if os.getenv("DEV_MODE", "").lower() in ("true", "1", "yes"):
    @router.post("/test-download",
        response_model=TestDownloadResponse,
        summary="Test Video Download",
        description="""
        Development endpoint for testing video downloads without WhatsApp integration.
        
        This endpoint allows you to test the video download functionality by providing
        a URL directly. It downloads the video and returns the local path and file size.
        Only available when DEV_MODE environment variable is set to true.
        """,
        tags=["Development"],
        responses={
            200: {
                "description": "Video downloaded successfully",
                "model": TestDownloadResponse
            },
            400: {
                "description": "No URL provided or invalid URL"
            },
            500: {
                "description": "Download failed"
            }
        })
    async def test_download(request: TestDownloadRequest):
        """
        Test video download functionality without WhatsApp integration.
        
        Downloads a video from the provided URL and returns the local path and file size.
        This endpoint is only available in development mode.
        
        Args:
            request: TestDownloadRequest containing the video URL
            
        Returns:
            TestDownloadResponse: Local path and file size of downloaded video
            
        Raises:
            HTTPException: If no URL provided or download fails
        """
        if not request.url:
            raise HTTPException(status_code=400, detail="No URL provided")
        
        try:
            local_path, file_size = await download_video(request.url, youtube_cookies_path, facebook_cookies_path)
            return TestDownloadResponse(
                local_path=local_path,
                file_size_mb=file_size
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}") 