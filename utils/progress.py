import time
import logging

logger = logging.getLogger(__name__)

class Progress:
    def __init__(self):
        self.last_update_time = 0
        self.update_interval = 8  # seconds
    
    def generate_progress_bar(self, current: int, total: int, length: int = 20) -> str:
        """Generate progress bar with filled and empty circles"""
        if total == 0:
            return "○" * length
        
        percentage = current / total
        filled = int(length * percentage)
        empty = length - filled
        
        bar = "●" * filled + "○" * empty
        return bar
    
    def format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable size"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    def format_time(self, seconds: int) -> str:
        """Format seconds to readable time"""
        if seconds < 0:
            return "0s"
        
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{int(minutes)}m, {int(secs)}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{int(hours)}h, {int(minutes)}m"
    
    def should_update(self) -> bool:
        """Check if progress should be updated (8 second interval)"""
        current_time = time.time()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            return True
        return False
    
    def get_download_progress_text(
        self,
        filename: str,
        current: int,
        total: int,
        speed: float,
        eta: int
    ) -> str:
        """Generate download progress text"""
        percentage = (current / total * 100) if total > 0 else 0
        progress_bar = self.generate_progress_bar(current, total)
        
        text = f"""
**Downloading**
`{filename[:50]}{'...' if len(filename) > 50 else ''}`
to my server

[{progress_bar}]

◌ Progress😉: 〘 {percentage:.2f}% 〙
Done: 〘{self.format_size(current)} of {self.format_size(total)}〙
◌ Speed🚀: 〘 {self.format_size(int(speed))}/s 〙
◌ Time Left⏳: 〘 {self.format_time(eta)} 〙
"""
        return text
    
    def get_upload_progress_text(
        self,
        filename: str,
        current: int,
        total: int,
        speed: float,
        eta: int
    ) -> str:
        """Generate upload progress text"""
        percentage = (current / total * 100) if total > 0 else 0
        progress_bar = self.generate_progress_bar(current, total)
        
        text = f"""
**Uploading**
`{filename[:50]}{'...' if len(filename) > 50 else ''}`
to Telegram

[{progress_bar}]

◌ Progress😉: 〘 {percentage:.2f}% 〙
Done: 〘{self.format_size(current)} of {self.format_size(total)}〙
◌ Speed🚀: 〘 {self.format_size(int(speed))}/s 〙
◌ Time Left⏳: 〘 {self.format_time(eta)} 〙
"""
        return text
    
    def get_queue_status_text(self, current: int, total: int, filename: str) -> str:
        """Generate queue status text"""
        return f"📊 **Task Progress:** {current}/{total}\n📁 **Current:** `{filename}`"


# Progress callback for pyrogram
async def progress_callback(current, total, message, progress_obj, start_time, filename, is_upload=False):
    """Callback function for upload/download progress"""
    try:
        if not progress_obj.should_update():
            return
        
        elapsed_time = time.time() - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        eta = int((total - current) / speed) if speed > 0 else 0
        
        if is_upload:
            text = progress_obj.get_upload_progress_text(filename, current, total, speed, eta)
        else:
            text = progress_obj.get_download_progress_text(filename, current, total, speed, eta)
        
        await message.edit_text(text)
    except Exception as e:
        logger.debug(f"Progress update error: {e}")
