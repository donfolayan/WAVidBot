from fastapi import FastAPI, Request, Response
import os
import json
import requests
from dotenv import load_dotenv
import yt_dlp
from typing import Optional, Callable
import asyncio
import time
from functools import wraps
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from urllib.parse import quote
from datetime import datetime, timedelta
import re
import http.cookiejar

# Load environment variables
load_dotenv()

# Configuration
WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN', '').strip()
if not WHATSAPP_TOKEN:
    raise ValueError("WHATSAPP_TOKEN environment variable is required")

# Function to create cookies files from environment variables
def setup_cookies():
    """Create cookies files from environment variables at runtime"""
    youtube_cookies = os.getenv('YOUTUBE_COOKIES_CONTENT')
    facebook_cookies = os.getenv('FACEBOOK_COOKIES_CONTENT')
    
    youtube_path = None
    facebook_path = None
    
    if youtube_cookies:
        try:
            with open('youtube_cookies.txt', 'w') as f:
                f.write(youtube_cookies)
            youtube_path = 'youtube_cookies.txt'
            print("YouTube cookies file created successfully")
        except Exception as e:
            print(f"Error creating YouTube cookies file: {e}")
    
    if facebook_cookies:
        try:
            with open('facebook_cookies.txt', 'w') as f:
                f.write(facebook_cookies)
            facebook_path = 'facebook_cookies.txt'
            print("Facebook cookies file created successfully")
        except Exception as e:
            print(f"Error creating Facebook cookies file: {e}")
    
    return youtube_path, facebook_path

# Create cookies files at startup
YOUTUBE_COOKIES_PATH, FACEBOOK_COOKIES_PATH = setup_cookies()

print("\nDEBUG: Token loaded:", WHATSAPP_TOKEN[:20] + "..." + WHATSAPP_TOKEN[-20:])
print(f"DEBUG: Full token length: {len(WHATSAPP_TOKEN)}")
print(f"DEBUG: YouTube cookies path: {YOUTUBE_COOKIES_PATH}")
print(f"DEBUG: Facebook cookies path: {FACEBOOK_COOKIES_PATH}")

app = FastAPI()

# Other configuration
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN', 'wa_downloader_test_token')
WHATSAPP_API_URL = "https://graph.facebook.com/v16.0"
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
FILE_RETENTION_HOURS = 24 
FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')

# Message deduplication
message_cache = {}
MESSAGE_CACHE_TTL = 60  # seconds

# Validate required environment variables
if not PHONE_NUMBER_ID:
    raise ValueError("WHATSAPP_PHONE_NUMBER_ID environment variable is required")

def with_retries(max_retries: int = MAX_RETRIES, delay: int = RETRY_DELAY):
    """Decorator to add retry logic to functions"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        print(f"Retry attempt {attempt + 1} of {max_retries}")
                    return await func(*args, **kwargs)
                except requests.exceptions.HTTPError as e:
                    last_exception = e
                    if e.response.status_code == 401:  # Don't retry auth errors
                        print("Authentication error - not retrying")
                        raise
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay)
                    continue
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay)
                    continue
            print(f"All {max_retries} attempts failed: {str(last_exception)}")
            raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        print(f"Retry attempt {attempt + 1} of {max_retries}")
                    return func(*args, **kwargs)
                except requests.exceptions.HTTPError as e:
                    last_exception = e
                    if e.response.status_code == 401:  # Don't retry auth errors
                        print("Authentication error - not retrying")
                        raise
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                    continue
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                    continue
            print(f"All {max_retries} attempts failed: {str(last_exception)}")
            raise last_exception

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing special characters and emojis"""
    # Remove emojis and special characters
    filename = re.sub(r'[^\w\s-]', '', filename)
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    # Trim length to avoid too long filenames
    if len(filename) > 50:
        filename = filename[:47] + "..."
    # Add a timestamp to prevent conflicts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename}_{timestamp}"
    return filename.strip()

