import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid
from config import Config
from database import db

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client: Client, message: Message):
    """Handle /broadcast command - Owner only"""
    user_id = message.from_user.id
    
    # Check if owner
    if user_id not in Config.OWNER_IDS:
        return await message.reply_text("❌ This command is only for owners!")
    
    # Check if reply
    if not message.reply_to_message:
        return await message.reply_text(
            "❌ **How to Broadcast:**\n\n"
            "Reply to a message with /broadcast\n"
            "The replied message will be sent to all users."
        )
    
    broadcast_msg = message.reply_to_message
    
    # Get all users
    users = await db.get_all_users()
    total_users = len(users)
    
    if total_users == 0:
        return await message.reply_text("❌ No users in database!")
    
    # Status message
    status_msg = await message.reply_text(
        f"📢 **Broadcasting Started**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"⏳ Progress: 0/{total_users}\n"
        f"✅ Success: 0\n"
        f"❌ Failed: 0"
    )
    
    success = 0
    failed = 0
    blocked = 0
    deleted = 0
    
    start_time = datetime.now()
    
    for i, user in enumerate(users, 1):
        try:
            await broadcast_msg.copy(user["user_id"])
            success += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await broadcast_msg.copy(user["user_id"])
                success += 1
            except:
                failed += 1
        except UserIsBlocked:
            blocked += 1
            failed += 1
        except InputUserDeactivated:
            deleted += 1
            failed += 1
        except PeerIdInvalid:
            failed += 1
        except Exception as e:
            logger.error(f"Broadcast error for {user['user_id']}: {e}")
            failed += 1
        
        # Update status every 50 users
        if i % 50 == 0:
            try:
                await status_msg.edit_text(
                    f"📢 **Broadcasting...**\n\n"
                    f"👥 Total Users: {total_users}\n"
                    f"⏳ Progress: {i}/{total_users}\n"
                    f"✅ Success: {success}\n"
                    f"❌ Failed: {failed}"
                )
            except:
                pass
        
        # Small delay to avoid flood
        await asyncio.sleep(0.05)
    
    end_time = datetime.now()
    time_taken = (end_time - start_time).seconds
    
    # Final status
    await status_msg.edit_text(
        f"📢 **Broadcast Completed!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 **Total Users:** {total_users}\n"
        f"✅ **Success:** {success}\n"
        f"❌ **Failed:** {failed}\n"
        f"🚫 **Blocked:** {blocked}\n"
        f"👻 **Deleted:** {deleted}\n"
        f"⏱️ **Time Taken:** {time_taken}s\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    # Log to channel
    try:
        await client.send_message(
            Config.LOG_CHANNEL,
            f"📢 **Broadcast Completed**\n\n"
            f"👤 **By:** {message.from_user.mention} (`{user_id}`)\n"
            f"👥 **Total:** {total_users}\n"
            f"✅ **Success:** {success}\n"
            f"❌ **Failed:** {failed}\n"
            f"⏱️ **Time:** {time_taken}s"
        )
    except:
        pass
