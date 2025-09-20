import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import from app modules
from app.endpoints import router
from app.cleanup import cleanup_old_files
from config import (
    BASE_URL, WHATSAPP_API_URL, PHONE_NUMBER_ID
)

# Load environment variables
load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
if not WHATSAPP_TOKEN:
    print("ERROR: WHATSAPP_TOKEN not found in environment variables")
    exit(1)
print(f"Token loaded: {WHATSAPP_TOKEN[:10]}...{WHATSAPP_TOKEN[-10:] if len(WHATSAPP_TOKEN) > 20 else '***'}")

# Check if we're in development mode
IS_DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("true", "1", "yes")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("\nServer Configuration:")
    print(f"BASE_URL: {BASE_URL}")
    print(f"WHATSAPP_API_URL: {WHATSAPP_API_URL}")
    print(f"PHONE_NUMBER_ID: {PHONE_NUMBER_ID}")
    print(f"Development Mode: {'Enabled' if IS_DEV_MODE else 'Disabled'}")
    print("\nStarting cleanup task...")
    asyncio.create_task(cleanup_old_files())
    print("Server started successfully!\n")
    yield
    # Shutdown
    print("Server shutting down...")

# Configure docs URLs based on development mode
docs_url = "/docs" if IS_DEV_MODE else None
redoc_url = "/redoc" if IS_DEV_MODE else None
openapi_url = "/openapi.json" if IS_DEV_MODE else None

app = FastAPI(
    title="WhatsApp Video Downloader API",
    description="""
    A FastAPI application that downloads videos from YouTube and Facebook, processes them with ffmpeg, 
    and serves them via WhatsApp Business API with Cloudinary integration.
    
    ## Features
    - Download videos from YouTube and Facebook
    - Process videos with ffmpeg for optimal quality
    - Send videos directly via WhatsApp (files < 16MB)
    - Upload to Cloudinary for shareable links
    - Automatic cleanup of old files
    
    ## Endpoints
    - `/webhook` - WhatsApp webhook for receiving messages
    - `/test-download` - Development endpoint for testing downloads (DEV_MODE only)
    - `/downloads/` - Static file serving for downloaded videos
    - `/privacy` - Privacy Policy page
    - `/terms` - Terms and Conditions page
    
    ## Legal
    This service includes privacy policy and terms of service endpoints to ensure compliance
    with data protection regulations and provide clear usage guidelines.
    
    ## Security
    - All sensitive data is handled via environment variables
    - API documentation is disabled in production (when DEV_MODE=false)
    - Proper CORS configuration for webhook endpoints
    """,
    version="1.0.1",
    contact={
        "name": "WhatsApp Video Downloader",
        "url": "https://github.com/donfolayan/wavidbot",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url
)

# Add CORS middleware for webhook endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # WhatsApp webhooks can come from anywhere
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Create downloads directory if it doesn't exist
os.makedirs("downloads", exist_ok=True)

# Mount the downloads directory
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

# Include API routes
app.include_router(router) 