def resolve_facebook_share(url, cookies_path=None):
    """Resolve a Facebook share URL to the final destination using browser headers and cookies."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.70 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    cookies = None
    if cookies_path and os.path.exists(cookies_path):
        cj = http.cookiejar.MozillaCookieJar()
        try:
            cj.load(cookies_path, ignore_discard=True, ignore_expires=True)
            cookies = {c.name: c.value for c in cj}
        except Exception as e:
            print(f"Warning: Could not load cookies from {cookies_path}: {e}")
    try:
        response = requests.get(url, headers=headers, cookies=cookies, allow_redirects=True, timeout=10)
        # Check for login or bot challenge in response
        if 'login' in response.url or 'checkpoint' in response.url or 'robot' in response.text.lower():
            print(f"Warning: Facebook may be showing a login or bot challenge page: {response.url}")
        return response.url
    except Exception as e:
        print(f"Error resolving Facebook share URL: {str(e)}")
        return url

@with_retries()
async def download_video(url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Download video using yt-dlp with retry logic. Returns (small_path, medium_path, original_path)"""
    print(f"Starting download for URL: {url}")
    
    # Add a delay before every download to avoid rapid requests
    DOWNLOAD_DELAY_SECONDS = 2  # You can adjust this value as needed
    print(f"Delaying {DOWNLOAD_DELAY_SECONDS} seconds before download to avoid rapid requests...")
    await asyncio.sleep(DOWNLOAD_DELAY_SECONDS)
    
    # --- Select cookies file based on URL ---
    cookies_path = None
    if 'youtube.com' in url or 'youtu.be' in url:
        cookies_path = YOUTUBE_COOKIES_PATH
        if cookies_path:
            print(f"Using YouTube cookies: {cookies_path}")
    elif 'facebook.com' in url:
        cookies_path = FACEBOOK_COOKIES_PATH
        if cookies_path:
            print(f"Using Facebook cookies: {cookies_path}")

    # Handle Facebook share URLs
    if 'facebook.com/share' in url:
        print("Detected Facebook share URL - attempting to resolve...")
        url = resolve_facebook_share(url, cookies_path)
        print(f"Resolved share URL to: {url}")

    # First download the original version
    original_opts = {
        'format': 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
        'outtmpl': 'downloads/original_%(title)s.%(ext)s',
        'quiet': False,
        'no_warnings': False,
        'merge_output_format': 'mp4',
        'verbose': True,  # Add verbose output for debugging
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.70 Safari/537.36',
    }
    # --- Add cookies file to yt-dlp options if available ---
    if cookies_path:
        original_opts['cookiefile'] = cookies_path
    
    original_path = None
    medium_path = None
    small_path = None
    
    try:
        # Download original version first
        with yt_dlp.YoutubeDL(original_opts) as ydl:
            print("Downloading original version...")
            try:
                info = ydl.extract_info(url, download=True)
                if info:
                    # Get the actual file path yt-dlp used
                    downloaded_path = ydl.prepare_filename(info)
                    # Now sanitize and add timestamp
                    title = info.get('title', 'video')
                    sanitized_title = sanitize_filename(title)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_filename = f"original_{sanitized_title}_{timestamp}.mp4"
                    new_path = os.path.join('downloads', new_filename)
                    if downloaded_path != new_path:
                        try:
                            os.rename(downloaded_path, new_path)
                            print(f"Renamed {downloaded_path} to {new_path}")
                        except Exception as e:
                            print(f"Error renaming file: {str(e)}")
                            # fallback: copy and remove
                            try:
                                import shutil
                                shutil.copy2(downloaded_path, new_path)
                                os.remove(downloaded_path)
                                print(f"Copied and removed {downloaded_path} to {new_path}")
                            except Exception as e2:
                                print(f"Error copying file: {str(e2)}")
                                new_path = downloaded_path
                                print(f"Using original file: {downloaded_path}")
                    original_path = new_path
                    if os.path.exists(original_path):
                        orig_size = os.path.getsize(original_path) / (1024 * 1024)  # MB
                        print(f"Original download completed: {original_path} (Size: {orig_size:.2f} MB)")
                        
                        if FFMPEG_PATH:
                            # Create medium quality version (720p)
                            try:
                                medium_filename = f"medium_{sanitized_title}_{timestamp}.mp4"
                                medium_path = os.path.join('downloads', medium_filename)
                                print("Creating medium quality version (720p)...")
                                medium_cmd = [
                                    FFMPEG_PATH,
                                    '-i', original_path,
                                    '-vf', 'scale=-2:720',  # 720p
                                    '-c:v', 'libx264',      # Video codec
                                    '-crf', '23',           # Quality (lower = better, 18-28 is good)
                                    '-preset', 'medium',     # Encoding speed preset
                                    '-c:a', 'aac',          # Audio codec
                                    '-b:a', '128k',         # Audio bitrate
                                    '-y',                    # Overwrite output
                                    medium_path
                                ]
                                process = await asyncio.create_subprocess_exec(
                                    *medium_cmd,
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE
                                )
                                await process.communicate()
                                if os.path.exists(medium_path):
                                    med_size = os.path.getsize(medium_path) / (1024 * 1024)
                                    print(f"Medium version completed: {medium_path} (Size: {med_size:.2f} MB)")
                            except Exception as e:
                                print(f"Error creating medium version: {str(e)}")
                            
                            # Create small version (480p)
                            try:
                                small_filename = f"small_{sanitized_title}_{timestamp}.mp4"
                                small_path = os.path.join('downloads', small_filename)
                                print("Creating small quality version (480p)...")
                                small_cmd = [
                                    FFMPEG_PATH,
                                    '-i', original_path,
                                    '-vf', 'scale=-2:480',  # 480p
                                    '-c:v', 'libx264',      # Video codec
                                    '-crf', '28',           # Quality (lower = better, 18-28 is good)
                                    '-preset', 'medium',     # Encoding speed preset
                                    '-c:a', 'aac',          # Audio codec
                                    '-b:a', '96k',          # Audio bitrate
                                    '-y',                    # Overwrite output
                                    small_path
                                ]
                                process = await asyncio.create_subprocess_exec(
                                    *small_cmd,
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE
                                )
                                await process.communicate()
                                if os.path.exists(small_path):
                                    small_size = os.path.getsize(small_path) / (1024 * 1024)
                                    print(f"Small version completed: {small_path} (Size: {small_size:.2f} MB)")
                            except Exception as e:
                                print(f"Error creating small version: {str(e)}")
            except yt_dlp.utils.DownloadError as e:
                print(f"yt-dlp download error: {str(e)}")
                if "requested format not available" in str(e).lower():
                    print("Video format not available - might be a private or deleted video")
                elif "video is private" in str(e).lower():
                    print("Video is private")
                elif "sign in to view" in str(e).lower():
                    print("Video requires authentication")
                return None, None, None
                
    except Exception as e:
        print(f"Error downloading video: {str(e)}")
        return None, None, None
        
    return small_path, medium_path, original_path

