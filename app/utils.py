import os
import re
from datetime import datetime
import base64
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing special characters and emojis"""
    filename = re.sub(r'[^\w\s-]', '', filename)
    filename = re.sub(r'\s+', ' ', filename)
    if len(filename) > 50:
        filename = filename[:47] + "..."
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename}_{timestamp}"
    return filename.strip()

def setup_cookies():
    """Create cookies files from base64-encoded environment variables at runtime"""
    youtube_cookies = os.getenv('YOUTUBE_COOKIES_CONTENT')
    facebook_cookies = os.getenv('FACEBOOK_COOKIES_CONTENT')
    youtube_path = None
    facebook_path = None
    if youtube_cookies:
        try:
            youtube_cookies = youtube_cookies.strip()
            decoded = base64.b64decode(youtube_cookies)
            if not decoded.startswith(b"# Netscape HTTP Cookie File"):
                logger.warning("Decoded YouTube cookies file does not start with Netscape header")
            with open('youtube_cookies.txt', 'wb') as f:
                f.write(decoded)
            youtube_path = 'youtube_cookies.txt'
            logger.info("YouTube cookies file created successfully (base64 decoded)")
        except Exception as e:
            logger.error(f"Error creating YouTube cookies file: {e}")
    if facebook_cookies:
        try:
            facebook_cookies = facebook_cookies.strip()
            decoded = base64.b64decode(facebook_cookies)
            if not decoded.startswith(b"# Netscape HTTP Cookie File"):
                logger.warning("Decoded Facebook cookies file does not start with Netscape header")
            with open('facebook_cookies.txt', 'wb') as f:
                f.write(decoded)
            facebook_path = 'facebook_cookies.txt'
            logger.info("Facebook cookies file created successfully (base64 decoded)")
        except Exception as e:
            logger.error(f"Error creating Facebook cookies file: {e}")
    return youtube_path, facebook_path 