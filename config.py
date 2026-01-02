import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Bot Configuration
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    
    # MongoDB Configuration
    MONGO_URI = os.environ.get("MONGO_URI", "")
    DB_NAME = "TelegramDownloaderBot"
    
    # Fixed Owners
    OWNER_IDS = [1598576202, 6518065496]
    
    # Log Channel
    LOG_CHANNEL = -1003286415377
    
    # Force Subscribe Channel
    FORCE_SUB_CHANNEL = "serenaunzipbot"
    FORCE_SUB_LINK = "https://t.me/serenaunzipbot"
    
    # Owner Contact
    OWNER_CONTACT = "https://t.me/technicalserena"
    OWNER_USERNAME = "@Xioqui_xin"
    
    # Media URLs from Environment
    START_PIC = os.environ.get("START_PIC", "")
    THUMBNAIL_URL = os.environ.get("THUMBNAIL_URL", "")
    
    # Terabox Cookies (Optional - for better download)
    TERABOX_COOKIE = os.environ.get("TERABOX_COOKIE", "")
    
    # Freemium Limits (Configurable)
    FREE_DAILY_LIMIT = 5
    FREE_MAX_SIZE = 200 * 1024 * 1024  # 200 MB in bytes
    FREE_MAX_SIZE_MB = 200
    
    # Premium Limits
    PREMIUM_MAX_SIZE = 4 * 1024 * 1024 * 1024  # 4 GB in bytes
    PREMIUM_MAX_SIZE_MB = 4096
    
    # Download/Upload Settings
    PROGRESS_UPDATE_INTERVAL = 8  # seconds
    CHUNK_SIZE = 1024 * 1024  # 1 MB chunks
    
    # Temp Directory
    DOWNLOAD_DIR = "./downloads"
    
    # Flask Port for Render
    PORT = int(os.environ.get("PORT", 8080))
    
    # Supported Extensions
    VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp']
    AUDIO_EXTENSIONS = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a']
    IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff']
    DOCUMENT_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx', '.apk', '.zip', '.rar']
