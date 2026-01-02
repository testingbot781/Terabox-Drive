import os
import re
import time
import json
import aiohttp
import asyncio
import logging
import aiofiles
import requests
from typing import Optional, Tuple, List, Dict
from urllib.parse import unquote, urlparse
from config import Config
from utils.progress import Progress
from utils.helpers import sanitize_filename, extract_gdrive_id

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self):
        self.progress = Progress()
        self.chunk_size = Config.CHUNK_SIZE
    
    def get_extension_from_content_type(self, content_type: str) -> str:
        """Get file extension from content-type"""
        content_type_map = {
            'video/mp4': '.mp4',
            'video/x-matroska': '.mkv',
            'video/webm': '.webm',
            'video/avi': '.avi',
            'video/x-msvideo': '.avi',
            'video/quicktime': '.mov',
            'audio/mpeg': '.mp3',
            'audio/mp3': '.mp3',
            'audio/wav': '.wav',
            'audio/flac': '.flac',
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'application/pdf': '.pdf',
            'application/zip': '.zip',
            'application/vnd.android.package-archive': '.apk',
        }
        ct = content_type.split(';')[0].strip().lower()
        return content_type_map.get(ct, '')
    
    def ensure_extension(self, filename: str, content_type: str = '', url: str = '') -> str:
        """Ensure filename has proper extension"""
        if not filename:
            filename = "downloaded_file"
        
        name, ext = os.path.splitext(filename)
        
        if ext and 2 <= len(ext) <= 5:
            return filename
        
        if content_type:
            ct_ext = self.get_extension_from_content_type(content_type)
            if ct_ext:
                return f"{name}{ct_ext}"
        
        if url:
            url_path = urlparse(url).path
            _, url_ext = os.path.splitext(url_path)
            if url_ext and 2 <= len(url_ext) <= 5:
                return f"{name}{url_ext}"
        
        if content_type and 'video' in content_type.lower():
            return f"{name}.mp4"
        
        return filename

    # ==================== SYNC DOWNLOAD (For Terabox) ====================
    
    def download_file_sync(
        self,
        url: str,
        download_path: str,
        filename: str = "downloading",
        headers: dict = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Synchronous download using requests (no session issues)"""
        try:
            request_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
            }
            
            if headers:
                request_headers.update(headers)
            
            logger.info(f"📥 Starting sync download: {filename}")
            
            response = requests.get(url, headers=request_headers, stream=True, timeout=3600, allow_redirects=True)
            
            if response.status_code not in [200, 206]:
                return False, None, f"HTTP Error: {response.status_code}"
            
            total_size = int(response.headers.get('Content-Length', 0))
            content_type = response.headers.get('Content-Type', '')
            
            # Get filename from headers
            cd = response.headers.get('Content-Disposition', '')
            if 'filename=' in cd:
                matches = re.findall(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd)
                if matches:
                    filename = sanitize_filename(unquote(matches[0]))
            
            # Ensure extension
            filename = self.ensure_extension(filename, content_type, url)
            
            file_path = os.path.join(download_path, filename)
            
            # Unique filename
            base, ext = os.path.splitext(file_path)
            counter = 1
            while os.path.exists(file_path):
                file_path = f"{base}_{counter}{ext}"
                counter += 1
            
            logger.info(f"📥 Downloading: {filename} ({total_size} bytes)")
            
            # Download
            downloaded = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                logger.info(f"✅ Downloaded: {file_path}")
                return True, file_path, None
            else:
                return False, None, "Download failed - empty file"
        
        except requests.Timeout:
            return False, None, "Download timeout"
        except Exception as e:
            logger.error(f"Sync download error: {e}")
            return False, None, str(e)

    # ==================== ASYNC DOWNLOAD (For GDrive & Direct) ====================
    
    async def download_file_async(
        self,
        url: str,
        download_path: str,
        progress_message,
        filename: str = "downloading",
        headers: dict = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Async download with progress"""
        connector = None
        session = None
        
        try:
            timeout = aiohttp.ClientTimeout(total=7200, connect=60)
            connector = aiohttp.TCPConnector(limit=10, force_close=True)
            
            session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector
            )
            
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
                content_type = resp.headers.get('Content-Type', '')
                
                cd = resp.headers.get('Content-Disposition', '')
                if 'filename=' in cd:
                    matches = re.findall(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd)
                    if matches:
                        filename = sanitize_filename(unquote(matches[0]))
                
                if filename in ["downloading", "downloaded_file"]:
                    url_path = urlparse(str(resp.url)).path
                    if url_path:
                        url_filename = url_path.split('/')[-1]
                        if url_filename:
                            filename = sanitize_filename(unquote(url_filename))
                
                filename = self.ensure_extension(filename, content_type, str(resp.url))
                
                file_path = os.path.join(download_path, filename)
                
                base, ext = os.path.splitext(file_path)
                counter = 1
                while os.path.exists(file_path):
                    file_path = f"{base}_{counter}{ext}"
                    counter += 1
                
                logger.info(f"📥 Downloading: {filename} ({total_size} bytes)")
                
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
            logger.error(f"Async download error: {e}")
            return False, None, str(e)
        finally:
            if session and not session.closed:
                await session.close()
            if connector and not connector.closed:
                await connector.close()
            # Give time for cleanup
            await asyncio.sleep(0.25)

    # ==================== GOOGLE DRIVE ====================
    
    async def get_gdrive_info(self, file_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Get Google Drive download info"""
        connector = None
        session = None
        
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            connector = aiohttp.TCPConnector(force_close=True)
            session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            
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
                    return redirect_url, sanitize_filename(filename)
            
            async with session.get(download_url) as resp:
                text = await resp.text()
                
                confirm_match = re.search(r'confirm=([0-9A-Za-z_-]+)', text)
                
                if confirm_match:
                    confirm_token = confirm_match.group(1)
                    download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm_token}"
                
                filename_match = re.search(r'"title":"([^"]+)"', text)
                filename = filename_match.group(1) if filename_match else "gdrive_file"
                
                return download_url, sanitize_filename(filename)
        
        except Exception as e:
            logger.error(f"GDrive info error: {e}")
            return None, None
        finally:
            if session and not session.closed:
                await session.close()
            if connector and not connector.closed:
                await connector.close()
            await asyncio.sleep(0.25)
    
    async def download_gdrive(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Google Drive"""
        try:
            # Direct links
            if 'drive.usercontent.google.com' in url or 'storage.googleapis.com' in url:
                logger.info("📁 Google Direct Link")
                return await self.download_file_async(url, download_path, progress_message, "google_file", {})
            
            file_id = extract_gdrive_id(url)
            if not file_id:
                return False, None, "Invalid Google Drive URL"
            
            download_url, filename = await self.get_gdrive_info(file_id)
            
            if not download_url:
                return False, None, "Could not get download URL"
            
            headers = {'Cookie': 'download_warning_token=1'}
            
            return await self.download_file_async(
                download_url, download_path, progress_message,
                filename or "gdrive_file", headers
            )
        
        except Exception as e:
            logger.error(f"GDrive error: {e}")
            return False, None, str(e)

    # ==================== TERABOX (Using Sync Requests) ====================
    
    def get_terabox_info_sync(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Get Terabox info using sync requests"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': 'https://www.terabox.com/',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            logger.info(f"🔍 Fetching Terabox: {url[:60]}...")
            
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            
            if response.status_code != 200:
                logger.error(f"Terabox status: {response.status_code}")
                return None, "terabox_file.mp4"
            
            text = response.text
            
            # Find download link
            download_url = None
            
            patterns = [
                r'"dlink"\s*:\s*"([^"]+)"',
                r'"downloadLink"\s*:\s*"([^"]+)"',
                r'href="(https://[^"]*d\.terabox[^"]*)"',
                r'href="(https://[^"]*terabox[^"]*download[^"]*)"',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    download_url = match.group(1)
                    download_url = download_url.replace('\\/', '/').replace('\\u0026', '&')
                    if download_url.startswith('http'):
                        logger.info(f"✅ Found dlink")
                        break
                    download_url = None
            
            # Find filename
            filename = "terabox_file"
            
            fname_patterns = [
                r'"server_filename"\s*:\s*"([^"]+)"',
                r'"filename"\s*:\s*"([^"]+)"',
                r'"name"\s*:\s*"([^"]+)"',
            ]
            
            for pattern in fname_patterns:
                match = re.search(pattern, text)
                if match:
                    fname = match.group(1).strip()
                    if fname and fname not in ["TeraBox", "1024Tera", "", "share"]:
                        filename = fname
                        break
            
            if '.' not in filename:
                filename = f"{filename}.mp4"
            
            return download_url, sanitize_filename(filename)
        
        except Exception as e:
            logger.error(f"Terabox info error: {e}")
            return None, "terabox_file.mp4"
    
    def get_terabox_folder_files_sync(self, url: str) -> List[Dict]:
        """Get Terabox folder files using sync"""
        files = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.terabox.com/',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            logger.info(f"📁 Fetching folder: {url[:60]}...")
            
            response = requests.get(url, headers=headers, timeout=30)
            text = response.text
            
            # Find file list
            list_match = re.search(r'"list"\s*:\s*(\[[\s\S]*?\])\s*[,}]', text)
            
            if list_match:
                try:
                    json_str = list_match.group(1)
                    file_list = json.loads(json_str)
                    
                    for item in file_list:
                        is_dir = item.get('isdir', 0) or item.get('is_dir', 0)
                        
                        if is_dir == 0:
                            fname = item.get('server_filename') or item.get('filename') or item.get('name') or 'file'
                            
                            if '.' not in fname:
                                fname = f"{fname}.mp4"
                            
                            dlink = item.get('dlink', '')
                            if dlink:
                                dlink = dlink.replace('\\/', '/').replace('\\u0026', '&')
                            
                            files.append({
                                'filename': sanitize_filename(fname),
                                'size': item.get('size', 0),
                                'dlink': dlink
                            })
                except json.JSONDecodeError as e:
                    logger.error(f"JSON error: {e}")
            
            logger.info(f"📁 Found {len(files)} files")
        
        except Exception as e:
            logger.error(f"Folder error: {e}")
        
        return files
    
    async def download_terabox(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Terabox"""
        try:
            # Check if folder
            is_folder = 'filelist' in url.lower() and 'path=' in url.lower()
            
            if is_folder:
                logger.info("📁 Terabox Folder detected")
                return True, "TERABOX_FOLDER:" + url, None
            
            # Update progress
            if progress_message:
                try:
                    await progress_message.edit_text("🔍 **Fetching Terabox info...**")
                except:
                    pass
            
            # Get info (sync to avoid session issues)
            loop = asyncio.get_event_loop()
            download_url, filename = await loop.run_in_executor(
                None, self.get_terabox_info_sync, url
            )
            
            headers = {
                'Referer': 'https://www.terabox.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            # Update progress
            if progress_message:
                try:
                    await progress_message.edit_text(f"📥 **Downloading**\n\n`{filename}`\n\n⏳ Please wait...")
                except:
                    pass
            
            if download_url and download_url.startswith('http'):
                logger.info(f"📥 Using dlink: {filename}")
                # Use sync download to avoid session issues
                success, file_path, error = await loop.run_in_executor(
                    None, self.download_file_sync, download_url, download_path, filename, headers
                )
                return success, file_path, error
            else:
                logger.info(f"📥 Trying direct URL: {filename}")
                success, file_path, error = await loop.run_in_executor(
                    None, self.download_file_sync, url, download_path, filename, headers
                )
                return success, file_path, error
        
        except Exception as e:
            logger.error(f"Terabox error: {e}")
            return False, None, str(e)
    
    async def download_terabox_single_file(self, file_info: Dict, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download single file from folder"""
        try:
            dlink = file_info.get('dlink', '')
            filename = file_info.get('filename', 'terabox_file.mp4')
            
            if not dlink or not dlink.startswith('http'):
                return False, None, "No download link"
            
            headers = {
                'Referer': 'https://www.terabox.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            if progress_message:
                try:
                    await progress_message.edit_text(f"📥 **Downloading**\n\n`{filename}`\n\n⏳ Please wait...")
                except:
                    pass
            
            loop = asyncio.get_event_loop()
            success, file_path, error = await loop.run_in_executor(
                None, self.download_file_sync, dlink, download_path, filename, headers
            )
            
            return success, file_path, error
        
        except Exception as e:
            logger.error(f"Single file error: {e}")
            return False, None, str(e)
    
    async def get_terabox_folder_files(self, url: str) -> List[Dict]:
        """Get folder files async wrapper"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_terabox_folder_files_sync, url)

    # ==================== DIRECT DOWNLOAD ====================
    
    async def download_direct(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from direct link"""
        try:
            parsed = urlparse(url)
            filename = parsed.path.split('/')[-1]
            filename = unquote(filename) if filename else "downloaded_file"
            
            return await self.download_file_async(
                url, download_path, progress_message,
                sanitize_filename(filename)
            )
        
        except Exception as e:
            logger.error(f"Direct error: {e}")
            return False, None, str(e)
