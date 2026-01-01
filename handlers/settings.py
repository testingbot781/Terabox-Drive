import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from database import user_db

logger = logging.getLogger(__name__)

# Setting states
setting_states = {}

@Client.on_message(filters.command("setting") & filters.private)
async def setting_command(client: Client, message: Message):
    """Handle /setting command"""
    user_id = message.from_user.id
    
    # Check if premium
    is_premium = await user_db.is_premium(user_id)
    
    if not is_premium:
        return await message.reply_text(
            "❌ **Premium Feature Only!**\n\n"
            "Settings are only available for premium users.\n\n"
            "💎 Contact owner to get premium!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👨‍💻 Get Premium", url=Config.OWNER_CONTACT)]
            ])
        )
    
    # Get current settings
    settings = await user_db.get_settings(user_id)
    
    chat_id = settings.get("chat_id", "Not Set")
    title = settings.get("title", "Not Set")
    thumbnail = "✅ Set" if settings.get("thumbnail") else "❌ Not Set"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📍 Set Chat ID", callback_data="set_chat_id"),
            InlineKeyboardButton("📝 Set Title", callback_data="set_title")
        ],
        [
            InlineKeyboardButton("🖼️ Set Thumbnail", callback_data="set_thumbnail"),
            InlineKeyboardButton("🔄 Reset Settings", callback_data="reset_settings")
        ],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await message.reply_text(
        f"⚙️ **Your Settings**\n\n"
        f"📍 **Chat ID:** `{chat_id}`\n"
        f"📝 **Title:** `{title if title != 'Not Set' else 'Default'}`\n"
        f"🖼️ **Thumbnail:** {thumbnail}\n\n"
        f"Click buttons below to modify:",
        reply_markup=keyboard
    )

@Client.on_callback_query(filters.regex("^set_chat_id$"))
async def set_chat_id_callback(client: Client, callback_query: CallbackQuery):
    """Set chat ID callback"""
    user_id = callback_query.from_user.id
    
    if not await user_db.is_premium(user_id):
        return await callback_query.answer("❌ Premium only!", show_alert=True)
    
    setting_states[user_id] = "waiting_chat_id"
    
    await callback_query.message.edit_text(
        "📍 **Set Chat ID**\n\n"
        "Send the Chat ID where you want files to be uploaded.\n\n"
        "**How to get Chat ID:**\n"
        "• Forward a message from that chat to @userinfobot\n"
        "• Or use @RawDataBot\n\n"
        "**Example:** `-1001234567890`\n\n"
        "Send /cancel to cancel.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_setting")]
        ])
    )
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^set_title$"))
async def set_title_callback(client: Client, callback_query: CallbackQuery):
    """Set title callback"""
    user_id = callback_query.from_user.id
    
    if not await user_db.is_premium(user_id):
        return await callback_query.answer("❌ Premium only!", show_alert=True)
    
    setting_states[user_id] = "waiting_title"
    
    await callback_query.message.edit_text(
        "📝 **Set Custom Title**\n\n"
        "Send the title format you want for uploaded files.\n\n"
        "**Variables:**\n"
        "• `{filename}` - Original filename\n"
        "• `{ext}` - File extension\n"
        "• `{size}` - File size\n\n"
        "**Example:**\n"
        "`📥 {filename}`\n\n"
        "Send /cancel to cancel.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_setting")]
        ])
    )
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^set_thumbnail$"))
async def set_thumbnail_callback(client: Client, callback_query: CallbackQuery):
    """Set thumbnail callback"""
    user_id = callback_query.from_user.id
    
    if not await user_db.is_premium(user_id):
        return await callback_query.answer("❌ Premium only!", show_alert=True)
    
    setting_states[user_id] = "waiting_thumbnail"
    
    await callback_query.message.edit_text(
        "🖼️ **Set Custom Thumbnail**\n\n"
        "Send an image to use as thumbnail for all uploads.\n\n"
        "**Requirements:**\n"
        "• JPG/PNG format\n"
        "• Max 200KB recommended\n"
        "• Square ratio works best\n\n"
        "Send /cancel to cancel.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_setting")]
        ])
    )
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^reset_settings$"))
async def reset_settings_callback(client: Client, callback_query: CallbackQuery):
    """Reset settings callback"""
    user_id = callback_query.from_user.id
    
    if not await user_db.is_premium(user_id):
        return await callback_query.answer("❌ Premium only!", show_alert=True)
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, Reset", callback_data="confirm_reset"),
            InlineKeyboardButton("❌ No", callback_data="cancel_setting")
        ]
    ])
    
    await callback_query.message.edit_text(
        "⚠️ **Confirm Reset**\n\n"
        "Are you sure you want to reset all settings?\n"
        "This will remove:\n"
        "• Custom Chat ID\n"
        "• Custom Title\n"
        "• Custom Thumbnail",
        reply_markup=keyboard
    )
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^confirm_reset$"))
async def confirm_reset_callback(client: Client, callback_query: CallbackQuery):
    """Confirm reset callback"""
    user_id = callback_query.from_user.id
    
    await user_db.reset_settings(user_id)
    
    await callback_query.message.edit_text(
        "✅ **Settings Reset Successfully!**\n\n"
        "All your settings have been reset to default.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
        ])
    )
    await callback_query.answer("Settings reset!", show_alert=True)

