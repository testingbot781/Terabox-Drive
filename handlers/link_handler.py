import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db, user_db
from utils.downloader import Downloader
from utils.uploader import Uploader
from utils.helpers import (
    is_gdrive_link, is_terabox_link, is_direct_link,
    extract_links_from_text, create_download_dir, cleanup_file,
    cleanup_user_dir, get_file_extension, get_file_type, 
    generate_summary, get_readable_file_size
)

logger = logging.getLogger(__name__)

downloader = Downloader()
uploader = Uploader()


async def check_force_sub(client: Client, user_id: int) -> bool:
    """Check force subscribe"""
    try:
        member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, user_id)
        if member.status in ["kicked", "banned", "left"]:
            return False
        return True
    except:
        return True


async def link_filter_func(_, __, message: Message):
    """Filter for links"""
    if not message.text:
        return False
    
    text = message.text.lower()
    return any([
        'http://' in text,
        'https://' in text,
        'drive.google' in text,
        'terabox' in text,
        '1024tera' in text,
        'storage.googleapis' in text,
    ])

link_filter = filters.create(link_filter_func)


@Client.on_message(filters.private & filters.text & link_filter)
async def private_link_handler(client: Client, message: Message):
    """Handle private links"""
    logger.info(f"📥 Private link from {message.from_user.id}")
    
    if message.text.startswith('/'):
        return
    
    await process_user_links(client, message, is_group=False)


@Client.on_message(filters.group & filters.text & link_filter)
async def group_link_handler(client: Client, message: Message):
    """Handle group links"""
    if not message.text:
        return
    
    bot = await client.get_me()
    bot_username = f"@{bot.username}".lower() if bot.username else ""
    
    is_mentioned = bot_username and bot_username in message.text.lower()
    is_reply_to_bot = False
    
    if message.reply_to_message and message.reply_to_message.from_user:
        is_reply_to_bot = message.reply_to_message.from_user.id == bot.id
    
    if not (is_mentioned or is_reply_to_bot):
        return
    
    logger.info(f"📥 Group link from {message.from_user.id}")
    await process_user_links(client, message, is_group=True)


