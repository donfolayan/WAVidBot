import os
import asyncio
import yt_dlp
import requests
import http.cookiejar
from datetime import datetime
from app.utils import sanitize_filename
from config import FFMPEG_PATH, CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET

# Import Cloudinary upload if available
try:
    from app.cloud import upload_to_cloudinary
    CLOUDINARY_AVAILABLE = all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET])
except ImportError:
    upload_to_cloudinary = None
    CLOUDINARY_AVAILABLE = False

def resolve_facebook_share(url, cookies_path=None):
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
        if 'login' in response.url or 'checkpoint' in response.url or 'robot' in response.text.lower():
            print(f"Warning: Facebook may be showing a login or bot challenge page: {response.url}")
        return response.url
    except Exception as e:
        print(f"Error resolving Facebook share URL: {str(e)}")
        return url

async def download_video(url: str, YOUTUBE_COOKIES_PATH=None, FACEBOOK_COOKIES_PATH=None) -> tuple:
    print(f"Starting download for URL: {url}")
    DOWNLOAD_DELAY_SECONDS = 2
    print(f"Delaying {DOWNLOAD_DELAY_SECONDS} seconds before download to avoid rapid requests...")
    await asyncio.sleep(DOWNLOAD_DELAY_SECONDS)
    cookies_path = None
    if 'youtube.com' in url or 'youtu.be' in url:
        cookies_path = YOUTUBE_COOKIES_PATH
        if cookies_path:
            print(f"Using YouTube cookies: {cookies_path}")
    elif 'facebook.com' in url:
        cookies_path = FACEBOOK_COOKIES_PATH
        if cookies_path:
            print(f"Using Facebook cookies: {cookies_path}")
    if 'facebook.com/share' in url:
        print("Detected Facebook share URL - attempting to resolve...")
        url = resolve_facebook_share(url, cookies_path)
        print(f"Resolved share URL to: {url}")
    original_opts = {
        'format': 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
        'outtmpl': 'downloads/original_%(title)s.%(ext)s',
        'quiet': False,
        'no_warnings': False,
        'merge_output_format': 'mp4',
        'verbose': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.70 Safari/537.36',
    }
    if cookies_path:
        original_opts['cookiefile'] = cookies_path
    original_path = None
    medium_path = None
    small_path = None
    try:
        with yt_dlp.YoutubeDL(original_opts) as ydl:
            print("Downloading original version...")
            try:
                info = ydl.extract_info(url, download=True)
                if info:
                    downloaded_path = ydl.prepare_filename(info)
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
                        orig_size = os.path.getsize(original_path) / (1024 * 1024)
                        print(f"Original download completed: {original_path} (Size: {orig_size:.2f} MB)")
                        return original_path, orig_size
            except yt_dlp.utils.DownloadError as e:
                print(f"yt-dlp download error: {str(e)}")
                if "requested format not available" in str(e).lower():
                    print("Video format not available - might be a private or deleted video")
                elif "video is private" in str(e).lower():
                    print("Video is private")
                elif "sign in to view" in str(e).lower():
                    print("Video requires authentication")
    except Exception as e:
        print(f"Error downloading video: {str(e)}")
    # If Cloudinary is available, upload and return URLs
    if CLOUDINARY_AVAILABLE and upload_to_cloudinary:
        try:
            print("Uploading to Cloudinary...")
            small_url, medium_url, original_url = None, None, None
            if small_path and os.path.exists(small_path):
                small_url, _ = upload_to_cloudinary(small_path)
                os.remove(small_path)
            if medium_path and os.path.exists(medium_path):
                medium_url, _ = upload_to_cloudinary(medium_path)
                os.remove(medium_path)
            if original_path and os.path.exists(original_path):
                original_url, _ = upload_to_cloudinary(original_path)
                os.remove(original_path)
            return small_url, medium_url, original_url
        except Exception as e:
            print(f"Cloudinary upload failed: {e}")
            # Fallback to local
    return None, None, None 