@with_retries()
def upload_media(file_path: str):
    """Upload media to WhatsApp Cloud API with retry logic"""
    url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/media"
    
    # Create headers with the full token
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",  # Token is already stripped on load
    }
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    file_size = os.path.getsize(file_path)
    print(f"File size: {file_size / (1024*1024):.2f} MB")
    
    with open(file_path, 'rb') as file:
        form_data = {
            'messaging_product': (None, 'whatsapp'),
            'file': (os.path.basename(file_path), file, 'video/mp4')
        }
        print(f"Uploading file: {file_path}")
        print("\nDEBUG: Request details:")
        print(f"URL: {url}")
        print("Headers:", json.dumps({k: v if k != "Authorization" else f"Bearer {WHATSAPP_TOKEN[:20]}...{WHATSAPP_TOKEN[-20:]}" for k, v in headers.items()}, indent=2))
        print("Form data:", form_data)
        
        try:
            response = requests.post(url, headers=headers, files=form_data, timeout=120)
            print(f"Upload response status: {response.status_code}")
            print(f"Upload response body: {response.text}")
            
            if response.status_code == 401:
                print("\nDEBUG: Token details:")
                print(f"Token length: {len(WHATSAPP_TOKEN)}")
                print(f"Token prefix: {WHATSAPP_TOKEN[:20]}")
                print(f"Token suffix: {WHATSAPP_TOKEN[-20:]}")
                
            response.raise_for_status()
            return response.json().get('id')
        except requests.exceptions.Timeout:
            print("Upload timed out after 120 seconds")
            raise
        except requests.exceptions.RequestException as e:
            print(f"Upload failed: {str(e)}")
            raise

