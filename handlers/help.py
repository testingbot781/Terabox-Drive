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

https://drive.google.com/file/d/xxxxx/view
https://terabox.com/s/xxxxx

━━━━━━━━━━━━━━━━━━━━━━
📝 **BULK DOWNLOAD (.txt)**
━━━━━━━━━━━━━━━━━━━━━━

1️⃣ Create a .txt file with links (one per line)
2️⃣ Send the .txt file to bot
3️⃣ Bot will process all links in queue

**Example .txt content:**
https://drive.google.com/file/d/xxx1
https://drive.google.com/file/d/xxx2
https://terabox.com/s/xxx3

━━━━━━━━━━━━━━━━━━━━━━
👥 **GROUP USAGE**
━━━━━━━━━━━━━━━━━━━━━━

• Reply to bot's message with links
• Mention bot with links: @botusername link
• Works in Topics! Files sent to same topic

━━━━━━━━━━━━━━━━━━━━━━
📁 **FOLDER HANDLING**
━━━━━━━━━━━━━━━━━━━━━━

• Folder contents auto-detected
• All files zipped together
• ZIP file sent with folder name

━━━━━━━━━━━━━━━━━━━━━━
🖼️ **THUMBNAIL GENERATION**
━━━━━━━━━━━━━━━━━━━━━━

Auto-generated for:
• Videos (.mp4, .mkv, etc.)
• Images (.jpg, .png, etc.)
• Audio (.mp3, .wav, etc.)
• PDF files
• APK files

━━━━━━━━━━━━━━━━━━━━━━
⚙️ **COMMANDS**
━━━━━━━━━━━━━━━━━━━━━━

/start - Start the bot
/help - This help message
/setting - User settings (Premium)
/cancel - Cancel current task

**Owner Commands:**
/broadcast - Send broadcast
/premium <user_id> <days> - Add premium
/removepremium <user_id> - Remove premium

━━━━━━━━━━━━━━━━━━━━━━
💎 **PREMIUM vs FREEMIUM**
━━━━━━━━━━━━━━━━━━━━━━

**🆓 FREEMIUM:**
• Daily Limit: {free_limit} tasks
• Max File Size: {free_size} MB
• Speed: Low
• Settings: ❌

**💎 PREMIUM:**
• Daily Limit: Unlimited
• Max File Size: {premium_size} MB
• Speed: High
• Settings: ✅

━━━━━━━━━━━━━━━━━━━━━━
⚠️ **NOTES**
━━━━━━━━━━━━━━━━━━━━━━

• Links processed one by one (queue)
• Progress shown every 8 seconds
• Failed downloads reported
• Files auto-deleted after upload
""".format(
    free_limit=Config.FREE_DAILY_LIMIT,
    free_size=Config.FREE_MAX_SIZE_MB,
    premium_size=Config.PREMIUM_MAX_SIZE_MB
)

@Client.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    user_id = message.from_user.id
    is_premium = await user_db.is_premium(user_id)
    
    status = "💎 Premium User" if is_premium else "🆓 Freemium User"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 How to Download", callback_data="help_download"),
            InlineKeyboardButton("📝 Bulk Download", callback_data="help_bulk")
        ],
        [
            InlineKeyboardButton("👥 Group Usage", callback_data="help_group"),
            InlineKeyboardButton("💎 Premium", callback_data="help_premium")
        ],
        [
            InlineKeyboardButton("📢 Channel", url=Config.FORCE_SUB_LINK),
            InlineKeyboardButton("👨‍💻 Support", url=Config.OWNER_CONTACT)
        ],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await message.reply_text(
        f"📚 **Bot Help & Guide**\n\n"
        f"👤 Your Status: {status}\n\n"
        f"Select a topic below or read the full guide:",
        reply_markup=keyboard
    )

@Client.on_callback_query(filters.regex("^help_download$"))
async def help_download_callback(client: Client, callback_query: CallbackQuery):
    """Download help callback"""
    text = """
