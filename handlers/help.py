import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from database import user_db

logger = logging.getLogger(__name__)

HELP_TEXT = """
📚 **COMPLETE BOT GUIDE**

━━━━━━━━━━━━━━━━━━━━━━
📥 **DOWNLOADING FILES**
━━━━━━━━━━━━━━━━━━━━━━

**Supported Sources:**
• Google Drive (Direct Links)
• Terabox (Direct Links)

**How to Download:**
1️⃣ Send a direct download link
2️⃣ Bot will download the file
3️⃣ File will be uploaded with thumbnail

**Example Links:**
