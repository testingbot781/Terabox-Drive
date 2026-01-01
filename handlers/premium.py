import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config
from database import user_db

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("premium") & filters.private)
async def add_premium_command(client: Client, message: Message):
    """Handle /premium command - Owner only"""
    user_id = message.from_user.id
    
    # Check if owner
    if user_id not in Config.OWNER_IDS:
        return await message.reply_text("❌ This command is only for owners!")
    
    # Parse command
    try:
        args = message.text.split()
        if len(args) < 3:
            return await message.reply_text(
                "❌ **Usage:**\n"
                "`/premium <user_id> <days>`\n\n"
                "**Example:**\n"
                "`/premium 123456789 30`"
            )
        
        target_user_id = int(args[1])
        days = int(args[2])
        
        if days <= 0:
            return await message.reply_text("❌ Days must be greater than 0!")
        
    except ValueError:
        return await message.reply_text("❌ Invalid user ID or days!")
    
    # Add premium
    success, expiry_date = await user_db.add_premium(target_user_id, days)
    
    if success:
        expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
        
        await message.reply_text(
            f"✅ **Premium Added!**\n\n"
            f"👤 **User ID:** `{target_user_id}`\n"
            f"📅 **Days:** {days}\n"
            f"⏰ **Expires:** {expiry_str}"
        )
        
        # Notify user
        try:
            await client.send_message(
                target_user_id,
                f"🎉 **Congratulations!**\n\n"
                f"You've been upgraded to **Premium**!\n\n"
                f"📅 **Duration:** {days} days\n"
                f"⏰ **Expires:** {expiry_str}\n\n"
                f"Enjoy unlimited downloads! 💎"
            )
        except:
            pass
        
        # Log
        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"💎 **Premium Added**\n\n"
                f"👤 **User:** `{target_user_id}`\n"
                f"📅 **Days:** {days}\n"
                f"⏰ **Expires:** {expiry_str}\n"
                f"👨‍💼 **By:** {message.from_user.mention}"
            )
        except:
            pass
    else:
        await message.reply_text("❌ Failed to add premium!")

@Client.on_message(filters.command("removepremium") & filters.private)
async def remove_premium_command(client: Client, message: Message):
    """Handle /removepremium command - Owner only"""
    user_id = message.from_user.id
    
    # Check if owner
    if user_id not in Config.OWNER_IDS:
        return await message.reply_text("❌ This command is only for owners!")
    
    # Parse command
    try:
        args = message.text.split()
        if len(args) < 2:
            return await message.reply_text(
                "❌ **Usage:**\n"
                "`/removepremium <user_id>`\n\n"
                "**Example:**\n"
                "`/removepremium 123456789`"
            )
        
        target_user_id = int(args[1])
        
    except ValueError:
        return await message.reply_text("❌ Invalid user ID!")
    
    # Check if premium
    is_premium = await user_db.is_premium(target_user_id)
    if not is_premium:
        return await message.reply_text("❌ User is not premium!")
    
    # Remove premium
    success = await user_db.remove_premium(target_user_id)
    
    if success:
        await message.reply_text(
            f"✅ **Premium Removed!**\n\n"
            f"👤 **User ID:** `{target_user_id}`"
        )
        
        # Notify user
        try:
            await client.send_message(
                target_user_id,
                "😔 **Premium Expired!**\n\n"
                "Your premium subscription has been removed.\n"
                "Contact owner to renew!"
            )
        except:
            pass
        
        # Log
        try:
            await client.send_message(
                Config.LOG_CHANNEL,
                f"💎 **Premium Removed**\n\n"
                f"👤 **User:** `{target_user_id}`\n"
                f"👨‍💼 **By:** {message.from_user.mention}"
            )
        except:
            pass
    else:
        await message.reply_text("❌ Failed to remove premium!")

@Client.on_message(filters.command("checkpremium") & filters.private)
async def check_premium_command(client: Client, message: Message):
    """Check premium status"""
    user_id = message.from_user.id
    
    # Check if checking self or other (owner only)
    args = message.text.split()
    if len(args) > 1 and user_id in Config.OWNER_IDS:
        try:
            target_user_id = int(args[1])
        except:
            return await message.reply_text("❌ Invalid user ID!")
    else:
        target_user_id = user_id
    
    is_premium = await user_db.is_premium(target_user_id)
    
    if is_premium:
        info = await user_db.get_premium_info(target_user_id)
        if info:
            expiry = info.get("expiry_date", "Unknown")
            if isinstance(expiry, datetime):
                expiry = expiry.strftime("%Y-%m-%d %H:%M:%S")
            
            await message.reply_text(
                f"💎 **Premium Status**\n\n"
                f"👤 **User:** `{target_user_id}`\n"
                f"✅ **Status:** Premium\n"
                f"⏰ **Expires:** {expiry}"
            )
        else:
            await message.reply_text(f"✅ User `{target_user_id}` is Premium (Owner)")
    else:
        await message.reply_text(f"🆓 User `{target_user_id}` is Freemium")
