import os
import re
import time
import json
import asyncio
import logging
import requests
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
        
        # All Terabox API base URLs to try
        self.TERABOX_API_BASES = [
            "https://www.terabox.com",
            "https://www.1024tera.com",
            "https://teraboxapp.com",
            "https://www.nephobox.com",
        ]
    
    # ==================== TERABOX URL NORMALIZATION ====================
    
    def extract_terabox_surl(self, url: str) -> Optional[str]:
        """Extract surl/shortcode from any Terabox URL format"""
        
        # Pattern 1: surl parameter in query string
        # Example: ?surl=XXXXXXXX or &surl=XXXXXXXX
        match = re.search(r'[?&]surl=([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        
        # Pattern 2: /s/XXXXXXXX or /s/1XXXXXXXX format
        # Example: terabox.com/s/1Rp_6exJ3GHUIPzhnX5pHSA
        match = re.search(r'/s/1?([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        
        # Pattern 3: Short domain like tbx.to/XXXXXXXX
        match = re.search(r'tbx\.to/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        
        # Pattern 4: terabox.link/XXXXXXXX
        match = re.search(r'terabox\.link/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        
        # Pattern 5: /sharing/link?surl= or /sharing/video?surl=
        match = re.search(r'/sharing/(?:link|video)\?surl=([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        
        # Pattern 6: /wap/share/filelist?surl=
        match = re.search(r'/wap/share/filelist\?surl=([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        
        # Pattern 7: Any URL with a long alphanumeric code at the end
        match = re.search(r'/([a-zA-Z0-9_-]{15,})(?:\?|$|&)', url)
        if match:
            return match.group(1)
        
        logger.warning(f"Could not extract surl from: {url}")
        return None
    
    def normalize_terabox_url(self, url: str) -> str:
        """Convert any Terabox URL to standard format"""
        surl = self.extract_terabox_surl(url)
        
        if surl:
            # Remove leading '1' if present (some URLs have it, some don't)
            clean_surl = surl.lstrip('1') if len(surl) > 20 else surl
            
            # Return standard format
            return f"https://www.terabox.com/s/1{clean_surl}"
        
        return url
    
    def get_extension_from_content_type(self, content_type: str) -> str:
        """Get file extension from content-type"""
        content_type_map = {
            'video/mp4': '.mp4',
            'video/x-matroska': '.mkv',
            'video/webm': '.webm',
            'video/avi': '.avi',
            'video/quicktime': '.mov',
            'audio/mpeg': '.mp3',
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

    # ==================== SYNC DOWNLOAD ====================
    
    def download_file_sync(
        self,
        url: str,
        download_path: str,
        filename: str = "downloading",
        headers: dict = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download file using requests (sync)"""
        try:
            request_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive',
            }
            
            if headers:
                request_headers.update(headers)
            
            logger.info(f"📥 Downloading: {filename}")
            
            response = requests.get(
                url,
                headers=request_headers,
                stream=True,
                timeout=3600,
                allow_redirects=True
            )
            
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
            
            filename = self.ensure_extension(filename, content_type, url)
            
            file_path = os.path.join(download_path, filename)
            
            # Unique filename
            base, ext = os.path.splitext(file_path)
            counter = 1
            while os.path.exists(file_path):
                file_path = f"{base}_{counter}{ext}"
                counter += 1
            
            logger.info(f"📥 Saving: {file_path} ({total_size} bytes)")
            
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
                return False, None, "Empty file"
        
        except requests.Timeout:
            return False, None, "Download timeout"
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False, None, str(e)

    # ==================== TERABOX API ====================
    
    def get_terabox_share_info(self, surl: str) -> Dict:
        """Get share info from Terabox API (try multiple endpoints)"""
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.terabox.com/',
        }
        
        if Config.TERABOX_COOKIE:
            headers['Cookie'] = Config.TERABOX_COOKIE
        
        # Try different API endpoints
        api_urls = []
        
        for base in self.TERABOX_API_BASES:
            # With leading 1
            api_urls.append(f"{base}/api/shorturlinfo?shorturl=1{surl}&root=1")
            # Without leading 1
            api_urls.append(f"{base}/api/shorturlinfo?shorturl={surl}&root=1")
        
        for api_url in api_urls:
            try:
                logger.info(f"🔍 Trying API: {api_url[:60]}...")
                
                response = requests.get(api_url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('errno') == 0:
                        logger.info(f"✅ API success!")
                        return data
                    else:
                        logger.debug(f"API errno: {data.get('errno')}")
            except Exception as e:
                logger.debug(f"API error: {e}")
                continue
        
        logger.warning("All API endpoints failed")
        return {}
    
    def get_terabox_file_list(self, surl: str, shareid: str = '', uk: str = '') -> List[Dict]:
        """Get file list from share"""
        files = []
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.terabox.com/',
        }
        
        if Config.TERABOX_COOKIE:
            headers['Cookie'] = Config.TERABOX_COOKIE
        
        for base in self.TERABOX_API_BASES:
            try:
                params = {
                    'shorturl': f"1{surl}",
                    'dir': '/',
                    'root': '1',
                    'page': '1',
                    'num': '100',
                }
                
                if shareid:
                    params['shareid'] = shareid
                if uk:
                    params['uk'] = uk
                
                list_url = f"{base}/share/list"
                
                response = requests.get(list_url, headers=headers, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('errno') == 0:
                        file_list = data.get('list', [])
                        
                        for item in file_list:
                            is_dir = item.get('isdir', 0)
                            
                            if is_dir == 0:
                                fname = item.get('server_filename') or item.get('filename') or 'file'
                                
                                if '.' not in fname:
                                    fname = f"{fname}.mp4"
                                
                                dlink = item.get('dlink', '')
                                
                                files.append({
                                    'filename': sanitize_filename(fname),
                                    'size': item.get('size', 0),
                                    'dlink': dlink,
                                    'fs_id': item.get('fs_id', ''),
                                })
                        
                        if files:
                            logger.info(f"✅ Got {len(files)} files from API")
                            return files
            except Exception as e:
                logger.debug(f"List API error: {e}")
                continue
        
        return files
    
    def scrape_terabox_page(self, url: str) -> Tuple[Optional[str], str, List[Dict]]:
        """Scrape Terabox page for download info"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            # Normalize URL first
            normalized_url = self.normalize_terabox_url(url)
            logger.info(f"🔍 Scraping: {normalized_url[:60]}...")
            
            response = requests.get(normalized_url, headers=headers, timeout=30, allow_redirects=True)
            text = response.text
            
            # Extract download link
            download_url = None
            dlink_patterns = [
                r'"dlink"\s*:\s*"([^"]+)"',
                r'"downloadLink"\s*:\s*"([^"]+)"',
                r'href="(https://[^"]*d\.terabox[^"]*)"',
                r'href="(https://[^"]*download[^"]*\.terabox[^"]*)"',
                r'"link"\s*:\s*"([^"]*download[^"]*)"',
            ]
            
            for pattern in dlink_patterns:
                match = re.search(pattern, text)
                if match:
                    download_url = match.group(1)
                    download_url = download_url.replace('\\/', '/').replace('\\u0026', '&')
                    if 'http' in download_url:
                        logger.info(f"✅ Found dlink")
                        break
                    download_url = None
            
            # Extract filename
            filename = "terabox_file"
            fname_patterns = [
                r'"server_filename"\s*:\s*"([^"]+)"',
                r'"filename"\s*:\s*"([^"]+)"',
                r'"name"\s*:\s*"([^"]+)"',
                r'"title"\s*:\s*"([^"]+)"',
            ]
            
            for pattern in fname_patterns:
                match = re.search(pattern, text)
                if match:
                    fname = match.group(1).strip()
                    if fname and fname.lower() not in ["terabox", "1024tera", "", "share", "分享", "nephobox"]:
                        filename = fname
                        break
            
            if '.' not in filename:
                filename = f"{filename}.mp4"
            
            # Extract file list
            files = []
            list_match = re.search(r'"list"\s*:\s*(\[[\s\S]*?\])\s*[,}]', text)
            
            if list_match:
                try:
                    json_str = list_match.group(1)
                    file_list = json.loads(json_str)
                    
                    for item in file_list:
                        is_dir = item.get('isdir', 0)
                        if is_dir == 0:
                            fname = item.get('server_filename') or item.get('filename') or 'file'
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
                except:
                    pass
            
            logger.info(f"📄 Scraped: filename={filename}, dlink={'Yes' if download_url else 'No'}, files={len(files)}")
            
            return download_url, sanitize_filename(filename), files
        
        except Exception as e:
            logger.error(f"Scrape error: {e}")
            return None, "terabox_file.mp4", []

    # ==================== MAIN TERABOX DOWNLOAD ====================
    
    async def download_terabox(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Terabox (any domain)"""
        try:
            # Check if folder
            url_lower = url.lower()
            is_folder = 'filelist' in url_lower or ('path=' in url_lower and 'path=%2f' not in url_lower)
            
            if is_folder:
                logger.info("📁 Terabox Folder detected")
                return True, "TERABOX_FOLDER:" + url, None
            
            # Update progress
            if progress_message:
                try:
                    await progress_message.edit_text("🔍 **Fetching Terabox info...**")
                except:
                    pass
            
            # Extract surl
            surl = self.extract_terabox_surl(url)
            logger.info(f"📎 Extracted surl: {surl}")
            
            if not surl:
                return False, None, "Could not extract share code from URL"
            
            # Try API first
            download_url = None
            filename = "terabox_file.mp4"
            
            share_info = self.get_terabox_share_info(surl)
            
            if share_info and share_info.get('errno') == 0:
                file_list = share_info.get('list', [])
                
                if file_list:
                    first_file = file_list[0]
                    filename = first_file.get('server_filename') or first_file.get('filename') or 'terabox_file'
                    download_url = first_file.get('dlink', '')
                    
                    if '.' not in filename:
                        filename = f"{filename}.mp4"
                    
                    filename = sanitize_filename(filename)
                    logger.info(f"✅ Got from API: {filename}")
            
            # Fallback to scraping
            if not download_url:
                logger.info("📄 Trying scrape method...")
                download_url, filename, files = self.scrape_terabox_page(url)
                
                if files and not download_url:
                    download_url = files[0].get('dlink', '')
                    filename = files[0].get('filename', filename)
            
            # Prepare headers
            headers = {
                'Referer': 'https://www.terabox.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            # Update progress
            if progress_message:
                try:
                    await progress_message.edit_text(
                        f"📥 **Downloading**\n\n"
                        f"`{filename}`\n\n"
                        f"⏳ Please wait..."
                    )
                except:
                    pass
            
            # Download
            loop = asyncio.get_event_loop()
            
            if download_url and download_url.startswith('http'):
                logger.info(f"📥 Using dlink: {filename}")
                success, file_path, error = await loop.run_in_executor(
                    None, self.download_file_sync, download_url, download_path, filename, headers
                )
            else:
                # Try normalized URL as last resort
                normalized = self.normalize_terabox_url(url)
                logger.info(f"📥 Trying normalized URL: {filename}")
                success, file_path, error = await loop.run_in_executor(
                    None, self.download_file_sync, normalized, download_path, filename, headers
                )
            
            return success, file_path, error
        
        except Exception as e:
            logger.error(f"Terabox error: {e}")
            return False, None, str(e)
    
    async def get_terabox_folder_files(self, url: str) -> List[Dict]:
        """Get files from Terabox folder"""
        files = []
        
        try:
            surl = self.extract_terabox_surl(url)
            
            if not surl:
                logger.error("Could not extract surl")
                return files
            
            logger.info(f"📁 Getting folder files: {surl}")
            
            # Try API
            share_info = self.get_terabox_share_info(surl)
            
            if share_info and share_info.get('errno') == 0:
                shareid = str(share_info.get('shareid', ''))
                uk = str(share_info.get('uk', ''))
                
                files = self.get_terabox_file_list(surl, shareid, uk)
                
                if files:
                    return files
            
            # Fallback to scraping
            logger.info("📄 Trying scrape for folder...")
            _, _, files = self.scrape_terabox_page(url)
            
            return files
        
        except Exception as e:
            logger.error(f"Folder files error: {e}")
            return files
    
    async def download_terabox_single_file(self, file_info: Dict, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download single file from folder"""
        try:
            dlink = file_info.get('dlink', '')
            filename = file_info.get('filename', 'terabox_file.mp4')
            
            if not dlink:
                return False, None, "No download link"
            
            headers = {
                'Referer': 'https://www.terabox.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            if progress_message:
                try:
                    await progress_message.edit_text(
                        f"📥 **Downloading**\n\n"
                        f"`{filename}`\n\n"
                        f"⏳ Please wait..."
                    )
                except:
                    pass
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.download_file_sync, dlink, download_path, filename, headers
            )
        
        except Exception as e:
            logger.error(f"Single file error: {e}")
            return False, None, str(e)

    # ==================== GOOGLE DRIVE ====================
    
    async def download_gdrive(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Google Drive"""
        try:
            if 'drive.usercontent.google.com' in url or 'storage.googleapis.com' in url:
                logger.info("📁 Google Direct Link")
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self.download_file_sync, url, download_path, "google_file", {}
                )
            
            file_id = extract_gdrive_id(url)
            if not file_id:
                return False, None, "Invalid Google Drive URL"
            
            download_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm=t"
            
            headers = {'Cookie': 'download_warning_token=1'}
            
            if progress_message:
                try:
                    await progress_message.edit_text("📥 **Downloading from Google Drive...**")
                except:
                    pass
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.download_file_sync, download_url, download_path, "gdrive_file", headers
            )
        
        except Exception as e:
            logger.error(f"GDrive error: {e}")
            return False, None, str(e)

    # ==================== DIRECT DOWNLOAD ====================
    
    async def download_direct(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from direct link"""
        try:
            parsed = urlparse(url)
            filename = parsed.path.split('/')[-1]
            filename = unquote(filename) if filename else "downloaded_file"
            
            if progress_message:
                try:
                    await progress_message.edit_text(f"📥 **Downloading**\n\n`{filename}`")
                except:
                    pass
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.download_file_sync, url, download_path, sanitize_filename(filename), {}
            )
        
        except Exception as e:
            logger.error(f"Direct error: {e}")
            return False, None, str(e)
