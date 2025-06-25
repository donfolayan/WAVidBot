from dotenv import load_dotenv
load_dotenv()

import os
import cloudinary
import cloudinary.uploader

print("DEBUG: CLOUDINARY_URL at import:", os.getenv("CLOUDINARY_URL"))
cloudinary.config(secure=True)
print("Cloudinary config:", cloudinary.config().cloud_name, cloudinary.config().api_key)

def test_upload():
    # You can use any local file or a URL
    result = cloudinary.uploader.upload(
        "https://cloudinary-devs.github.io/cld-docs-assets/assets/images/butterfly.jpeg",
        resource_type="image",
        public_id="quickstart_butterfly",
        unique_filename=False,
        overwrite=True
    )
    print("Upload result:", result)
    print("Secure URL:", result.get("secure_url"))

if __name__ == "__main__":
    test_upload() 