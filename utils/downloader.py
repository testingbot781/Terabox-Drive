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
from utils.helpers import sanitize_filename, extract_gdrive_id, is_terabox_folder

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self):
        self.progress = Progress()
        self.chunk_size = Config.CHUNK_SIZE
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=3600)
            connector = aiohttp.TCPConnector(limit=10, force_close=True)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
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
    
    # ============ GOOGLE DRIVE ============
    async def get_gdrive_info(self, file_id: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """Get Google Drive file info and download URL"""
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
            
            # For larger files
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
            
            # Add cookie if available
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status != 200:
                    return url, "terabox_file", None
                
                text = await resp.text()
                
                # Try to find download link in various patterns
                download_patterns = [
                    r'"dlink":"([^"]+)"',
                    r'"downloadLink":"([^"]+)"',
                    r'"link":"([^"]+)"',
                    r'"urls":\[.*?"url":"([^"]+)"',
                ]
                
                download_url = None
                for pattern in download_patterns:
                    match = re.search(pattern, text)
                    if match:
                        download_url = match.group(1).replace('\\/', '/').replace('\\u0026', '&')
                        if 'http' in download_url:
                            break
                
                # Extract filename
                filename_patterns = [
                    r'"server_filename":"([^"]+)"',
                    r'"filename":"([^"]+)"',
                    r'"name":"([^"]+)"',
                    r'"title":"([^"]+)"',
                ]
                
                filename = "terabox_file"
                for pattern in filename_patterns:
                    match = re.search(pattern, text)
                    if match:
                        fname = match.group(1).strip()
                        if fname and fname not in ["TeraBox", "1024Tera", ""]:
                            filename = fname
                            break
                
                # Extract size
                size = None
                size_match = re.search(r'"size":(\d+)', text)
                if size_match:
                    size = int(size_match.group(1))
                
                if download_url:
                    return download_url, sanitize_filename(filename), size
                
                return url, sanitize_filename(filename), size
        
        except Exception as e:
            logger.error(f"Terabox info error: {e}")
            return url, "terabox_file", None
    
    async def get_terabox_folder_files(self, url: str) -> List[Dict]:
        """Get list of files from Terabox folder"""
        files = []
        try:
            session = await self.get_session()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.terabox.com/',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
                
                # Try to extract file list from JSON in page
                list_match = re.search(r'"list":\s*(\[.*?\])', text, re.DOTALL)
                if list_match:
                    try:
                        file_list = json.loads(list_match.group(1))
                        for item in file_list:
                            if item.get('isdir') == 0:  # Is a file, not directory
                                files.append({
                                    'filename': item.get('server_filename', 'unknown'),
                                    'size': item.get('size', 0),
                                    'dlink': item.get('dlink', ''),
                                    'path': item.get('path', '')
                                })
                    except json.JSONDecodeError:
                        pass
        
        except Exception as e:
            logger.error(f"Terabox folder error: {e}")
        
        return files
    
    # ============ DOWNLOAD FILE ============
    async def download_file(
        self,
        url: str,
        download_path: str,
        progress_message,
        filename: str = "downloading",
        headers: dict = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download file with progress updates"""
        try:
            session = await self.get_session()
            
            request_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
            }
            
            if headers:
                request_headers.update(headers)
            
            async with session.get(url, headers=request_headers, allow_redirects=True) as resp:
                if resp.status not in [200, 206]:
                    return False, None, f"HTTP Error: {resp.status}"
                
                total_size = int(resp.headers.get('Content-Length', 0))
                
                # Get filename from headers
                cd = resp.headers.get('Content-Disposition', '')
                if 'filename=' in cd:
                    matches = re.findall(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd)
                    if matches:
                        filename = sanitize_filename(unquote(matches[0]))
                
                # Get from URL if still default
                if filename == "downloading":
                    url_path = urlparse(str(resp.url)).path
                    if url_path:
                        url_filename = url_path.split('/')[-1]
                        if url_filename and '.' in url_filename:
                            filename = sanitize_filename(unquote(url_filename))
                
                file_path = os.path.join(download_path, filename)
                
                # Ensure unique filename
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
    
    # ============ MAIN DOWNLOAD METHODS ============
    async def download_gdrive(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Google Drive"""
        try:
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
    
    async def download_terabox(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Terabox"""
        try:
            # Check if it's a folder
            if is_terabox_folder(url):
                return await self.download_terabox_folder(url, download_path, progress_message)
            
            download_url, filename, size = await self.get_terabox_info(url)
            
            if not download_url:
                return False, None, "Could not get download URL"
            
            headers = {'Referer': 'https://www.terabox.com/'}
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            return await self.download_file(
                download_url, download_path, progress_message,
                filename or "terabox_file", headers
            )
        
        except Exception as e:
            logger.error(f"Terabox download error: {e}")
            return False, None, str(e)
    
    async def download_terabox_folder(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download all files from Terabox folder and zip them"""
        try:
            import shutil
            
            files = await self.get_terabox_folder_files(url)
            
            if not files:
                # Try single file download as fallback
                return await self.download_terabox(url.replace('filelist', 's'), download_path, progress_message)
            
            # Create temp folder for downloads
            folder_name = f"terabox_folder_{int(time.time())}"
            folder_path = os.path.join(download_path, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            
            downloaded_files = []
            
            for i, file_info in enumerate(files, 1):
                try:
                    await progress_message.edit_text(
                        f"📥 **Downloading Folder**\n\n"
                        f"📊 File: {i}/{len(files)}\n"
                        f"📁 `{file_info['filename']}`"
                    )
                    
                    if file_info.get('dlink'):
                        headers = {'Referer': 'https://www.terabox.com/'}
                        if Config.TERABOX_COOKIE:
                            headers['Cookie'] = Config.TERABOX_COOKIE
                        
                        success, file_path, _ = await self.download_file(
                            file_info['dlink'],
                            folder_path,
                            None,  # No progress for individual files
                            file_info['filename'],
                            headers
                        )
                        
                        if success:
                            downloaded_files.append(file_path)
                
                except Exception as e:
                    logger.error(f"Error downloading file from folder: {e}")
            
            if not downloaded_files:
                shutil.rmtree(folder_path, ignore_errors=True)
                return False, None, "No files downloaded from folder"
            
            # Zip the folder
            zip_path = os.path.join(download_path, f"{folder_name}.zip")
            shutil.make_archive(zip_path.replace('.zip', ''), 'zip', folder_path)
            
            # Cleanup folder
            shutil.rmtree(folder_path, ignore_errors=True)
            
            return True, zip_path, None
        
        except Exception as e:
            logger.error(f"Terabox folder download error: {e}")
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