@with_retries()
def send_message(to: str, message: str):
    """Send a text message using WhatsApp API with retry logic"""
    url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/messages"
    
    print(f"\n{'='*50}")
    print("SENDING MESSAGE")
    print(f"To: {to}")
    print(f"Message length: {len(message)}")
    print("Message content:")
    print(message)
    print(f"{'='*50}\n")
    
    # Create headers with the full token
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",  # Token is already stripped on load
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    
    try:
        print("\nDEBUG: Request details:")
        print(f"URL: {url}")
        print("Headers:", json.dumps({k: v if k != "Authorization" else f"Bearer {WHATSAPP_TOKEN[:20]}...{WHATSAPP_TOKEN[-20:]}" for k, v in headers.items()}, indent=2))
        print("Data:", json.dumps(data, indent=2))
        
        response = requests.post(url, headers=headers, json=data)
        print(f"\nResponse status: {response.status_code}")
        print(f"Response body: {response.text}")
        
        if response.status_code == 401:
            print("\nDEBUG: Token details:")
            print(f"Token length: {len(WHATSAPP_TOKEN)}")
            print(f"Token prefix: {WHATSAPP_TOKEN[:20]}")
            print(f"Token suffix: {WHATSAPP_TOKEN[-20:]}")
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error in send_message: {str(e)}")
        print(f"Full error details: {type(e).__name__}: {str(e)}")
        raise

@with_retries()
def send_video(to: str, video_path: str):
    """Send a video file using WhatsApp API with retry logic"""
    try:
        # First upload the video
        print("Starting video upload process...")
        media_id = upload_media(video_path)
        
        if not media_id:
            raise Exception("Failed to upload video")
            
        print(f"Video uploaded successfully with media_id: {media_id}")
        
        # Now send the message with the media ID
        url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/messages"
        
        # Create headers with the full token
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",  # Token is already stripped on load
            "Content-Type": "application/json"
        }
        
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "video",
            "video": {
                "id": media_id,
                "caption": ""
            }
        }
        
        print("Sending video message...")
        print("\nDEBUG: Request details:")
        print(f"URL: {url}")
        print("Headers:", json.dumps({k: v if k != "Authorization" else f"Bearer {WHATSAPP_TOKEN[:20]}...{WHATSAPP_TOKEN[-20:]}" for k, v in headers.items()}, indent=2))
        print("Data:", json.dumps(data, indent=2))
        
        response = requests.post(url, headers=headers, json=data)
        print(f"Video send response status: {response.status_code}")
        print(f"Video send response body: {response.text}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error sending video: {str(e)}")
        print(f"Full error details: {type(e).__name__}: {str(e)}")
        send_message(to, "❌ Error sending video. Retrying...")
        raise  # Re-raise to trigger retry

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Handle webhook verification from WhatsApp"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return Response(content=challenge, media_type="text/plain")
        else:
            return Response(status_code=403)

