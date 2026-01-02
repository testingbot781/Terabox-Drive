import os
import time
import logging
import asyncio
import subprocess
from typing import Optional, Tuple
from pyrogram import Client
from pyrogram.types import Message
from config import Config
from utils.progress import Progress
from utils.helpers import get_readable_file_size
from utils.thumbnail import ThumbnailGenerator

logger = logging.getLogger(__name__)

class Uploader:
    def __init__(self):
        self.progress = Progress()
        self.thumbnail_gen = ThumbnailGenerator()
    
    async def get_video_metadata(self, file_path: str) -> Tuple[int, int, int]:
        """Get video duration, width, height using ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            
            if stdout:
                import json
                data = json.loads(stdout.decode())
                
                # Get duration
                duration = 0
                if 'format' in data and 'duration' in data['format']:
                    duration = int(float(data['format']['duration']))
                
                # Get video stream info
                width = 0
                height = 0
                for stream in data.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        width = stream.get('width', 0)
                        height = stream.get('height', 0)
                        if 'duration' in stream and duration == 0:
                            duration = int(float(stream['duration']))
                        break
                
                logger.info(f"📊 Video metadata: {duration}s, {width}x{height}")
                return duration, width, height
            
            return 0, 0, 0
        except Exception as e:
            logger.error(f"Video metadata error: {e}")
            return 0, 0, 0
    
    async def get_audio_duration(self, file_path: str) -> int:
        """Get audio duration"""
        try:
            from mutagen import File
            audio = File(file_path)
            if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                return int(audio.info.length)
            return 0
        except:
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
        custom_thumbnail: str = None,
        file_type: str = "document"
    ) -> Tuple[bool, Optional[Message], Optional[str]]:
        """Upload file to Telegram - Videos are PLAYABLE!"""
        try:
            if not os.path.exists(file_path):
                return False, None, "File not found"
            
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            logger.info(f"⬆️ Uploading: {filename} ({get_readable_file_size(file_size)}) as {file_type}")
            
            if caption is None:
                caption = f"📁 **{filename}**\n📊 Size: {get_readable_file_size(file_size)}"
            
            # Generate thumbnail
            thumbnail = None
            if custom_thumbnail and os.path.exists(custom_thumbnail):
                thumbnail = custom_thumbnail
            else:
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
                except:
                    pass
            
            sent_message = None
            
            # ============ UPLOAD AS VIDEO ============
            if file_type == "video":
                logger.info("🎬 Uploading as VIDEO (playable)")
                
                # Get video metadata
                duration, width, height = await self.get_video_metadata(file_path)
                
                try:
                    sent_message = await client.send_video(
                        chat_id=chat_id,
                        video=file_path,
                        caption=caption,
                        duration=duration,
                        width=width,
                        height=height,
                        thumb=thumbnail,
                        supports_streaming=True,  # IMPORTANT: Makes video playable!
                        reply_to_message_id=reply_to_message_id,
                        message_thread_id=message_thread_id,
                        progress=progress_callback
                    )
                    logger.info("✅ Video uploaded successfully!")
                except Exception as e:
                    logger.error(f"Video upload failed, trying as document: {e}")
                    # Fallback to document
                    sent_message = await client.send_document(
                        chat_id=chat_id,
                        document=file_path,
                        caption=caption,
                        thumb=thumbnail,
                        reply_to_message_id=reply_to_message_id,
                        message_thread_id=message_thread_id,
                        progress=progress_callback
                    )
            
            # ============ UPLOAD AS AUDIO ============
            elif file_type == "audio":
                logger.info("🎵 Uploading as AUDIO")
                
                duration = await self.get_audio_duration(file_path)
                
                try:
                    sent_message = await client.send_audio(
                        chat_id=chat_id,
                        audio=file_path,
                        caption=caption,
                        duration=duration,
                        thumb=thumbnail,
                        reply_to_message_id=reply_to_message_id,
                        message_thread_id=message_thread_id,
                        progress=progress_callback
                    )
                except Exception as e:
                    logger.error(f"Audio upload failed: {e}")
                    sent_message = await client.send_document(
                        chat_id=chat_id,
                        document=file_path,
                        caption=caption,
                        thumb=thumbnail,
                        reply_to_message_id=reply_to_message_id,
                        message_thread_id=message_thread_id,
                        progress=progress_callback
                    )
            
            # ============ UPLOAD AS IMAGE ============
            elif file_type == "image":
                logger.info("🖼️ Uploading as IMAGE")
                
                if file_size < 10 * 1024 * 1024:  # Under 10 MB
                    try:
                        sent_message = await client.send_photo(
                            chat_id=chat_id,
                            photo=file_path,
                            caption=caption,
                            reply_to_message_id=reply_to_message_id,
                            message_thread_id=message_thread_id,
                            progress=progress_callback
                        )
                    except:
                        sent_message = await client.send_document(
                            chat_id=chat_id,
                            document=file_path,
                            caption=caption,
                            thumb=thumbnail,
                            reply_to_message_id=reply_to_message_id,
                            message_thread_id=message_thread_id,
                            progress=progress_callback
                        )
                else:
                    sent_message = await client.send_document(
                        chat_id=chat_id,
                        document=file_path,
                        caption=caption,
                        thumb=thumbnail,
                        reply_to_message_id=reply_to_message_id,
                        message_thread_id=message_thread_id,
                        progress=progress_callback
                    )
            
            # ============ UPLOAD AS DOCUMENT ============
            else:
                logger.info("📄 Uploading as DOCUMENT")
                
                sent_message = await client.send_document(
                    chat_id=chat_id,
                    document=file_path,
                    caption=caption,
                    thumb=thumbnail,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=message_thread_id,
                    progress=progress_callback
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
            display_url = url[:80] + "..." if len(url) > 80 else url
            
            log_text = f"""
{status_emoji} **File {'Uploaded' if status == 'success' else 'Failed'}**

👤 **User:** @{username or 'None'} (`{user_id}`)
📁 **File:** `{filename}`
🔗 **Link:** `{display_url}`
"""
            
            if error:
                log_text += f"\n❌ **Error:** `{error[:100]}`"
            
            await client.send_message(Config.LOG_CHANNEL, log_text)
        except Exception as e:
            logger.error(f"Log send error: {e}")