@Client.on_callback_query(filters.regex("^cancel_setting$"))
async def cancel_setting_callback(client: Client, callback_query: CallbackQuery):
    """Cancel setting callback"""
    user_id = callback_query.from_user.id
    
    if user_id in setting_states:
        del setting_states[user_id]
    
    await callback_query.message.edit_text(
        "❌ **Cancelled!**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
        ])
    )
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^open_settings$"))
async def open_settings_callback(client: Client, callback_query: CallbackQuery):
    """Open settings callback"""
    user_id = callback_query.from_user.id
    
    settings = await user_db.get_settings(user_id)
    
    chat_id = settings.get("chat_id", "Not Set")
    title = settings.get("title", "Not Set")
    thumbnail = "✅ Set" if settings.get("thumbnail") else "❌ Not Set"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📍 Set Chat ID", callback_data="set_chat_id"),
            InlineKeyboardButton("📝 Set Title", callback_data="set_title")
        ],
        [
            InlineKeyboardButton("🖼️ Set Thumbnail", callback_data="set_thumbnail"),
            InlineKeyboardButton("🔄 Reset Settings", callback_data="reset_settings")
        ],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await callback_query.message.edit_text(
        f"⚙️ **Your Settings**\n\n"
        f"📍 **Chat ID:** `{chat_id}`\n"
        f"📝 **Title:** `{title if title != 'Not Set' else 'Default'}`\n"
        f"🖼️ **Thumbnail:** {thumbnail}\n\n"
        f"Click buttons below to modify:",
        reply_markup=keyboard
    )
    await callback_query.answer()

# Handle setting inputs
@Client.on_message(filters.private & ~filters.command(["start", "help", "setting", "cancel", "broadcast", "premium", "removepremium"]))
async def handle_setting_input(client: Client, message: Message):
    """Handle setting input messages"""
    user_id = message.from_user.id
    
    if user_id not in setting_states:
        return  # Not in setting mode, let other handlers process
    
    state = setting_states[user_id]
    
    if state == "waiting_chat_id":
        try:
            chat_id = int(message.text)
            await user_db.set_chat_id(user_id, chat_id)
            del setting_states[user_id]
            
            await message.reply_text(
                f"✅ **Chat ID Set!**\n\n"
                f"Files will be uploaded to: `{chat_id}`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
                ])
            )
        except ValueError:
            await message.reply_text("❌ Invalid Chat ID! Please send a valid number.")
    
    elif state == "waiting_title":
        title = message.text
        await user_db.set_title(user_id, title)
        del setting_states[user_id]
        
        await message.reply_text(
            f"✅ **Title Format Set!**\n\n"
            f"Title: `{title}`",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
            ])
        )
    
    elif state == "waiting_thumbnail":
        if message.photo:
            # Download thumbnail
            photo = await message.download()
            await user_db.set_thumbnail(user_id, photo)
            del setting_states[user_id]
            
            await message.reply_text(
                "✅ **Thumbnail Set!**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Open Settings", callback_data="open_settings")]
                ])
            )
        else:
            await message.reply_text("❌ Please send an image!")
