import os
import logging
import asyncio
import aiohttp
from PIL import Image
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)

class ThumbnailGenerator:
    def __init__(self):
        self.default_thumbnail = Config.THUMBNAIL_URL
    
    async def generate_video_thumbnail(self, video_path: str, output_path: str) -> Optional[str]:
        """Generate thumbnail from video using ffmpeg"""
        try:
            # Use ffmpeg to extract frame
            cmd = [
                'ffmpeg', '-i', video_path,
                '-ss', '00:00:01',
                '-vframes', '1',
                '-vf', 'scale=320:320:force_original_aspect_ratio=decrease',
                '-y', output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            
            # Fallback to default thumbnail
            return await self.download_default_thumbnail(output_path)
        except Exception as e:
            logger.error(f"Video thumbnail error: {e}")
            return await self.download_default_thumbnail(output_path)
    
    async def generate_image_thumbnail(self, image_path: str, output_path: str) -> Optional[str]:
        """Generate thumbnail from image"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Resize maintaining aspect ratio
                img.thumbnail((320, 320), Image.Resampling.LANCZOS)
                
                # Save as JPEG
                img.save(output_path, 'JPEG', quality=85)
            
            if os.path.exists(output_path):
                return output_path
            
            return None
        except Exception as e:
            logger.error(f"Image thumbnail error: {e}")
            return None
    
    async def generate_pdf_thumbnail(self, pdf_path: str, output_path: str) -> Optional[str]:
        """Generate thumbnail for PDF - uses default thumbnail"""
        try:
            # Use default thumbnail for PDFs
            if self.default_thumbnail:
                return await self.download_default_thumbnail(output_path)
            return None
        except Exception as e:
            logger.error(f"PDF thumbnail error: {e}")
            return None
    
    async def generate_audio_thumbnail(self, audio_path: str, output_path: str) -> Optional[str]:
        """Extract album art from audio file"""
        try:
            from mutagen import File
            
            audio = File(audio_path)
            
            if audio is None:
                return await self.download_default_thumbnail(output_path)
            
            # Try to get album art
            artwork = None
            
            # Check for pictures attribute (FLAC, OGG, etc.)
            if hasattr(audio, 'pictures') and audio.pictures:
                artwork = audio.pictures[0].data
            
            # Check for tags (MP3 with ID3)
            elif hasattr(audio, 'tags') and audio.tags:
                for key in audio.tags.keys():
                    if 'APIC' in str(key):
                        artwork = audio.tags[key].data
                        break
            
            if artwork:
                with open(output_path, 'wb') as f:
                    f.write(artwork)
                
                # Resize if needed
                try:
                    with Image.open(output_path) as img:
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')
                        img.thumbnail((320, 320), Image.Resampling.LANCZOS)
                        img.save(output_path, 'JPEG', quality=85)
                except:
                    pass
                
                return output_path
            
            # Fallback to default
            return await self.download_default_thumbnail(output_path)
        except Exception as e:
            logger.error(f"Audio thumbnail error: {e}")
            return await self.download_default_thumbnail(output_path)
    
    async def generate_apk_thumbnail(self, apk_path: str, output_path: str) -> Optional[str]:
        """Generate thumbnail for APK - uses default thumbnail"""
        try:
            if self.default_thumbnail:
                return await self.download_default_thumbnail(output_path)
            return None
        except Exception as e:
            logger.error(f"APK thumbnail error: {e}")
            return None
    
    async def download_default_thumbnail(self, output_path: str) -> Optional[str]:
        """Download default thumbnail from URL"""
        try:
            if not self.default_thumbnail:
                return None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.default_thumbnail) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(output_path, 'wb') as f:
                            f.write(content)
                        
                        # Resize to proper thumbnail size
                        try:
                            with Image.open(output_path) as img:
                                if img.mode in ('RGBA', 'P'):
                                    img = img.convert('RGB')
                                img.thumbnail((320, 320), Image.Resampling.LANCZOS)
                                img.save(output_path, 'JPEG', quality=85)
                        except:
                            pass
                        
                        return output_path
            return None
        except Exception as e:
            logger.error(f"Default thumbnail download error: {e}")
            return None
    
    async def generate_thumbnail(self, file_path: str, file_type: str) -> Optional[str]:
        """Generate thumbnail based on file type"""
        try:
            output_path = file_path + "_thumb.jpg"
            
            if file_type == "video":
                return await self.generate_video_thumbnail(file_path, output_path)
            elif file_type == "image":
                return await self.generate_image_thumbnail(file_path, output_path)
            elif file_type == "pdf":
                return await self.generate_pdf_thumbnail(file_path, output_path)
            elif file_type == "audio":
                return await self.generate_audio_thumbnail(file_path, output_path)
            elif file_type == "apk":
                return await self.generate_apk_thumbnail(file_path, output_path)
            else:
                # For other files, use default thumbnail
                if self.default_thumbnail:
                    return await self.download_default_thumbnail(output_path)
                return None
        except Exception as e:
            logger.error(f"Thumbnail generation error: {e}")
            return None