async def process_user_links(client: Client, message: Message, is_group: bool = False):
    """Process links"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "User"
    chat_id = message.chat.id
    
    logger.info(f"🔄 Processing for user {user_id}")
    
    try:
        await db.add_user(user_id, username, first_name)
    except:
        pass
    
    try:
        if await db.is_user_banned(user_id):
            return await message.reply_text("❌ You are banned!")
    except:
        pass
    
    if not is_group:
        try:
            if not await check_force_sub(client, user_id):
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Channel", url=Config.FORCE_SUB_LINK)],
                    [InlineKeyboardButton("🔄 Try Again", callback_data="check_sub")]
                ])
                return await message.reply_text(
                    "⚠️ **Please join our channel first!**",
                    reply_markup=keyboard
                )
        except:
            pass
    
    try:
        can_use, remaining = await user_db.can_use_bot(user_id)
        is_premium = await user_db.is_premium(user_id)
        
        if not can_use:
            return await message.reply_text(
                "❌ **Daily Limit Reached!**\n\n"
                "💎 Upgrade to Premium for unlimited access!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👨‍💻 Get Premium", url=Config.OWNER_CONTACT)]
                ])
            )
    except:
        is_premium = False
        remaining = Config.FREE_DAILY_LIMIT
    
    links = extract_links_from_text(message.text)
    logger.info(f"📎 Found {len(links)} links")
    
    if not links:
        return await message.reply_text("❌ No valid links found!")
    
    supported_links = []
    for link in links:
        if is_gdrive_link(link) or is_terabox_link(link) or is_direct_link(link):
            supported_links.append(link)
    
    if not supported_links:
        return await message.reply_text(
            "❌ **No Supported Links!**\n\n"
            "Supported: Google Drive, Terabox, Direct links"
        )
    
    status_msg = await message.reply_text(
        f"📥 **Processing {len(supported_links)} Link(s)...**",
        reply_to_message_id=message.id
    )
    
    if is_group:
        try:
            await status_msg.pin(disable_notification=True)
        except:
            pass
    
    results = {
        'total': len(supported_links),
        'success': 0,
        'failed': 0,
        'file_types': {}
    }
    
    for i, link in enumerate(supported_links, 1):
        try:
            await status_msg.edit_text(
                f"📥 **Processing {i}/{len(supported_links)}**\n\n"
                f"🔗 `{link[:50]}...`\n"
                f"⏳ Downloading..."
            )
            
            success, file_type = await download_and_upload_link(
                client=client,
                url=link,
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                reply_to_id=message.id,
                progress_message=status_msg
            )
            
            if success:
                results['success'] += 1
                if file_type:
                    results['file_types'][file_type] = results['file_types'].get(file_type, 0) + 1
                
                if not is_premium:
                    try:
                        await user_db.increment_usage(user_id)
                    except:
                        pass
            else:
                results['failed'] += 1
            
            # Add delay between files to avoid flood
            if i < len(supported_links):
                await asyncio.sleep(Config.MESSAGE_DELAY)
        
        except Exception as e:
            logger.error(f"Error: {e}")
            results['failed'] += 1
    
    await cleanup_user_dir(user_id)
    
    # Send summary with inline button
    summary = generate_summary(results)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Contact Owner", url=Config.OWNER_CONTACT)],
        [InlineKeyboardButton("📢 Join Channel", url=Config.FORCE_SUB_LINK)]
    ])
    
    try:
        await status_msg.edit_text(summary, reply_markup=keyboard)
    except:
        pass
    
    if is_group:
        try:
            await status_msg.unpin()
        except:
            pass


async def download_and_upload_link(
    client: Client,
    url: str,
    user_id: int,
    username: str,
    chat_id: int,
    reply_to_id: int,
    progress_message: Message
) -> tuple:
    """Download and upload single link"""
    download_path = create_download_dir(user_id)
    file_path = None
    
    try:
        logger.info(f"⬇️ Downloading: {url[:50]}...")
        
        if is_gdrive_link(url):
            success, file_path, error = await downloader.download_gdrive(url, download_path, progress_message)
        elif is_terabox_link(url):
            success, file_path, error = await downloader.download_terabox(url, download_path, progress_message)
        else:
            success, file_path, error = await downloader.download_direct(url, download_path, progress_message)
        
        if not success or not file_path:
            logger.error(f"❌ Download failed: {error}")
            await progress_message.edit_text(f"❌ **Download Failed!**\n\n`{error}`")
            await uploader.send_log(client, user_id, username, url, "Unknown", "failed", error)
            return False, None
        
        logger.info(f"✅ Downloaded: {file_path}")
        
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        extension = get_file_extension(filename)
        file_type = get_file_type(extension)
        
        logger.info(f"📊 File: {filename}, Size: {get_readable_file_size(file_size)}, Type: {file_type}")
        
        max_size, max_size_mb = await user_db.get_max_size(user_id)
        
        if file_size > max_size:
            await cleanup_file(file_path)
            error_msg = f"File too large! Max: {max_size_mb}MB"
            await progress_message.edit_text(f"❌ {error_msg}")
            await uploader.send_log(client, user_id, username, url, filename, "failed", error_msg)
            return False, None
        
        try:
            settings = await user_db.get_settings(user_id)
            custom_thumbnail = settings.get("thumbnail")
            target_chat = settings.get("chat_id") or chat_id
        except:
            custom_thumbnail = None
            target_chat = chat_id
        
        caption = f"📁 **{filename}**\n📊 Size: {get_readable_file_size(file_size)}"
        
        logger.info(f"⬆️ Uploading to {target_chat}...")
        
        success, sent_message, error = await uploader.upload_file(
            client=client,
            file_path=file_path,
            chat_id=target_chat,
            progress_message=progress_message,
            caption=caption,
            reply_to_message_id=reply_to_id if target_chat == chat_id else None,
            message_thread_id=None,
            custom_thumbnail=custom_thumbnail,
            file_type=file_type
        )
        
        await cleanup_file(file_path)
        
        if success:
            logger.info("✅ Upload success!")
            await progress_message.edit_text(f"✅ **Uploaded!**\n\n📁 `{filename}`")
            await uploader.send_log(client, user_id, username, url, filename, "success")
            
            # Add delay after successful upload
            await asyncio.sleep(Config.MESSAGE_DELAY)
            
            return True, file_type
        else:
            logger.error(f"❌ Upload failed: {error}")
            await progress_message.edit_text(f"❌ **Upload Failed!**\n\n`{error}`")
            await uploader.send_log(client, user_id, username, url, filename, "failed", error)
            return False, None
    
    except asyncio.CancelledError:
        if file_path:
            await cleanup_file(file_path)
        return False, None
    
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        if file_path:
            await cleanup_file(file_path)
        try:
            await progress_message.edit_text(f"❌ **Error:** `{str(e)}`")
        except:
            pass
        return False, None


logger.info("✅ Link handler loaded!")
