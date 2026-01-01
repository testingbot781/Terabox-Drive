import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from config import Config
from database import db, user_db

logger = logging.getLogger(__name__)

# Force Subscribe Check
async def force_sub_check(client: Client, user_id: int):
    """Check if user has joined force subscribe channel"""
    try:
        member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, user_id)
        if member.status in ["kicked", "banned"]:
            return False
        return True
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        logger.warning("Bot is not admin in force sub channel!")
        return True
    except Exception as e:
        logger.error(f"Force sub check error: {e}")
        return True

# Start Command
@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Add user to database
    await db.add_user(user_id, username, first_name)
    
    # Check if banned
    if await db.is_user_banned(user_id):
        return await message.reply_text("❌ You are banned from using this bot!")
    
    # Check force subscribe
    if not await force_sub_check(client, user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url=Config.FORCE_SUB_LINK)],
            [InlineKeyboardButton("🔄 Try Again", callback_data="check_sub")]
        ])
        
        if Config.START_PIC:
            return await message.reply_photo(
                photo=Config.START_PIC,
                caption="⚠️ **Access Denied!**\n\n"
                        "You need to join our channel first to use this bot.\n\n"
                        "👇 Click the button below to join:",
                reply_markup=keyboard
            )
        else:
            return await message.reply_text(
                "⚠️ **Access Denied!**\n\n"
                "You need to join our channel first to use this bot.\n\n"
                "👇 Click the button below to join:",
                reply_markup=keyboard
            )
    
    # Check premium status
    is_premium = await user_db.is_premium(user_id)
    premium_badge = "💎 Premium" if is_premium else "🆓 Freemium"
    
    # Get usage info
    can_use, remaining = await user_db.can_use_bot(user_id)
    if is_premium:
        usage_text = "♾️ Unlimited"
    else:
        usage_text = f"📊 {remaining}/{Config.FREE_DAILY_LIMIT} tasks remaining today"
    
    # Start message
    start_text = f"""
🎉 **Welcome to Multi Downloader Bot!**

━━━━━━━━━━━━━━━━━━━━━━
👤 **User:** {first_name}
🏷️ **Status:** {premium_badge}
{usage_text}
━━━━━━━━━━━━━━━━━━━━━━

📥 **What I can do:**
• Download files from **Google Drive**
• Download files from **Terabox**
• Generate **Thumbnails** for files
• Process **multiple links** from .txt files
• Auto **ZIP** folder contents
• Queue management for bulk downloads

📋 **Supported Formats:**
Video | Audio | Images | PDF | APK | Documents

🔗 **How to use:**
Just send me a Google Drive or Terabox link!

━━━━━━━━━━━━━━━━━━━━━━
Use /help for detailed instructions
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Force Sub Channel", url=Config.FORCE_SUB_LINK)],
        [InlineKeyboardButton("👨‍💻 Owner Contact", url=Config.OWNER_CONTACT)]
    ])
    
    if Config.START_PIC:
        await message.reply_photo(
            photo=Config.START_PIC,
            caption=start_text,
            reply_markup=keyboard
        )
    else:
        await message.reply_text(
            start_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# Start in Group
@Client.on_message(filters.command("start") & filters.group)
async def start_group(client: Client, message: Message):
    """Handle /start in groups"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel", url=Config.FORCE_SUB_LINK)],
        [InlineKeyboardButton("👨‍💻 Contact", url=Config.OWNER_CONTACT)]
    ])
    
    await message.reply_text(
        "👋 **Hello! I'm Multi Downloader Bot!**\n\n"
        "📥 Send me Google Drive or Terabox links to download files!\n\n"
        "💡 **Tip:** Reply to my message or mention me with links in topics!",
        reply_markup=keyboard
    )

# Check Subscription Callback
@Client.on_callback_query(filters.regex("^check_sub$"))
async def check_sub_callback(client: Client, callback_query: CallbackQuery):
    """Check subscription callback"""
    user_id = callback_query.from_user.id
    
    if await force_sub_check(client, user_id):
        await callback_query.answer("✅ Verified! You can use the bot now.", show_alert=True)
        await callback_query.message.delete()
        
        # Send start message
        message = callback_query.message
        message.from_user = callback_query.from_user
        await start_command(client, message)
    else:
        await callback_query.answer("❌ You haven't joined yet! Please join first.", show_alert=True)

# Close Button Callback
@Client.on_callback_query(filters.regex("^close$"))
async def close_callback(client: Client, callback_query: CallbackQuery):
    """Close message callback"""
    await callback_query.message.delete()
    await callback_query.answer("Closed!", show_alert=False)
