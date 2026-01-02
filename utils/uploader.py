import os
import time
import logging
import asyncio
from typing import Optional, Tuple
from pyrogram import Client
from pyrogram.types import Message
from config import Config
from utils.progress import Progress
from utils.helpers import get_file_extension, get_file_type, get_readable_file_size
from utils.thumbnail import ThumbnailGenerator

logger = logging.getLogger(__name__)

class Uploader:
    def __init__(self):
        self.progress = Progress()
        self.thumbnail_gen = ThumbnailGenerator()
    
    async def get_video_info(self, file_path: str) -> Tuple[int, int, int]:
        """Get video duration, width, height using ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,duration',
                '-show_entries', 'format=duration',
                '-of', 'csv=p=0:s=,',
                file_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            output = stdout.decode().strip()
            
            if output:
                parts = output.split(',')
                width = int(float(parts[0])) if len(parts) > 0 and parts[0] else 0
                height = int(float(parts[1])) if len(parts) > 1 and parts[1] else 0
                duration = int(float(parts[2])) if len(parts) > 2 and parts[2] else 0
                return duration, width, height
            
            return 0, 0, 0
        except Exception as e:
            logger.debug(f"Video info error: {e}")
            return 0, 0, 0
    
    async def get_audio_duration(self, file_path: str) -> int:
        """Get audio duration"""
        try:
            from mutagen import File
            audio = File(file_path)
            if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                return int(audio.info.length)
            return 0
        except Exception as e:
            logger.debug(f"Audio duration error: {e}")
            return 0
    
    async def upload_file(
        self,
        client: Client,
        file_path: str,
        chat_id: int,
        progress_message: Message,
        caption: str = None,
        reply_to_message_id: int = None,
        message_thread_id: int = None,
        custom_thumbnail: str = None
    ) -> Tuple[bool, Optional[Message], Optional[str]]:
        """Upload file to Telegram with progress"""
        try:
            if not os.path.exists(file_path):
                return False, None, "File not found"
            
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            extension = get_file_extension(filename)
            file_type = get_file_type(extension)
            
            # Generate caption if not provided
            if caption is None:
                caption = f"📁 **{filename}**\n📊 Size: {get_readable_file_size(file_size)}"
            
            # Generate thumbnail
            thumbnail = custom_thumbnail
            if not thumbnail:
                thumbnail = await self.thumbnail_gen.generate_thumbnail(file_path, file_type)
            
            # Progress callback
            start_time = time.time()
            
            async def progress_callback(current, total):
                try:
                    if self.progress.should_update():
                        elapsed = time.time() - start_time
                        speed = current / elapsed if elapsed > 0 else 0
                        eta = int((total - current) / speed) if speed > 0 else 0
                        
                        text = self.progress.get_upload_progress_text(
                            filename, current, total, speed, eta
                        )
                        await progress_message.edit_text(text)
                except Exception as e:
                    logger.debug(f"Upload progress error: {e}")
            
            # Upload based on file type
            sent_message = None
            
            # Base upload kwargs
            upload_kwargs = {
                'chat_id': chat_id,
                'caption': caption,
                'progress': progress_callback,
            }
            
            if reply_to_message_id:
                upload_kwargs['reply_to_message_id'] = reply_to_message_id
            
            if message_thread_id:
                upload_kwargs['message_thread_id'] = message_thread_id
            
            if file_type == "video":
                # Get video info
                duration, width, height = await self.get_video_info(file_path)
                
                sent_message = await client.send_video(
                    **upload_kwargs,
                    video=file_path,
                    thumb=thumbnail,
                    duration=duration,
                    width=width,
                    height=height,
                    supports_streaming=True
                )
            
            elif file_type == "audio":
                # Get audio duration
                duration = await self.get_audio_duration(file_path)
                
                sent_message = await client.send_audio(
                    **upload_kwargs,
                    audio=file_path,
                    thumb=thumbnail,
                    duration=duration
                )
            
            elif file_type == "image":
                # Send as photo if small enough, else as document
                if file_size < 10 * 1024 * 1024:  # 10 MB
                    sent_message = await client.send_photo(
                        **upload_kwargs,
                        photo=file_path
                    )
                else:
                    sent_message = await client.send_document(
                        **upload_kwargs,
                        document=file_path,
                        thumb=thumbnail
                    )
            
            else:
                # Send as document
                sent_message = await client.send_document(
                    **upload_kwargs,
                    document=file_path,
                    thumb=thumbnail
                )
            
            # Cleanup thumbnail
            if thumbnail and os.path.exists(thumbnail) and thumbnail != custom_thumbnail:
                try:
                    os.remove(thumbnail)
                except:
                    pass
            
            return True, sent_message, None
        
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return False, None, str(e)
    
    async def send_log(
        self,
        client: Client,
        user_id: int,
        username: str,
        url: str,
        filename: str,
        status: str,
        error: str = None
    ):
        """Send log to log channel"""
        try:
            status_emoji = "✅" if status == "success" else "❌"
            
            # Truncate long URLs
            display_url = url[:100] + "..." if len(url) > 100 else url
            
            log_text = f"""
{status_emoji} **File {'Uploaded' if status == 'success' else 'Failed'}**

👤 **User:** @{username or 'None'} (`{user_id}`)
📁 **File:** `{filename}`
🔗 **Link:** `{display_url}`
"""
            
            if error:
                log_text += f"❌ **Error:** `{error}`"
            
            await client.send_message(
                Config.LOG_CHANNEL,
                log_text
            )
        except Exception as e:
            logger.error(f"Log send error: {e}")
