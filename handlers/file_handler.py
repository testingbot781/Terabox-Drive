import os
import uuid
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db, user_db
from handlers.start import force_sub_check
from handlers.link_handler import process_queue
from utils.queue_manager import queue_manager, Task
from utils.helpers import (
    read_txt_file, create_download_dir, cleanup_file,
    is_gdrive_link, is_terabox_link, is_direct_link
)

logger = logging.getLogger(__name__)

@Client.on_message(filters.private & filters.document)
async def handle_document(client: Client, message: Message):
    """Handle document uploads (including .txt files)"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Check if it's a txt file
    if not message.document.file_name.endswith('.txt'):
        return  # Ignore non-txt files
    
    # Add user to database
    await db.add_user(user_id, username, first_name)
    
    # Check if banned
    if await db.is_user_banned(user_id):
        return await message.reply_text("❌ You are banned from using this bot!")
    
    # Check force subscribe
    if not await force_sub_check(client, user_id):
        return await message.reply_text(
            "⚠️ Please join our channel first!\n\n"
            f"🔗 {Config.FORCE_SUB_LINK}"
        )
    
    # Check daily limit
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
    
    # Send processing message
    processing_msg = await message.reply_text("📄 **Processing .txt file...**\n\n⏳ Reading links...")
    
    # Download txt file
    download_path = create_download_dir(user_id)
    txt_file_path = os.path.join(download_path, message.document.file_name)
    
    try:
        await message.download(txt_file_path)
    except Exception as e:
        await cleanup_file(txt_file_path)
        return await processing_msg.edit_text(f"❌ Failed to download file: {e}")
    
    # Read links from file
    links = await read_txt_file(txt_file_path)
    
    # Cleanup txt file
    await cleanup_file(txt_file_path)
    
    if not links:
        return await processing_msg.edit_text(
            "❌ **No Links Found!**\n\n"
            "The .txt file doesn't contain any valid links.\n\n"
            "**Format:**\n"
            "```\n"
            "https://drive.google.com/...\n"
            "https://terabox.com/...\n"
            "```"
        )
    
    # Filter supported links
    supported_links = []
    unsupported_count = 0
    
    for link in links:
        if is_gdrive_link(link) or is_terabox_link(link) or is_direct_link(link):
            supported_links.append(link)
        else:
            unsupported_count += 1
    
    if not supported_links:
        return await processing_msg.edit_text(
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
            return await processing_msg.edit_text(
                f"❌ **Limit Exceeded!**\n\n"
                f"Links in file: {len(supported_links)}\n"
                f"Remaining today: {remaining}\n\n"
                f"💎 Upgrade to Premium for unlimited access!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👨‍💻 Get Premium", url=Config.OWNER_CONTACT)]
                ])
            )
    
    # Create tasks
    tasks = []
    for link in supported_links:
        task = Task(
            task_id=str(uuid.uuid4()),
            user_id=user_id,
            url=link,
            chat_id=message.chat.id,
            reply_to_id=message.id
        )
        tasks.append(task)
    
    # Add tasks to queue
    added = await queue_manager.add_multiple_tasks(tasks)
    
    if added == 0:
        return await processing_msg.edit_text("❌ Failed to add tasks to queue!")
    
    # Increment usage for freemium users
    if not is_premium:
        for _ in range(added):
            await user_db.increment_usage(user_id)
    
    # Update processing message
    await processing_msg.edit_text(
        f"📄 **TXT File Processed!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Total Links:** {len(links)}\n"
        f"✅ **Supported:** {len(supported_links)}\n"
        f"❌ **Unsupported:** {unsupported_count}\n"
        f"📥 **Added to Queue:** {added}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏳ Processing will start shortly..."
    )
    
    # Start processing if not already running
    if not queue_manager.is_processing(user_id):
        asyncio.create_task(process_queue(client, user_id, processing_msg))

@Client.on_message(filters.group & filters.document)
async def handle_group_document(client: Client, message: Message):
    """Handle document uploads in groups"""
    # Check if bot is mentioned or message is reply to bot
    bot_info = await client.get_me()
    
    # Check reply
    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id
    
    # Check caption for mention
    is_mentioned = message.caption and f"@{bot_info.username}" in message.caption
    
    if not (is_reply_to_bot or is_mentioned):
        return
    
    if not message.document.file_name.endswith('.txt'):
        return await message.reply_text("❌ Please send a .txt file with links!")
    
    # Process same as private
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Add user to database
    await db.add_user(user_id, username, first_name)
    
    # Check if banned
    if await db.is_user_banned(user_id):
        return await message.reply_text("❌ You are banned from using this bot!")
    
    # Check daily limit
    can_use, remaining = await user_db.can_use_bot(user_id)
    is_premium = await user_db.is_premium(user_id)
    
    if not can_use:
        return await message.reply_text(
            "❌ **Daily Limit Reached!**\n\n"
            "💎 Upgrade to Premium for unlimited access!"
        )
    
    # Get topic ID
    topic_id = message.message_thread_id if message.message_thread_id else None
    
    # Send processing message
    processing_msg = await message.reply_text(
        "📄 **Processing .txt file...**\n\n⏳ Reading links...",
        reply_to_message_id=message.id
    )
    
    # Try to pin
    try:
        await processing_msg.pin(disable_notification=True)
    except:
        pass
    
    # Download txt file
    download_path = create_download_dir(user_id)
    txt_file_path = os.path.join(download_path, message.document.file_name)
    
    try:
        await message.download(txt_file_path)
    except Exception as e:
        await cleanup_file(txt_file_path)
        return await processing_msg.edit_text(f"❌ Failed to download file: {e}")
    
    # Read links from file
    links = await read_txt_file(txt_file_path)
    
    # Cleanup txt file
    await cleanup_file(txt_file_path)
    
    if not links:
        return await processing_msg.edit_text("❌ **No Links Found!**")
    
    # Filter supported links
    supported_links = []
    for link in links:
        if is_gdrive_link(link) or is_terabox_link(link) or is_direct_link(link):
            supported_links.append(link)
    
    if not supported_links:
        return await processing_msg.edit_text("❌ **No Supported Links Found!**")
    
    # Check remaining limit
    if not is_premium and len(supported_links) > remaining:
        return await processing_msg.edit_text(
            f"❌ **Limit Exceeded!**\n\n"
            f"Links: {len(supported_links)} | Remaining: {remaining}"
        )
    
    # Create tasks
    tasks = []
    for link in supported_links:
        task = Task(
            task_id=str(uuid.uuid4()),
            user_id=user_id,
            url=link,
            chat_id=message.chat.id,
            topic_id=topic_id,
            reply_to_id=message.id
        )
        tasks.append(task)
    
    # Add tasks to queue
    added = await queue_manager.add_multiple_tasks(tasks)
    
    # Increment usage
    if not is_premium:
        for _ in range(added):
            await user_db.increment_usage(user_id)
    
    # Update message
    await processing_msg.edit_text(
        f"📄 **TXT File Processed!**\n\n"
        f"✅ Added {added} tasks to queue\n"
        f"⏳ Processing..."
    )
    
    # Start processing
    if not queue_manager.is_processing(user_id):
        asyncio.create_task(process_queue(client, user_id, processing_msg))