@app.post("/webhook")
async def receive_webhook(request: Request):
    """Handle incoming webhooks from WhatsApp"""
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
                return {"status": "ok"}
                
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
                            return {"status": "ok"}
                    
                    # Update cache with current timestamp
                    message_cache[message_id] = time.time()
                    
                    # Clean old entries from cache
                    current_time = time.time()
                    message_cache.update({k: v for k, v in message_cache.items() 
                                       if current_time - v < MESSAGE_CACHE_TTL})
                
                await handle_message_update(value)
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Error in webhook: {str(e)}")
        print(f"Full error details: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}

async def handle_message_update(value):
    """Handle incoming messages"""
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
                        small_path, medium_path, original_path = await download_video(url)
                        if not original_path:
                            print(f"Failed to download video from URL: {url}")
                            send_message(from_number, "❌ Could not download video. For Facebook videos, please make sure:\n\n1. The video is public\n2. You're sharing the direct video URL\n3. The video hasn't been deleted")
                            return
                            
                        # Generate download links for all versions
                        links = []
                        print("\nGenerating download links...")
                        
                        # Original quality
                        if original_path and os.path.exists(original_path):
                            print(f"Found original file: {original_path}")
                            filename = os.path.basename(original_path).strip()
                            encoded_filename = quote(filename)
                            original_size = os.path.getsize(original_path) / (1024 * 1024)  # MB
                            original_url = f"{BASE_URL.strip()}/downloads/{encoded_filename}"
                            link_text = f"📹 Original Quality ({original_size:.1f}MB):\n{original_url}"
                            links.append(link_text)
                            print(f"Added original quality link: {link_text}")
                            
                            # Try to send directly if under 16MB
                            if original_size < 16:
                                print(f"Original file is under 16MB ({original_size:.1f}MB), sending directly...")
                                try:
                                    await send_video(from_number, original_path)
                                    message = "🎥 Here's your video!\n\n📥 You can also download it here:\n\n" + "\n\n".join(links)
                                    print(f"\nSending message with video and links:\n{message}")
                                    send_message(from_number, message)
                                    return
                                except Exception as e:
                                    print(f"Error sending video directly: {str(e)}")
                                    # Continue to send links only
                        else:
                            print("Original file not found or doesn't exist")
                        
                        # Medium quality
                        if medium_path and os.path.exists(medium_path):
                            print(f"Found medium file: {medium_path}")
                            filename = os.path.basename(medium_path).strip()
                            encoded_filename = quote(filename)
                            medium_size = os.path.getsize(medium_path) / (1024 * 1024)
                            medium_url = f"{BASE_URL.strip()}/downloads/{encoded_filename}"
                            link_text = f"📹 Medium Quality - 720p ({medium_size:.1f}MB):\n{medium_url}"
                            links.append(link_text)
                            print(f"Added medium quality link: {link_text}")
                        else:
                            print("Medium file not found or doesn't exist")
                        
                        # Small quality
                        if small_path and os.path.exists(small_path):
                            print(f"Found small file: {small_path}")
                            filename = os.path.basename(small_path).strip()
                            encoded_filename = quote(filename)
                            small_size = os.path.getsize(small_path) / (1024 * 1024)
                            small_url = f"{BASE_URL.strip()}/downloads/{encoded_filename}"
                            link_text = f"📹 Small Quality - 480p ({small_size:.1f}MB):\n{small_url}"
                            links.append(link_text)
                            print(f"Added small quality link: {link_text}")
                        else:
                            print("Small file not found or doesn't exist")
                            
                        print(f"\nTotal links generated: {len(links)}")
                        
                        if not links:
                            print("No links were generated!")
                            send_message(from_number, "❌ Error: No download links could be generated. Please try again.")
                            return
                            
                        # Send links only message
                        message = "📥 Download options (tap link and click 'Download Video'):\n\n" + "\n\n".join(links)
                        print(f"\nSending message with links:\n{message}")
                        send_message(from_number, message)
                            
                    except Exception as e:
                        print(f"Error downloading video: {str(e)}")
                        send_message(from_number, "❌ Error downloading video. Please check if the video is accessible.")
                        return
                else:
                    help_message = """👋 Welcome to WA Video Downloader!
                    
Just send me a Facebook or YouTube video URL, and I'll download it for you.

Supported platforms:
• Facebook
• YouTube

Note: Videos under 16MB will be sent directly in chat. For all videos, you'll get download links in different qualities."""
                    send_message(from_number, help_message)
                    
    except Exception as e:
        print(f"Error in handle_message_update: {str(e)}")
        print(f"Full error details: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

# Create downloads directory if it doesn't exist
os.makedirs("downloads", exist_ok=True)

# Mount the downloads directory
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

@app.get("/downloads/{filename:path}")
async def download_page(filename: str):
    """Serve a download page with button"""
    file_path = os.path.join("downloads", filename)
    if os.path.exists(file_path):
        # Get the file size for display
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        # Create an HTML page with download button
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Download Video</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    min-height: 90vh;
                    background-color: #f0f2f5;
                }}
                .container {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    text-align: center;
                    max-width: 90%;
                    width: 500px;
                }}
                h1 {{
                    color: #1a73e8;
                    font-size: 24px;
                    margin-bottom: 20px;
                }}
                .info {{
                    color: #5f6368;
                    margin-bottom: 20px;
                }}
                .download-btn {{
                    background-color: #1a73e8;
                    color: white;
                    padding: 12px 24px;
                    border: none;
                    border-radius: 5px;
                    font-size: 16px;
                    cursor: pointer;
                    text-decoration: none;
                    display: inline-block;
                    margin-top: 10px;
                }}
                .download-btn:hover {{
                    background-color: #1557b0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Your Video is Ready!</h1>
                <div class="info">
                    <p>Filename: {filename}</p>
                    <p>Size: {size_mb:.1f} MB</p>
                </div>
                <a href="/direct-download/{quote(filename)}" class="download-btn">
                    Download Video
                </a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    return {"error": "File not found"}, 404

@app.get("/direct-download/{filename:path}")
async def direct_download(filename: str):
    """Handle the actual file download"""
    file_path = os.path.join("downloads", filename)
    if os.path.exists(file_path):
        # Force download with application/octet-stream
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Content-Type": "application/octet-stream",  # Force download instead of play
            "Content-Length": str(os.path.getsize(file_path))
        }
        return FileResponse(
            file_path,
            headers=headers,
            filename=filename
        )
    return {"error": "File not found"}, 404

# Add a test endpoint
@app.get("/")
async def root():
    return {"message": "WhatsApp Webhook is running!"}

async def cleanup_old_files():
    """Remove files older than FILE_RETENTION_HOURS"""
    while True:
        try:
            now = datetime.now()
            for filename in os.listdir("downloads"):
                file_path = os.path.join("downloads", filename)
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                if now - file_modified > timedelta(hours=FILE_RETENTION_HOURS):
                    try:
                        os.remove(file_path)
                        print(f"Removed old file: {filename}")
                    except Exception as e:
                        print(f"Error removing file {filename}: {str(e)}")
        except Exception as e:
            print(f"Error in cleanup: {str(e)}")
        await asyncio.sleep(3600)  # Run every hour

@app.on_event("startup")
async def startup_event():
    """Run startup tasks"""
    print("\nServer Configuration:")
    print(f"BASE_URL: {BASE_URL}")
    print(f"WHATSAPP_API_URL: {WHATSAPP_API_URL}")
    print(f"PHONE_NUMBER_ID: {PHONE_NUMBER_ID}")
    print("\nStarting cleanup task...")
    asyncio.create_task(cleanup_old_files())
    print("Server started successfully!\n") 