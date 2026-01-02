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

# Initialize downloader and uploader
downloader = Downloader()
uploader = Uploader()


# ==================== FORCE SUBSCRIBE CHECK ====================

async def check_force_sub(client: Client, user_id: int) -> bool:
    """Check if user has joined force subscribe channel"""
    try:
        member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, user_id)
        if member.status in ["kicked", "banned", "left"]:
            return False
        return True
    except Exception as e:
        logger.debug(f"Force sub check: {e}")
        return True


# ==================== LINK FILTER ====================

async def link_filter_func(_, __, message: Message):
    """Filter function to detect links in messages"""
    if not message.text:
        return False
    
    text = message.text.lower()
    
    # Check for URL patterns
    has_link = any([
        'http://' in text,
        'https://' in text,
        'drive.google.com' in text,
        'terabox' in text,
        '1024tera' in text,
        'storage.googleapis' in text,
    ])
    
    return has_link

link_filter = filters.create(link_filter_func)


# ==================== PRIVATE CHAT HANDLER ====================

@Client.on_message(filters.private & filters.text & link_filter)
async def private_link_handler(client: Client, message: Message):
    """Handle links sent in private chat"""
    logger.info(f"📥 Private link from user {message.from_user.id}")
    
    # Skip if it's a command
    if message.text.startswith('/'):
        return
    
    await process_user_links(client, message, is_group=False)


# ==================== GROUP CHAT HANDLER ====================

@Client.on_message(filters.group & filters.text & link_filter)
async def group_link_handler(client: Client, message: Message):
    """Handle links in group when bot is mentioned or replied to"""
    if not message.text:
        return
    
    # Get bot info
    bot = await client.get_me()
    bot_username = f"@{bot.username}".lower() if bot.username else ""
    
    # Check if bot is mentioned
    is_mentioned = bot_username and bot_username in message.text.lower()
    
    # Check if replied to bot
    is_reply_to_bot = False
    if message.reply_to_message and message.reply_to_message.from_user:
        is_reply_to_bot = message.reply_to_message.from_user.id == bot.id
    
    # Only process if mentioned or replied to
    if not (is_mentioned or is_reply_to_bot):
        return
    
    logger.info(f"📥 Group link from user {message.from_user.id}")
    await process_user_links(client, message, is_group=True)


# ==================== MAIN LINK PROCESSOR ====================

