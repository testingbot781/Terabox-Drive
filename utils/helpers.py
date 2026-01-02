import os
import re
import shutil
import asyncio
import aiofiles
import logging
from typing import Optional, Tuple, List
from urllib.parse import urlparse, parse_qs, unquote
from config import Config

logger = logging.getLogger(__name__)

def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    if not filename:
        return ''
    if '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[-1].lower()
        # Validate extension length
        if len(ext) <= 6:
            return ext
    return ''

def get_file_type(extension: str) -> str:
    """Determine file type from extension"""
    if not extension:
        return "document"
    
    ext = extension.lower()
    
    # Video
    video_exts = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpeg', '.mpg', '.ts', '.vob']
    if ext in video_exts:
        return "video"
    
    # Audio
    audio_exts = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus', '.amr']
    if ext in audio_exts:
        return "audio"
    
    # Image
    image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.ico', '.svg']
    if ext in image_exts:
        return "image"
    
    # PDF
    if ext == '.pdf':
        return "pdf"
    
    # APK
    if ext == '.apk':
        return "apk"
    
    # Archive
    archive_exts = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz']
    if ext in archive_exts:
        return "archive"
    
    return "document"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to remove invalid characters"""
    if not filename:
        return "downloaded_file"
    
    # Decode URL encoding
    try:
        filename = unquote(filename)
    except:
        pass
    
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*\x00\n\r\t'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. \t\n\r')
    
    # Limit filename length but preserve extension
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    
    return filename if filename else "downloaded_file"

def extract_gdrive_id(url: str) -> Optional[str]:
    """Extract Google Drive file ID from URL"""
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'/folders/([a-zA-Z0-9_-]+)',
        r'open\?id=([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def is_gdrive_folder(url: str) -> bool:
    """Check if Google Drive URL is a folder"""
    return '/folders/' in url or 'folderview' in url

def extract_terabox_id(url: str) -> Optional[str]:
    """Extract Terabox file ID from URL"""
    patterns = [
        r'surl=([a-zA-Z0-9_-]+)',
        r'/s/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def is_gdrive_link(url: str) -> bool:
    """Check if URL is a Google Drive link"""
    gdrive_patterns = [
        'drive.google.com',
        'docs.google.com',
    ]
    return any(pattern in url.lower() for pattern in gdrive_patterns)

def is_terabox_link(url: str) -> bool:
    """Check if URL is a Terabox link"""
    terabox_patterns = [
        'terabox.com',
        'teraboxapp.com',
        '1024terabox.com',
        '1024tera.com',
        'terabox.app',
        'gcloud.life',
        'momerybox.com',
        'teraboxlink.com',
        'freeterabox.com',
        'terabox.tech',
        'teraboxshare.com',
    ]
    return any(pattern in url.lower() for pattern in terabox_patterns)

def is_terabox_folder(url: str) -> bool:
    """Check if Terabox URL is a folder"""
    return 'filelist' in url.lower() or 'path=' in url.lower()

def is_direct_link(url: str) -> bool:
    """Check if URL is a direct download link"""
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        direct_extensions = [
            '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.3gp',
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a',
            '.pdf', '.zip', '.rar', '.7z', '.apk',
            '.jpg', '.jpeg', '.png', '.gif', '.webp'
        ]
        return any(path.endswith(ext) for ext in direct_extensions)
    except:
        return False

def extract_links_from_text(text: str) -> List[str]:
    """Extract all URLs from text"""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    return [url.strip() for url in urls if url.strip()]

async def read_txt_file(file_path: str) -> List[str]:
    """Read links from txt file"""
    links = []
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = await f.read()
            links = extract_links_from_text(content)
    except Exception as e:
        logger.error(f"Error reading txt file: {e}")
    return links

def create_download_dir(user_id: int) -> str:
    """Create download directory for user"""
    user_dir = os.path.join(Config.DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

async def cleanup_file(file_path: str):
    """Delete file after upload"""
    try:
        if file_path and os.path.exists(file_path):
            if os.path.isfile(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ Cleaned: {file_path}")
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                logger.info(f"🗑️ Cleaned dir: {file_path}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

async def cleanup_user_dir(user_id: int):
    """Clean up user's download directory completely"""
    try:
        user_dir = os.path.join(Config.DOWNLOAD_DIR, str(user_id))
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            logger.info(f"🗑️ Cleaned user dir: {user_dir}")
    except Exception as e:
        logger.error(f"User dir cleanup error: {e}")

def get_readable_file_size(size_bytes: int) -> str:
    """Convert bytes to readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

async def zip_folder(folder_path: str, output_path: str) -> str:
    """Zip a folder"""
    try:
        shutil.make_archive(output_path.replace('.zip', ''), 'zip', folder_path)
        return output_path
    except Exception as e:
        logger.error(f"Zip error: {e}")
        raise

def generate_summary(results: dict) -> str:
    """Generate task summary"""
    total = results.get('total', 0)
    success = results.get('success', 0)
    failed = results.get('failed', 0)
    
    file_types = results.get('file_types', {})
    
    summary = f"""
📊 **Task Summary**
━━━━━━━━━━━━━━━━━━━━━━

✅ **Successful:** {success}
❌ **Failed:** {failed}
📁 **Total:** {total}

📋 **File Types:**
"""
    
    if file_types:
        for ftype, count in file_types.items():
            emoji = {
                'video': '🎬',
                'audio': '🎵',
                'image': '🖼️',
                'pdf': '📄',
                'apk': '📱',
                'archive': '🗜️',
                'document': '📎'
            }.get(ftype, '📁')
            summary += f"{emoji} {ftype.title()}: {count}\n"
    else:
        summary += "None\n"
    
    summary += "━━━━━━━━━━━━━━━━━━━━━━"
    
    return summary
