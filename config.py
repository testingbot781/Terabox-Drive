import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Bot Configuration
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    
    # MongoDB
    MONGO_URL = os.environ.get("MONGO_URL", "")
    
    # Fixed Owners
    OWNER_IDS = [1598576202, 6518065496]
    
    # Log Channel
    LOG_CHANNEL = -1002286415377
    
    # Force Subscribe Channel
    FORCE_SUB_CHANNEL = "serenaunzipbot"
    FORCE_SUB_LINK = "https://t.me/serenaunzipbot"
    
    # Owner Contact
    OWNER_CONTACT = "https://t.me/technicalserena"
    OWNER_USERNAME = "@Xioqui_xin"
    
    # Start Picture
    START_PIC = os.environ.get("START_PIC", "")
    
    # Default Thumbnail for PDFs
    DEFAULT_THUMBNAIL = os.environ.get("DEFAULT_THUMBNAIL", "")
    
    # Freemium Limits (Configurable)
    FREE_DAILY_LIMIT = 5
    FREE_MAX_SIZE = 200 * 1024 * 1024  # 200 MB in bytes
    FREE_SPEED_LIMIT = 1  # MB/s (low speed)
    
    # Premium Limits
    PREMIUM_MAX_SIZE = 4 * 1024 * 1024 * 1024  # 4 GB in bytes
    PREMIUM_SPEED_LIMIT = 0  # 0 means unlimited
    
    # Progress Update Interval
    PROGRESS_UPDATE_INTERVAL = 8  # seconds
    
    # Download Path
    DOWNLOAD_PATH = "./downloads"
    
    # Flask Port for Render
    PORT = int(os.environ.get("PORT", 8080))
    
    # Bot Info
    BOT_NAME = "Serena Downloader Bot"
    BOT_VERSION = "1.0.0"