📥 **HOW TO DOWNLOAD**

**Step 1:** Get your download link
• Google Drive: Share link
• Terabox: Copy direct link

**Step 2:** Send link to bot
Just paste the link in chat!

**Step 3:** Wait for download
Bot shows progress with:
• Download percentage
• Speed
• ETA

**Step 4:** Receive file
File uploaded with:
• Original name
• Thumbnail
• File info

**Example:**

  https://drive.google.com/file/d/1ABC.../view

  """
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Back", callback_data="help_main")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^help_bulk$"))
async def help_bulk_callback(client: Client, callback_query: CallbackQuery):
    """Bulk download help callback"""
    text = """
📝 **BULK DOWNLOAD (.txt)**

**Step 1:** Create a text file
Open notepad and paste links

**Step 2:** Format links
One link per line:

  https://drive.google.com/file/d/xxx1
https://drive.google.com/file/d/xxx2
https://terabox.com/s/xxx3


**Step 3:** Save as .txt
Save file with .txt extension

**Step 4:** Send to bot
Upload the .txt file

**Step 5:** Queue processing
• Bot processes one by one
• Shows: 1/10 tasks running
• Progress for each file

**Step 6:** Summary
After completion:
• Total files
• Success count
• Failed count
• File types breakdown
"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Back", callback_data="help_main")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^help_group$"))
async def help_group_callback(client: Client, callback_query: CallbackQuery):
    """Group help callback"""
    text = """
👥 **GROUP USAGE**

**Method 1: Reply**
Reply to bot's message with link

**Method 2: Mention**
@botusername https://link.com

**Topic Support:**
• Bot detects topics automatically
• Files sent to same topic
• Reply to user's message

**Permissions Needed:**
• Send Messages
• Send Media
• Pin Messages (optional)

**Note:**
• Same limits apply
• Queue shared with DM
• Progress shown in group
"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Back", callback_data="help_main")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^help_premium$"))
async def help_premium_callback(client: Client, callback_query: CallbackQuery):
    """Premium help callback"""
    text = f"""
💎 **PREMIUM BENEFITS**

**🆓 FREEMIUM:**
├ Daily Limit: {Config.FREE_DAILY_LIMIT} tasks
├ Max Size: {Config.FREE_MAX_SIZE_MB} MB
├ Speed: Low
├ Settings: ❌
└ Priority: Low

**💎 PREMIUM:**
├ Daily Limit: ♾️ Unlimited
├ Max Size: {Config.PREMIUM_MAX_SIZE_MB} MB (4 GB)
├ Speed: High
├ Settings: ✅
└ Priority: High

**Premium Settings:**
• Custom Chat ID
• Custom Title Format
• Custom Thumbnail

**Get Premium:**
Contact owner for premium subscription!
"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Get Premium", url=Config.OWNER_CONTACT)],
        [InlineKeyboardButton("◀️ Back", callback_data="help_main")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^help_main$"))
async def help_main_callback(client: Client, callback_query: CallbackQuery):
    """Main help callback"""
    user_id = callback_query.from_user.id
    is_premium = await user_db.is_premium(user_id)
    status = "💎 Premium User" if is_premium else "🆓 Freemium User"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 How to Download", callback_data="help_download"),
            InlineKeyboardButton("📝 Bulk Download", callback_data="help_bulk")
        ],
        [
            InlineKeyboardButton("👥 Group Usage", callback_data="help_group"),
            InlineKeyboardButton("💎 Premium", callback_data="help_premium")
        ],
        [
            InlineKeyboardButton("📢 Channel", url=Config.FORCE_SUB_LINK),
            InlineKeyboardButton("👨‍💻 Support", url=Config.OWNER_CONTACT)
        ],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await callback_query.message.edit_text(
        f"📚 **Bot Help & Guide**\n\n"
        f"👤 Your Status: {status}\n\n"
        f"Select a topic below or read the full guide:",
        reply_markup=keyboard
    )
    await callback_query.answer()
