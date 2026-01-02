import os
import uuid
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db, user_db
from utils.downloader import Downloader
from utils.uploader import Uploader
from utils.helpers import (
    read_txt_file, create_download_dir, cleanup_file, cleanup_user_dir,
    is_gdrive_link, is_terabox_link, is_direct_link,
    get_file_extension, get_file_type, get_readable_file_size, generate_summary
)

logger = logging.getLogger(__name__)

# Initialize
downloader = Downloader()
uploader = Uploader()


# Force Subscribe Check
async def check_force_sub(client: Client, user_id: int) -> bool:
    """Check if user has joined force subscribe channel"""
    try:
        member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, user_id)
        if member.status in ["kicked", "banned", "left"]:
            return False
        return True
    except Exception:
        return True


# ============ PRIVATE - TXT FILE HANDLER ============
@Client.on_message(filters.private & filters.document)
async def private_document_handler(client: Client, message: Message):
    """Handle document uploads in private chat"""
    
    # Check if it's a txt file
    if not message.document:
        return
    
    if not message.document.file_name:
        return
    
    if not message.document.file_name.lower().endswith('.txt'):
        return
    
    logger.info(f"📄 TXT file received from {message.from_user.id}")
    
    await process_txt_file(client, message, is_group=False)


# ============ GROUP - TXT FILE HANDLER ============
@Client.on_message(filters.group & filters.document)
async def group_document_handler(client: Client, message: Message):
    """Handle document uploads in groups"""
    
    if not message.document:
        return
    
    if not message.document.file_name:
        return
    
    if not message.document.file_name.lower().endswith('.txt'):
        return
    
    # Get bot info
    bot = await client.get_me()
    bot_username = f"@{bot.username}".lower() if bot.username else ""
    
    # Check if bot is mentioned in caption
    is_mentioned = False
    if message.caption and bot_username:
        is_mentioned = bot_username in message.caption.lower()
    
    # Check if replied to bot
    is_reply_to_bot = False
    if message.reply_to_message and message.reply_to_message.from_user:
        is_reply_to_bot = message.reply_to_message.from_user.id == bot.id
    
    if not (is_mentioned or is_reply_to_bot):
        return
    
    logger.info(f"📄 TXT file received in group from {message.from_user.id}")
    
    await process_txt_file(client, message, is_group=True)


