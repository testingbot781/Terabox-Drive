import os
import re
import time
import json
import asyncio
import logging
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
        
        self.TERABOX_API_BASES = [
            "https://www.terabox.com",
            "https://www.1024tera.com",
            "https://teraboxapp.com",
            "https://www.nephobox.com",
        ]
    
    def extract_terabox_surl(self, url: str) -> Optional[str]:
        """Extract surl from Terabox URL"""
        patterns = [
            r'[?&]surl=([a-zA-Z0-9_-]+)',
            r'/s/1?([a-zA-Z0-9_-]+)',
            r'tbx\.to/([a-zA-Z0-9_-]+)',
            r'terabox\.link/([a-zA-Z0-9_-]+)',
            r'/sharing/(?:link|video)\?surl=([a-zA-Z0-9_-]+)',
            r'/wap/share/filelist\?surl=([a-zA-Z0-9_-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def normalize_terabox_url(self, url: str) -> str:
        """Normalize Terabox URL"""
        surl = self.extract_terabox_surl(url)
        if surl:
            clean_surl = surl.lstrip('1') if len(surl) > 20 else surl
            return f"https://www.terabox.com/s/1{clean_surl}"
        return url
    
    def get_extension_from_content_type(self, content_type: str) -> str:
        """Get extension from content-type"""
        ct_map = {
            'video/mp4': '.mp4',
            'video/x-matroska': '.mkv',
            'video/webm': '.webm',
            'video/avi': '.avi',
            'video/quicktime': '.mov',
            'video/x-msvideo': '.avi',
            'video/x-flv': '.flv',
            'video/3gpp': '.3gp',
            'audio/mpeg': '.mp3',
            'audio/mp3': '.mp3',
            'audio/wav': '.wav',
            'audio/x-wav': '.wav',
            'audio/flac': '.flac',
            'audio/aac': '.aac',
            'audio/ogg': '.ogg',
            'audio/mp4': '.m4a',
            'audio/x-m4a': '.m4a',
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/bmp': '.bmp',
            'application/pdf': '.pdf',
            'application/zip': '.zip',
            'application/x-zip-compressed': '.zip',
            'application/x-rar-compressed': '.rar',
            'application/x-7z-compressed': '.7z',
            'application/vnd.android.package-archive': '.apk',
            'application/octet-stream': '',  # Unknown - don't add extension
            'text/html': '.html',  # This indicates error page!
        }
        ct = content_type.split(';')[0].strip().lower()
        return ct_map.get(ct, '')
    
    def detect_file_type_from_bytes(self, file_path: str) -> Optional[str]:
        """Detect actual file type from magic bytes"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(32)
            
            # Video signatures
            if header[:4] == b'\x00\x00\x00\x1c' or header[:4] == b'\x00\x00\x00\x20':
                if b'ftyp' in header[:12]:
                    return '.mp4'
            if header[:4] == b'\x1a\x45\xdf\xa3':
                return '.mkv'
            if header[:4] == b'RIFF' and header[8:12] == b'AVI ':
                return '.avi'
            if header[:4] == b'\x1a\x45\xdf\xa3':
                return '.webm'
            if header[:3] == b'FLV':
                return '.flv'
            
            # Audio signatures
            if header[:3] == b'ID3' or header[:2] == b'\xff\xfb' or header[:2] == b'\xff\xfa':
                return '.mp3'
            if header[:4] == b'fLaC':
                return '.flac'
            if header[:4] == b'RIFF' and header[8:12] == b'WAVE':
                return '.wav'
            if header[:4] == b'OggS':
                return '.ogg'
            
            # Image signatures
            if header[:2] == b'\xff\xd8':
                return '.jpg'
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                return '.png'
            if header[:6] in [b'GIF87a', b'GIF89a']:
                return '.gif'
            if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                return '.webp'
            if header[:2] == b'BM':
                return '.bmp'
            
            # Document signatures
            if header[:4] == b'%PDF':
                return '.pdf'
            if header[:4] == b'PK\x03\x04':
                # Could be zip, apk, docx, etc.
                return '.zip'
            if header[:6] == b'Rar!\x1a\x07':
                return '.rar'
            
            # HTML (error page)
            if b'<!DOCTYPE' in header or b'<html' in header.lower() or b'<HTML' in header:
                return '.html'
            
            return None
        except:
            return None
    
    def validate_download(self, file_path: str, expected_min_size: int = 10000) -> Tuple[bool, str]:
        """Validate downloaded file is not an error page"""
        try:
            if not os.path.exists(file_path):
                return False, "File does not exist"
            
            file_size = os.path.getsize(file_path)
            
            # Very small files are likely error pages
            if file_size < 1000:
                return False, "File too small - likely error page"
            
            # Detect actual type
            detected_ext = self.detect_file_type_from_bytes(file_path)
            
            if detected_ext == '.html':
                return False, "Downloaded HTML error page instead of file"
            
            return True, "OK"
        except Exception as e:
            return False, str(e)

    def download_file_sync(
        self,
        url: str,
        download_path: str,
        filename: str = "downloading",
        headers: dict = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download file - preserves original extension"""
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
            
            # Check if we got HTML (error page)
            if 'text/html' in content_type.lower():
                logger.error("Got HTML response - file not available")
                return False, None, "File not available or requires login"
            
            # Get filename from Content-Disposition header
            cd = response.headers.get('Content-Disposition', '')
            if 'filename=' in cd:
                matches = re.findall(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd)
                if matches:
                    filename = sanitize_filename(unquote(matches[0]))
            
            # If still no extension, get from content-type
            name, ext = os.path.splitext(filename)
            if not ext or ext == '.':
                ct_ext = self.get_extension_from_content_type(content_type)
                if ct_ext and ct_ext != '.html':
                    filename = f"{name}{ct_ext}"
            
            # DON'T force any extension - keep original or detected
            
            file_path = os.path.join(download_path, filename)
            
            # Unique filename
            base, ext = os.path.splitext(file_path)
            counter = 1
            while os.path.exists(file_path):
                file_path = f"{base}_{counter}{ext}"
                counter += 1
            
            logger.info(f"📥 Saving: {file_path} (Expected: {total_size} bytes)")
            
            downloaded = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            # Validate the download
            is_valid, error_msg = self.validate_download(file_path)
            
            if not is_valid:
                # Delete invalid file
                try:
                    os.remove(file_path)
                except:
                    pass
                return False, None, error_msg
            
            # Fix extension based on actual content
            detected_ext = self.detect_file_type_from_bytes(file_path)
            if detected_ext:
                current_ext = os.path.splitext(file_path)[1].lower()
                if current_ext != detected_ext and detected_ext != '.html':
                    new_path = os.path.splitext(file_path)[0] + detected_ext
                    os.rename(file_path, new_path)
                    file_path = new_path
                    logger.info(f"📝 Fixed extension: {detected_ext}")
            
            final_size = os.path.getsize(file_path)
            logger.info(f"✅ Downloaded: {file_path} ({final_size} bytes)")
            
            return True, file_path, None
        
        except requests.Timeout:
            return False, None, "Download timeout"
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False, None, str(e)

    # ==================== TERABOX ====================
    
    def get_terabox_share_info(self, surl: str) -> Dict:
        """Get share info from Terabox API"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.terabox.com/',
        }
        
        if Config.TERABOX_COOKIE:
            headers['Cookie'] = Config.TERABOX_COOKIE
        
        for base in self.TERABOX_API_BASES:
            for prefix in ['1', '']:
                try:
                    api_url = f"{base}/api/shorturlinfo?shorturl={prefix}{surl}&root=1"
                    response = requests.get(api_url, headers=headers, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('errno') == 0:
                            logger.info(f"✅ API success: {base}")
                            return data
                except:
                    continue
        
        return {}
    
    def get_terabox_file_list(self, surl: str, shareid: str = '', uk: str = '') -> List[Dict]:
        """Get file list from share"""
        files = []
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
                
                response = requests.get(f"{base}/share/list", headers=headers, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('errno') == 0:
                        for item in data.get('list', []):
                            if item.get('isdir', 0) == 0:
                                fname = item.get('server_filename') or item.get('filename') or 'file'
                                dlink = item.get('dlink', '')
                                
                                files.append({
                                    'filename': sanitize_filename(fname),
                                    'size': item.get('size', 0),
                                    'dlink': dlink,
                                })
                        
                        if files:
                            return files
            except:
                continue
        
        return files
    
    def scrape_terabox_page(self, url: str) -> Tuple[Optional[str], str, List[Dict]]:
        """Scrape Terabox page"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            }
            
            if Config.TERABOX_COOKIE:
                headers['Cookie'] = Config.TERABOX_COOKIE
            
            normalized_url = self.normalize_terabox_url(url)
            response = requests.get(normalized_url, headers=headers, timeout=30, allow_redirects=True)
            text = response.text
            
            # Extract dlink
            download_url = None
            for pattern in [r'"dlink"\s*:\s*"([^"]+)"', r'"downloadLink"\s*:\s*"([^"]+)"']:
                match = re.search(pattern, text)
                if match:
                    download_url = match.group(1).replace('\\/', '/').replace('\\u0026', '&')
                    if download_url.startswith('http'):
                        break
                    download_url = None
            
            # Extract filename (keep original extension!)
            filename = "terabox_file"
            for pattern in [r'"server_filename"\s*:\s*"([^"]+)"', r'"filename"\s*:\s*"([^"]+)"']:
                match = re.search(pattern, text)
                if match:
                    fname = match.group(1).strip()
                    if fname and fname.lower() not in ["terabox", "1024tera", "", "share"]:
                        filename = fname
                        break
            
            # Extract file list
            files = []
            list_match = re.search(r'"list"\s*:\s*(\[[\s\S]*?\])\s*[,}]', text)
            if list_match:
                try:
                    file_list = json.loads(list_match.group(1))
                    for item in file_list:
                        if item.get('isdir', 0) == 0:
                            fname = item.get('server_filename') or item.get('filename') or 'file'
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
            
            return download_url, sanitize_filename(filename), files
        
        except Exception as e:
            logger.error(f"Scrape error: {e}")
            return None, "terabox_file", []

    async def download_terabox(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Terabox"""
        try:
            url_lower = url.lower()
            is_folder = 'filelist' in url_lower or ('path=' in url_lower and 'path=%2f' not in url_lower)
            
            if is_folder:
                logger.info("📁 Terabox Folder")
                return True, "TERABOX_FOLDER:" + url, None
            
            if progress_message:
                try:
                    await progress_message.edit_text("🔍 **Fetching Terabox info...**")
                except:
                    pass
            
            surl = self.extract_terabox_surl(url)
            if not surl:
                return False, None, "Could not extract share code"
            
            logger.info(f"📎 surl: {surl}")
            
            # Try API
            download_url = None
            filename = "terabox_file"
            
            share_info = self.get_terabox_share_info(surl)
            
            if share_info and share_info.get('errno') == 0:
                file_list = share_info.get('list', [])
                if file_list:
                    first_file = file_list[0]
                    filename = first_file.get('server_filename') or first_file.get('filename') or 'terabox_file'
                    download_url = first_file.get('dlink', '')
                    filename = sanitize_filename(filename)
            
            # Fallback scrape
            if not download_url:
                download_url, filename, files = self.scrape_terabox_page(url)
                if files and not download_url:
                    download_url = files[0].get('dlink', '')
                    filename = files[0].get('filename', filename)
            
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
            
            if download_url and download_url.startswith('http'):
                success, file_path, error = await loop.run_in_executor(
                    None, self.download_file_sync, download_url, download_path, filename, headers
                )
            else:
                normalized = self.normalize_terabox_url(url)
                success, file_path, error = await loop.run_in_executor(
                    None, self.download_file_sync, normalized, download_path, filename, headers
                )
            
            return success, file_path, error
        
        except Exception as e:
            logger.error(f"Terabox error: {e}")
            return False, None, str(e)
    
    async def get_terabox_folder_files(self, url: str) -> List[Dict]:
        """Get folder files"""
        surl = self.extract_terabox_surl(url)
        if not surl:
            return []
        
        share_info = self.get_terabox_share_info(surl)
        
        if share_info and share_info.get('errno') == 0:
            shareid = str(share_info.get('shareid', ''))
            uk = str(share_info.get('uk', ''))
            files = self.get_terabox_file_list(surl, shareid, uk)
            if files:
                return files
        
        _, _, files = self.scrape_terabox_page(url)
        return files
    
    async def download_terabox_single_file(self, file_info: Dict, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download single file from folder"""
        dlink = file_info.get('dlink', '')
        filename = file_info.get('filename', 'file')
        
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
                await progress_message.edit_text(f"📥 **Downloading**\n\n`{filename}`")
            except:
                pass
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.download_file_sync, dlink, download_path, filename, headers
        )

    # ==================== GOOGLE DRIVE ====================
    
    async def download_gdrive(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from Google Drive"""
        try:
            if 'drive.usercontent.google.com' in url or 'storage.googleapis.com' in url:
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
            return False, None, str(e)

    async def download_direct(self, url: str, download_path: str, progress_message) -> Tuple[bool, Optional[str], Optional[str]]:
        """Download from direct link"""
        try:
            filename = urlparse(url).path.split('/')[-1]
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
            return False, None, str(e)