async def process_user_links(client: Client, message: Message, is_group: bool = False):
    """Main function to process links from user message"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "User"
    chat_id = message.chat.id
    
    logger.info(f"🔄 Processing links for user {user_id}")
    
    # Add user to database
    try:
        await db.add_user(user_id, username, first_name)
    except Exception as e:
        logger.error(f"DB add user error: {e}")
    
    # Check if user is banned
    try:
        if await db.is_user_banned(user_id):
            return await message.reply_text("❌ You are banned from using this bot!")
    except Exception as e:
        logger.error(f"Ban check error: {e}")
    
    # Check force subscribe (only in private chat)
    if not is_group:
        try:
            if not await check_force_sub(client, user_id):
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Channel", url=Config.FORCE_SUB_LINK)],
                    [InlineKeyboardButton("🔄 Try Again", callback_data="check_sub")]
                ])
                return await message.reply_text(
                    "⚠️ **Please join our channel first!**\n\n"
                    f"🔗 {Config.FORCE_SUB_LINK}",
                    reply_markup=keyboard
                )
        except Exception as e:
            logger.error(f"Force sub error: {e}")
    
    # Check daily usage limit
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
    except Exception as e:
        logger.error(f"Limit check error: {e}")
        is_premium = False
        remaining = Config.FREE_DAILY_LIMIT
    
    # Extract links from message
    links = extract_links_from_text(message.text)
    logger.info(f"📎 Found {len(links)} links in message")
    
    if not links:
        return await message.reply_text("❌ No valid links found in your message!")
    
    # Filter for supported links
    supported_links = []
    for link in links:
        if is_gdrive_link(link) or is_terabox_link(link) or is_direct_link(link):
            supported_links.append(link)
            logger.info(f"✅ Supported: {link[:50]}...")
        else:
            logger.info(f"❌ Unsupported: {link[:50]}...")
    
    if not supported_links:
        return await message.reply_text(
            "❌ **No Supported Links Found!**\n\n"
            "**Supported sources:**\n"
            "• Google Drive\n"
            "• Terabox / 1024Tera\n"
            "• Direct download links (.mp4, .pdf, etc.)"
        )
    
    # Send initial status message
    status_msg = await message.reply_text(
        f"📥 **Processing {len(supported_links)} Link(s)...**\n\n"
        f"⏳ Please wait...",
        reply_to_message_id=message.id
    )
    
    # Pin message in group
    if is_group:
        try:
            await status_msg.pin(disable_notification=True)
        except Exception as e:
            logger.debug(f"Could not pin: {e}")
    
    # Initialize results tracker
    results = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'file_types': {}
    }
    
    # Process each link
    for i, link in enumerate(supported_links, 1):
        try:
            # Update status
            link_display = link[:50] + "..." if len(link) > 50 else link
            await status_msg.edit_text(
                f"📥 **Processing Link {i}/{len(supported_links)}**\n\n"
                f"🔗 `{link_display}`\n"
                f"⏳ Checking link type..."
            )
            
            # Check if Terabox folder
            if is_terabox_link(link):
                is_folder = 'filelist' in link.lower() or ('path=' in link.lower() and '%2F' in link.lower())
                
                if is_folder:
                    logger.info(f"📁 Processing Terabox folder: {link[:50]}...")
                    
                    # Process folder
                    folder_results = await process_terabox_folder(
                        client=client,
                        url=link,
                        user_id=user_id,
                        username=username,
                        chat_id=chat_id,
                        reply_to_id=message.id,
                        progress_message=status_msg,
                        is_premium=is_premium
                    )
                    
                    # Add folder results to total
                    results['total'] += folder_results['total']
                    results['success'] += folder_results['success']
                    results['failed'] += folder_results['failed']
                    
                    for ft, count in folder_results.get('file_types', {}).items():
                        results['file_types'][ft] = results['file_types'].get(ft, 0) + count
                    
                    # Delay between links
                    if i < len(supported_links):
                        await asyncio.sleep(Config.MESSAGE_DELAY)
                    
                    continue
            
            # Single file download
            results['total'] += 1
            
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
                
                # Increment usage for free users
                if not is_premium:
                    try:
                        await user_db.increment_usage(user_id)
                    except Exception as e:
                        logger.error(f"Usage increment error: {e}")
            else:
                results['failed'] += 1
            
            # Delay between links to avoid flood
            if i < len(supported_links):
                await asyncio.sleep(Config.MESSAGE_DELAY)
        
        except Exception as e:
            logger.error(f"Link processing error: {e}")
            results['total'] += 1
            results['failed'] += 1
    
    # Cleanup user's download directory
    await cleanup_user_dir(user_id)
    
    # Send final summary with owner contact button
    summary = generate_summary(results)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Contact Owner", url=Config.OWNER_CONTACT)]
    ])
    
    try:
        await status_msg.edit_text(summary, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Summary edit error: {e}")
    
    # Unpin message in group
    if is_group:
        try:
            await status_msg.unpin()
        except Exception as e:
            logger.debug(f"Could not unpin: {e}")


# ==================== TERABOX FOLDER PROCESSOR ====================

async def process_terabox_folder(
    client: Client,
    url: str,
    user_id: int,
    username: str,
    chat_id: int,
    reply_to_id: int,
    progress_message: Message,
    is_premium: bool
) -> dict:
    """Process Terabox folder - download each file separately"""
    
    results = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'file_types': {}
    }
    
    try:
        # Update progress
        await progress_message.edit_text(
            "📁 **Terabox Folder Detected**\n\n"
            "⏳ Fetching file list..."
        )
        
        # Get folder files
        files = await downloader.get_terabox_folder_files(url)
        
        if not files:
            logger.error("No files found in Terabox folder")
            await progress_message.edit_text(
                "❌ **Could not fetch folder files!**\n\n"
                "The folder may be empty or requires login.\n"
                "Try adding `TERABOX_COOKIE` to environment."
            )
            results['total'] = 1
            results['failed'] = 1
            return results
        
        logger.info(f"📁 Found {len(files)} files in folder")
        results['total'] = len(files)
        
        # Update progress
        await progress_message.edit_text(
            f"📁 **Terabox Folder**\n\n"
            f"📊 Found **{len(files)}** file(s)\n"
            f"⏳ Starting downloads..."
        )
        
        # Create download directory
        download_path = create_download_dir(user_id)
        
        # Process each file
        for i, file_info in enumerate(files, 1):
            try:
                filename = file_info.get('filename', f'file_{i}')
                file_size = file_info.get('size', 0)
                
                logger.info(f"📥 Processing folder file {i}/{len(files)}: {filename}")
                
                # Update progress
                await progress_message.edit_text(
                    f"📁 **Folder: {i}/{len(files)}**\n\n"
                    f"📄 `{filename}`\n"
                    f"📊 Size: {get_readable_file_size(file_size)}\n"
                    f"⏳ Downloading..."
                )
                
                # Download file
                success, file_path, error = await downloader.download_terabox_single_file(
                    file_info, download_path, progress_message
                )
                
                if not success or not file_path:
                    logger.error(f"Failed to download: {filename} - {error}")
                    results['failed'] += 1
                    await uploader.send_log(client, user_id, username, url, filename, "failed", error)
                    continue
                
                # Get actual file info
                actual_filename = os.path.basename(file_path)
                actual_size = os.path.getsize(file_path)
                extension = get_file_extension(actual_filename)
                file_type = get_file_type(extension)
                
                # Check size limit
                max_size, max_size_mb = await user_db.get_max_size(user_id)
                
                if actual_size > max_size:
                    await cleanup_file(file_path)
                    error_msg = f"File too large! Max: {max_size_mb}MB"
                    logger.error(f"{filename}: {error_msg}")
                    results['failed'] += 1
                    await uploader.send_log(client, user_id, username, url, actual_filename, "failed", error_msg)
                    continue
                
                # Update progress for upload
                await progress_message.edit_text(
                    f"📁 **Folder: {i}/{len(files)}**\n\n"
                    f"📄 `{actual_filename}`\n"
                    f"📊 Size: {get_readable_file_size(actual_size)}\n"
                    f"⬆️ Uploading..."
                )
                
                # Create caption
                caption = f"📁 **{actual_filename}**\n📊 Size: {get_readable_file_size(actual_size)}"
                
                # Upload file
                upload_success, sent_msg, upload_error = await uploader.upload_file(
                    client=client,
                    file_path=file_path,
                    chat_id=chat_id,
                    progress_message=progress_message,
                    caption=caption,
                    reply_to_message_id=reply_to_id,
                    message_thread_id=None,
                    custom_thumbnail=None,
                    file_type=file_type
                )
                
                # Cleanup file immediately
                await cleanup_file(file_path)
                
                if upload_success:
                    results['success'] += 1
                    results['file_types'][file_type] = results['file_types'].get(file_type, 0) + 1
                    await uploader.send_log(client, user_id, username, url, actual_filename, "success")
                    
                    # Increment usage for free users
                    if not is_premium:
                        try:
                            await user_db.increment_usage(user_id)
                        except:
                            pass
                    
                    logger.info(f"✅ Uploaded: {actual_filename}")
                else:
                    results['failed'] += 1
                    await uploader.send_log(client, user_id, username, url, actual_filename, "failed", upload_error)
                    logger.error(f"❌ Upload failed: {actual_filename} - {upload_error}")
                
                # Delay between files
                await asyncio.sleep(Config.MESSAGE_DELAY)
            
            except Exception as e:
                logger.error(f"Folder file error: {e}")
                results['failed'] += 1
        
        # Final cleanup
        await cleanup_user_dir(user_id)
    
    except Exception as e:
        logger.error(f"Folder processing error: {e}")
        results['failed'] += 1
    
    return results


# ==================== SINGLE LINK DOWNLOADER & UPLOADER ====================

async def download_and_upload_link(
    client: Client,
    url: str,
    user_id: int,
    username: str,
    chat_id: int,
    reply_to_id: int,
    progress_message: Message
) -> tuple:
    """Download and upload a single link"""
    
    download_path = create_download_dir(user_id)
    file_path = None
    
    try:
        logger.info(f"⬇️ Starting download: {url[:50]}...")
        
        # Determine link type and download
        if is_gdrive_link(url):
            logger.info("📁 Link type: Google Drive")
            success, file_path, error = await downloader.download_gdrive(
                url, download_path, progress_message
            )
        elif is_terabox_link(url):
            logger.info("📁 Link type: Terabox")
            success, file_path, error = await downloader.download_terabox(
                url, download_path, progress_message
            )
            
            # Check if it's a folder marker
            if success and file_path and file_path.startswith("TERABOX_FOLDER:"):
                # This shouldn't happen here, but handle gracefully
                return False, None
        else:
            logger.info("📁 Link type: Direct")
            success, file_path, error = await downloader.download_direct(
                url, download_path, progress_message
            )
        
        # Check download result
        if not success or not file_path:
            logger.error(f"❌ Download failed: {error}")
            await progress_message.edit_text(f"❌ **Download Failed!**\n\n`{error}`")
            await uploader.send_log(client, user_id, username, url, "Unknown", "failed", error)
            return False, None
        
        logger.info(f"✅ Downloaded: {file_path}")
        
        # Get file information
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        extension = get_file_extension(filename)
        file_type = get_file_type(extension)
        
        logger.info(f"📊 File: {filename}, Size: {get_readable_file_size(file_size)}, Type: {file_type}")
        
        # Check file size limit
        max_size, max_size_mb = await user_db.get_max_size(user_id)
        
        if file_size > max_size:
            await cleanup_file(file_path)
            error_msg = f"File too large! Max: {max_size_mb}MB, File: {get_readable_file_size(file_size)}"
            await progress_message.edit_text(f"❌ **{error_msg}**")
            await uploader.send_log(client, user_id, username, url, filename, "failed", error_msg)
            return False, None
        
        # Get user settings
        try:
            settings = await user_db.get_settings(user_id)
            custom_thumbnail = settings.get("thumbnail")
            custom_title = settings.get("title")
            target_chat = settings.get("chat_id") or chat_id
        except Exception as e:
            logger.error(f"Settings error: {e}")
            custom_thumbnail = None
            custom_title = None
            target_chat = chat_id
        
        # Create caption
        if custom_title:
            try:
                caption = custom_title.format(
                    filename=filename,
                    ext=extension,
                    size=get_readable_file_size(file_size)
                )
            except:
                caption = f"📁 **{filename}**\n📊 Size: {get_readable_file_size(file_size)}"
        else:
            caption = f"📁 **{filename}**\n📊 Size: {get_readable_file_size(file_size)}"
        
        # Upload file
        logger.info(f"⬆️ Uploading to chat {target_chat}...")
        
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
        
        # Cleanup file immediately after upload
        await cleanup_file(file_path)
        
        if success:
            logger.info(f"✅ Upload successful: {filename}")
            await progress_message.edit_text(f"✅ **Uploaded Successfully!**\n\n📁 `{filename}`")
            await uploader.send_log(client, user_id, username, url, filename, "success")
            return True, file_type
        else:
            logger.error(f"❌ Upload failed: {error}")
            await progress_message.edit_text(f"❌ **Upload Failed!**\n\n`{error}`")
            await uploader.send_log(client, user_id, username, url, filename, "failed", error)
            return False, None
    
    except asyncio.CancelledError:
        logger.info("Task cancelled")
        if file_path:
            await cleanup_file(file_path)
        return False, None
    
    except Exception as e:
        logger.error(f"❌ Error in download_and_upload_link: {e}")
        if file_path:
            await cleanup_file(file_path)
        try:
            await progress_message.edit_text(f"❌ **Error:** `{str(e)}`")
        except:
            pass
        return False, None


# Log when handler is loaded
logger.info("✅ Link handler loaded successfully!")
