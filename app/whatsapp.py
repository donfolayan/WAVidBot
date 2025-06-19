import os
import json
import requests
from config import WHATSAPP_TOKEN, WHATSAPP_API_URL, PHONE_NUMBER_ID

def upload_media(file_path: str):
    """Upload a media file to WhatsApp and return the media ID"""
    try:
        file_size = os.path.getsize(file_path)
        print(f"File size: {file_size / (1024*1024):.2f} MB")
        
        url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/media"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        
        with open(file_path, "rb") as file:
            files = {"file": file}
            data = {"messaging_product": "whatsapp"}
            
            print(f"Uploading file: {file_path}")
            
            response = requests.post(url, headers=headers, files=files, data=data, timeout=120)
            
            if response.status_code == 200:
                return response.json().get("id")
            else:
                print(f"Upload failed with status {response.status_code}: {response.text}")
                return None
    except requests.exceptions.Timeout:
        print("Upload timed out after 120 seconds")
        return None
    except Exception as e:
        print(f"Upload failed: {str(e)}")
        return None

def send_message(to: str, message: str):
    """Send a text message via WhatsApp"""
    try:
        url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message}
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code != 200:
            print(f"Error in send_message: HTTP {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error in send_message: {str(e)}")
        print(f"Full error details: {type(e).__name__}: {str(e)}")

async def send_video(to: str, video_path: str):
    """Send a video message via WhatsApp"""
    try:
        print("Starting video upload process...")
        media_id = upload_media(video_path)
        if not media_id:
            raise Exception("Failed to upload video to WhatsApp")
        
        print(f"Video uploaded successfully with media_id: {media_id}")
        
        url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "video",
            "video": {"id": media_id}
        }
        
        print("Sending video message...")
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"Failed to send video: {response.text}")
    except Exception as e:
        print(f"Error sending video: {str(e)}")
        print(f"Full error details: {type(e).__name__}: {str(e)}")
        raise 