# ============ PROCESS TXT FILE ============
async def process_txt_file(client: Client, message: Message, is_group: bool = False):
    """Process txt file with links"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "User"
    chat_id = message.chat.id
    
    # Get topic ID
    topic_id = None
    if is_group:
        topic_id = getattr(message, 'message_thread_id', None)
    
    # Add user to database
    try:
        await db.add_user(user_id, username, first_name)
    except Exception as e:
        logger.error(f"DB error: {e}")
    
    # Check if banned
    try:
        if await db.is_user_banned(user_id):
            return await message.reply_text("❌ You are banned from using this bot!")
    except:
        pass
    
    # Check force subscribe (only in private)
    if not is_group:
        try:
            if not await check_force_sub(client, user_id):
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Channel", url=Config.FORCE_SUB_LINK)],
                ])
                return await message.reply_text(
                    "⚠️ **Please join our channel first!**",
                    reply_markup=keyboard
                )
        except:
            pass
    
    # Check daily limit
    try:
        can_use, remaining = await user_db.can_use_bot(user_id)
        is_premium = await user_db.is_premium(user_id)
        
        if not can_use:
            return await message.reply_text(
                "❌ **Daily Limit Reached!**\n\n"
                f"You've used all {Config.FREE_DAILY_LIMIT} free tasks for today.\n\n"
                "💎 Upgrade to Premium for unlimited access!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👨‍💻 Get Premium", url=Config.OWNER_CONTACT)]
                ])
            )
    except:
        is_premium = False
        remaining = Config.FREE_DAILY_LIMIT
    
    # Send processing message
    status_msg = await message.reply_text(
        "📄 **Processing .txt file...**\n\n⏳ Reading links...",
        reply_to_message_id=message.id
    )
    
    # Try to pin in group
    if is_group:
        try:
            await status_msg.pin(disable_notification=True)
        except:
            pass
    
    # Download txt file
    download_path = create_download_dir(user_id)
    txt_file_path = os.path.join(download_path, message.document.file_name)
    
    try:
        await message.download(txt_file_path)
        logger.info(f"📥 Downloaded txt file: {txt_file_path}")
    except Exception as e:
        await cleanup_file(txt_file_path)
        return await status_msg.edit_text(f"❌ Failed to download file: {e}")
    
    # Read links from file
    links = await read_txt_file(txt_file_path)
    
    # Cleanup txt file
    await cleanup_file(txt_file_path)
    
    if not links:
        return await status_msg.edit_text(
            "❌ **No Links Found!**\n\n"
            "The .txt file doesn't contain any valid links.\n\n"
            "**Format:**\n"
            "```\n"
            "https://drive.google.com/...\n"
            "https://terabox.com/...\n"
            "```"
        )
    
    logger.info(f"📎 Found {len(links)} links in txt file")
    
    # Filter supported links
    supported_links = []
    unsupported_count = 0
    
    for link in links:
        if is_gdrive_link(link) or is_terabox_link(link) or is_direct_link(link):
            supported_links.append(link)
        else:
            unsupported_count += 1
    
    if not supported_links:
        return await status_msg.edit_text(
            f"❌ **No Supported Links Found!**\n\n"
            f"Total links: {len(links)}\n"
            f"Unsupported: {unsupported_count}\n\n"
            "Supported sources:\n"
            "• Google Drive\n"
            "• Terabox\n"
            "• Direct download links"
        )
    
    # Check remaining limit for freemium users
    if not is_premium:
        if len(supported_links) > remaining:
            return await status_msg.edit_text(
                f"❌ **Limit Exceeded!**\n\n"
                f"Links in file: {len(supported_links)}\n"
                f"Remaining today: {remaining}\n\n"
                f"💎 Upgrade to Premium for unlimited access!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👨‍💻 Get Premium", url=Config.OWNER_CONTACT)]
                ])
            )
    
    # Update status
    await status_msg.edit_text(
        f"📄 **TXT File Processed!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Total Links:** {len(links)}\n"
        f"✅ **Supported:** {len(supported_links)}\n"
        f"❌ **Unsupported:** {unsupported_count}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏳ Starting downloads..."
    )
    
    # Process each link
    results = {
        'total': len(supported_links),
        'success': 0,
        'failed': 0,
        'file_types': {}
    }
    
    for i, link in enumerate(supported_links, 1):
        try:
            # Update status
            await status_msg.edit_text(
                f"📥 **Processing {i}/{len(supported_links)}**\n\n"
                f"🔗 `{link[:50]}...`\n"
                f"⏳ Downloading..."
            )
            
            # Download and upload
            success, file_type = await download_and_upload(
                client=client,
                url=link,
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                topic_id=topic_id,
                reply_to_id=message.id,
                progress_message=status_msg
            )
            
            if success:
                results['success'] += 1
                if file_type:
                    results['file_types'][file_type] = results['file_types'].get(file_type, 0) + 1
                
                # Increment usage
                if not is_premium:
                    try:
                        await user_db.increment_usage(user_id)
                    except:
                        pass
            else:
                results['failed'] += 1
        
        except Exception as e:
            logger.error(f"Error processing link: {e}")
            results['failed'] += 1
    
    # Cleanup
    await cleanup_user_dir(user_id)
    
    # Send summary
    summary = generate_summary(results)
    try:
        await status_msg.edit_text(summary)
    except:
        pass
    
    # Unpin
    if is_group:
        try:
            await status_msg.unpin()
        except:
            pass


# ============ DOWNLOAD AND UPLOAD ============
async def download_and_upload(
    client: Client,
    url: str,
    user_id: int,
    username: str,
    chat_id: int,
    topic_id: int,
    reply_to_id: int,
    progress_message: Message
) -> tuple:
    """Download and upload a single link"""
    download_path = create_download_dir(user_id)
    file_path = None
    
    try:
        # Download
        if is_gdrive_link(url):
            success, file_path, error = await downloader.download_gdrive(url, download_path, progress_message)
        elif is_terabox_link(url):
            success, file_path, error = await downloader.download_terabox(url, download_path, progress_message)
        else:
            success, file_path, error = await downloader.download_direct(url, download_path, progress_message)
        
        if not success or not file_path:
            await progress_message.edit_text(f"❌ **Download Failed!**\n\n`{error}`")
            await uploader.send_log(client, user_id, username, url, "Unknown", "failed", error)
            return False, None
        
        # File info
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        extension = get_file_extension(filename)
        file_type = get_file_type(extension)
        
        # Check size
        max_size, max_size_mb = await user_db.get_max_size(user_id)
        if file_size > max_size:
            await cleanup_file(file_path)
            error_msg = f"File too large! Max: {max_size_mb}MB"
            await progress_message.edit_text(f"❌ {error_msg}")
            return False, None
        
        # Get settings
        try:
            settings = await user_db.get_settings(user_id)
            custom_thumbnail = settings.get("thumbnail")
            target_chat = settings.get("chat_id") or chat_id
        except:
            custom_thumbnail = None
            target_chat = chat_id
        
        # Caption
        caption = f"📁 **{filename}**\n📊 Size: {get_readable_file_size(file_size)}"
        
        # Upload
        success, sent_msg, error = await uploader.upload_file(
            client=client,
            file_path=file_path,
            chat_id=target_chat,
            progress_message=progress_message,
            caption=caption,
            reply_to_message_id=reply_to_id if target_chat == chat_id else None,
            message_thread_id=topic_id,
            custom_thumbnail=custom_thumbnail,
            file_type=file_type
        )
        
        # Cleanup
        await cleanup_file(file_path)
        
        if success:
            await progress_message.edit_text(f"✅ **Uploaded!**\n\n📁 `{filename}`")
            await uploader.send_log(client, user_id, username, url, filename, "success")
            return True, file_type
        else:
            await progress_message.edit_text(f"❌ **Upload Failed!**\n\n`{error}`")
            return False, None
    
    except Exception as e:
        if file_path:
            await cleanup_file(file_path)
        return False, None


logger.info("✅ File handler loaded successfully!")
