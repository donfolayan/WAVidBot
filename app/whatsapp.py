import os
import json
import requests
from config import WHATSAPP_TOKEN, WHATSAPP_API_URL, PHONE_NUMBER_ID

def upload_media(file_path: str):
    url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/media"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
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

def send_message(to: str, message: str):
    url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/messages"
    print(f"\n{'='*50}")
    print("SENDING MESSAGE")
    print(f"To: {to}")
    print(f"Message length: {len(message)}")
    print("Message content:")
    print(message)
    print(f"{'='*50}\n")
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
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

def send_video(to: str, video_path: str):
    try:
        print("Starting video upload process...")
        media_id = upload_media(video_path)
        if not media_id:
            raise Exception("Failed to upload video")
        print(f"Video uploaded successfully with media_id: {media_id}")
        url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
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
        raise 