import os
from datetime import datetime, timedelta
import asyncio
from config import FILE_RETENTION_HOURS

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