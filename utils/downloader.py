import os
import re
import time
import json
import aiohttp
import asyncio
import logging
import aiofiles
from typing import Optional, Tuple, List, Dict
from urllib.parse import unquote, urlparse, parse_qs
from config import Config
from utils.progress import Progress
from utils.helpers import sanitize_filename, extract_gdrive_id

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self):
        self.progress = Progress()
        self.chunk_size = Config.CHUNK_SIZE
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=7200,
                connect=60,
                sock_read=300
            )
            connector = aiohttp.TCPConnector(
                limit=20,
                limit_per_host=10,
                force_close=False,
                enable_cleanup_closed=True
            )
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive',
            }
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=headers
            )
        return self.session
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def get_extension_from_content_type(self, content_type: str) -> str:
        """Get file extension from content-type"""
        content_type_map = {
            'video/mp4': '.mp4',
            'video/x-matroska': '.mkv',
            'video/webm': '.webm',
            'video/avi': '.avi',
            'video/x-msvideo': '.avi',
            'video/quicktime': '.mov',
            'video/x-flv': '.flv',
            'video/3gpp': '.3gp',
            'audio/mpeg': '.mp3',
            'audio/mp3': '.mp3',
            'audio/wav': '.wav',
            'audio/x-wav': '.wav',
            'audio/flac': '.flac',
            'audio/aac': '.aac',
            'audio/ogg': '.ogg',
            'audio/m4a': '.m4a',
            'audio/mp4': '.m4a',
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'application/pdf': '.pdf',
            'application/zip': '.zip',
            'application/x-rar-compressed': '.rar',
            'application/vnd.android.package-archive': '.apk',
            'application/octet-stream': '',
        }
        
        ct = content_type.split(';')[0].strip().lower()
        return content_type_map.get(ct, '')
    
    def ensure_extension(self, filename: str, content_type: str = '', url: str = '') -> str:
        """Ensure filename has proper extension"""
        if not filename:
            filename = "downloaded_file"
        
        name, ext = os.path.splitext(filename)
        
        if ext and len(ext) <= 5 and ext != '.':
            return filename
        
        if content_type:
            ct_ext = self.get_extension_from_content_type(content_type)
            if ct_ext:
                return f"{name}{ct_ext}"
        
        if url:
            parsed = urlparse(url)
            url_path = parsed.path
            _, url_ext = os.path.splitext(url_path)
            if url_ext and len(url_ext) <= 5:
                return f"{name}{url_ext}"
        
        if 'video' in content_type.lower():
            return f"{name}.mp4"
        
        return filename
    
    # ============ DOWNLOAD FILE ============
    async def download_file(
        self,
        url: str,
        download_path: str,
        progress_message,
        filename: str = "downloading",
        headers: dict = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download file with progress"""
        try:
            session = await self.get_session()
            
            request_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive',
            }
            
            if headers:
                request_headers.update(headers)
            
            async with session.get(url, headers=request_headers, allow_redirects=True) as resp:
                if resp.status not in [200, 206]:
                    return False, None, f"HTTP Error: {resp.status}"
                
                total_size = int(resp.headers.get('Content-Length', 0))
                content_type = resp.headers.get('Content-Type', '')
                
                # Get filename from headers
                cd = resp.headers.get('Content-Disposition', '')
                if 'filename=' in cd:
                    matches = re.findall(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd)
                    if matches:
                        filename = sanitize_filename(unquote(matches[0]))
                
                # Get from URL if needed
                if filename == "downloading" or filename == "downloaded_file":
                    url_path = urlparse(str(resp.url)).path
                    if url_path:
                        url_filename = url_path.split('/')[-1]
                        if url_filename and len(url_filename) > 1:
                            filename = sanitize_filename(unquote(url_filename))
                
                # Ensure extension
                filename = self.ensure_extension(filename, content_type, str(resp.url))
                
                logger.info(f"📥 Downloading: {filename} ({total_size} bytes)")
                
                file_path = os.path.join(download_path, filename)
                
                # Unique filename
                base, ext = os.path.splitext(file_path)
                counter = 1
                while os.path.exists(file_path):
                    file_path = f"{base}_{counter}{ext}"
                    counter += 1
                
                # Download
                downloaded = 0
                start_time = time.time()
                
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(self.chunk_size):
                        if chunk:
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            if self.progress.should_update() and progress_message:
                                try:
                                    elapsed = time.time() - start_time
                                    speed = downloaded / elapsed if elapsed > 0 else 0
                                    display_total = total_size if total_size > 0 else downloaded
                                    eta = int((display_total - downloaded) / speed) if speed > 0 and total_size > 0 else 0
                                    
                                    text = self.progress.get_download_progress_text(
                                        filename, downloaded, display_total, speed, eta
                                    )
                                    await progress_message.edit_text(text)
                                except:
                                    pass
                
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    logger.info(f"✅ Downloaded: {file_path}")
                    return True, file_path, None
                else:
                    return False, None, "Download failed - empty file"
        
        except asyncio.CancelledError:
            return False, None, "Download cancelled"
        except asyncio.TimeoutError:
            return False, None, "Download timeout"
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False, None, str(e)
    
    # ============ GOOGLE DRIVE ============
    async def get_gdrive_info(self, file_id: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """Get Google Drive file info"""
        try:
            session = await self.get_session()
            download_url = f"https://drive.google.com/uc?id={file_id}&export=download"
            
            async with session.get(download_url, allow_redirects=False) as resp:
                if resp.status == 302:
                    redirect_url = resp.headers.get('Location', '')
                    filename = "gdrive_file"
                    cd = resp.headers.get('Content-Disposition', '')
                    if 'filename=' in cd:
                        match = re.findall(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd)
                        if match:
                            filename = unquote(match[0])
                    return redirect_url, sanitize_filename(filename), None
            
            async with session.get(download_url) as resp:
                text = await resp.text()
                
                confirm_match = re.search(r'confirm=([0-9A-Za-z_-]+)', text)
                uuid_match = re.search(r'uuid=([0-9A-Za-z_-]+)', text)
                
                if confirm_match:
                    confirm_token = confirm_match.group(1)
                    if uuid_match:
                        uuid_token = uuid_match.group(1)
                        download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm_token}&uuid={uuid_token}"
                    else:
                        download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm_token}"
                
                filename_match = re.search(r'"title":"([^"]+)"', text)
                if not filename_match:
                    filename_match = re.search(r'<span class="uc-name-size"><a[^>]*>([^<]+)</a>', text)
                
                filename = filename_match.group(1) if filename_match else "gdrive_file"
                return download_url, sanitize_filename(filename), None
        
        except Exception as e:
            logger.error(f"GDrive info error: {e}")
            return None, None, None
    
    async def download_gdrive(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Google Drive (including usercontent and storage links)"""
        try:
            # Check if it's a direct download link (usercontent or storage)
            if 'drive.usercontent.google.com' in url or 'storage.googleapis.com' in url:
                logger.info("📁 Detected: Google Direct Download Link")
                return await self.download_file(
                    url, download_path, progress_message,
                    "google_file", {}
                )
            
            # Regular Google Drive link
            file_id = extract_gdrive_id(url)
            if not file_id:
                return False, None, "Invalid Google Drive URL"
            
            download_url, filename, size = await self.get_gdrive_info(file_id)
            
            if not download_url:
                return False, None, "Could not get download URL"
            
            headers = {'Cookie': 'download_warning_token=1'}
            
            return await self.download_file(
                download_url, download_path, progress_message,
                filename or "gdrive_file", headers
            )
        
        except Exception as e:
            logger.error(f"GDrive download error: {e}")
            return False, None, str(e)
    
    # ============ TERABOX ============
    async def get_terabox_info(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """Get Terabox download info"""
        try:
            session = await self.get_session()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.terabox.com/',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None, "terabox_file.mp4", None
                
                text = await resp.text()
                
                # Find download link
                download_patterns = [
                    r'"dlink":"([^"]+)"',
                    r'"downloadLink":"([^"]+)"',
                    r'"link":"([^"]+)"',
                ]
                
                download_url = None
                for pattern in download_patterns:
                    match = re.search(pattern, text)
                    if match:
                        download_url = match.group(1).replace('\\/', '/').replace('\\u0026', '&')
                        if download_url.startswith('http'):
                            break
                        download_url = None
                
                # Find filename
                filename_patterns = [
                    r'"server_filename":"([^"]+)"',
                    r'"filename":"([^"]+)"',
                    r'"name":"([^"]+)"',
                ]
                
                filename = "terabox_file"
                for pattern in filename_patterns:
                    match = re.search(pattern, text)
                    if match:
                        fname = match.group(1).strip()
                        if fname and fname not in ["TeraBox", "1024Tera", ""]:
                            filename = fname
                            break
                
                # Ensure extension
                if '.' not in filename:
                    filename = f"{filename}.mp4"
                
                # Get size
                size = None
                size_match = re.search(r'"size":(\d+)', text)
                if size_match:
                    size = int(size_match.group(1))
                
                return download_url, sanitize_filename(filename), size
        
        except Exception as e:
            logger.error(f"Terabox info error: {e}")
            return None, "terabox_file.mp4", None
    
    async def download_terabox(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Terabox"""
        try:
            # Check if it's a folder link
            if 'filelist' in url.lower() and 'path=' in url.lower():
                logger.info("📁 Detected: Terabox Folder - Downloading as single file")
                # Don't use recursive folder download - just try to get the file
            
            download_url, filename, size = await self.get_terabox_info(url)
            
            if not download_url:
                # Try direct download
                logger.info("📁 Trying direct Terabox download...")
                headers = {'Referer': 'https://www.terabox.com/'}
                if Config.TERABOX_COOKIE:
                    headers['Cookie'] = Config.TERABOX_COOKIE
                
                return await self.download_file(
                    url, download_path, progress_message,
                    filename or "terabox_file.mp4", headers
                )
            
            headers = {'Referer': 'https://www.terabox.com/'}
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            return await self.download_file(
                download_url, download_path, progress_message,
                filename or "terabox_file.mp4", headers
            )
        
        except Exception as e:
            logger.error(f"Terabox download error: {e}")
            return False, None, str(e)
    
    async def download_direct(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from direct link"""
        try:
            parsed = urlparse(url)
            filename = parsed.path.split('/')[-1]
            filename = unquote(filename) if filename else "downloaded_file"
            
            return await self.download_file(
                url, download_path, progress_message,
                sanitize_filename(filename)
            )
        
        except Exception as e:
            logger.error(f"Direct download error: {e}")
            return False, None, str(e)
