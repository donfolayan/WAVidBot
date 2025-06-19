import cloudinary
import cloudinary.uploader
import cloudinary.api
from config import CLOUDINARY_RETENTION_HOURS
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor

cloudinary.config(secure=True)

executor = ThreadPoolExecutor()

def upload_to_cloudinary(file_path, folder="wa-downloads"):
    """Uploads a file to Cloudinary and returns the URL and public_id."""
    response = cloudinary.uploader.upload(
        file_path,
        resource_type="video",
        folder=folder,
        use_filename=True,
        unique_filename=False,
        overwrite=True
    )
    return response.get("secure_url"), response.get("public_id")

async def async_upload_to_cloudinary(file_path, folder="wa-downloads"):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, upload_to_cloudinary, file_path, folder)

def cleanup_cloudinary_files(folder="wa-downloads", retention_hours=CLOUDINARY_RETENTION_HOURS):
    """Deletes Cloudinary files older than retention_hours in the given folder."""
    cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
    resources = cloudinary.api.resources(type="upload", prefix=folder, resource_type="video", max_results=500)
    for res in resources.get("resources", []):
        created_at = datetime.strptime(res["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        if created_at < cutoff:
            print(f"Deleting Cloudinary file: {res['public_id']} (created at {created_at})")
            cloudinary.uploader.destroy(res["public_id"], resource_type="video") 