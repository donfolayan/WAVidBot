import os
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv('WHATSAPP_TOKEN', '').strip()
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN', 'wa_downloader_test_token')
WHATSAPP_API_URL = "https://graph.facebook.com/v22.0"
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
FILE_RETENTION_HOURS = int(os.getenv('FILE_RETENTION_HOURS', '24'))
MESSAGE_CACHE_TTL = 60
CLOUDINARY_RETENTION_HOURS = int(os.getenv('CLOUDINARY_RETENTION_HOURS', '24'))

if not WHATSAPP_TOKEN:
    raise ValueError("WHATSAPP_TOKEN environment variable is required")
if not PHONE_NUMBER_ID:
    raise ValueError("WHATSAPP_PHONE_NUMBER_ID environment variable is required") 