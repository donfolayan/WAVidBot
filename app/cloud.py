import os

# If CLOUDINARY_URL is not set, construct it from individual vars
if not os.getenv("CLOUDINARY_URL"):
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")
    if cloud_name and api_key and api_secret:
        os.environ["CLOUDINARY_URL"] = f"cloudinary://{api_key}:{api_secret}@{cloud_name}"

import cloudinary
import cloudinary.uploader
import cloudinary.api
from config import CLOUDINARY_RETENTION_HOURS
from datetime import datetime, timedelta

cloudinary.config(secure=True)
print("Cloudinary config:", cloudinary.config().cloud_name, cloudinary.config().api_key)

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

def cleanup_cloudinary_files(folder="wa-downloads", retention_hours=CLOUDINARY_RETENTION_HOURS):
    """Deletes Cloudinary files older than retention_hours in the given folder."""
    cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
    resources = cloudinary.api.resources(type="upload", prefix=folder, resource_type="video", max_results=500)
    for res in resources.get("resources", []):
        created_at = datetime.strptime(res["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        if created_at < cutoff:
            print(f"Deleting Cloudinary file: {res['public_id']} (created at {created_at})")
            cloudinary.uploader.destroy(res["public_id"], resource_type="video") 