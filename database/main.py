import asyncio
import logging
import os
from threading import Thread
from flask import Flask
from pyrogram import Client, idle
from config import Config
from database import db, user_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask app for Render port binding
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "🤖 Telegram Downloader Bot is Running!"

@flask_app.route('/health')
def health():
    return {"status": "healthy", "message": "Bot is running"}

def run_flask():
    """Run Flask server"""
    flask_app.run(host='0.0.0.0', port=Config.PORT, threaded=True)

# Create downloads directory
os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)

# Initialize Pyrogram Client
app = Client(
    name="DownloaderBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    workers=100,
    plugins=dict(root="handlers")
)

async def main():
    """Main function to start the bot"""
    
    # Connect to MongoDB
    await db.connect()
    await user_db.connect()
    
    # Start Flask in a separate thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"🌐 Flask server started on port {Config.PORT}")
    
    # Start the bot
    await app.start()
    
    bot_info = await app.get_me()
    logger.info(f"✅ Bot started: @{bot_info.username}")
    
    # Send startup message to log channel
    try:
        await app.send_message(
            Config.LOG_CHANNEL,
            f"🚀 **Bot Started Successfully!**\n\n"
            f"📛 **Bot:** @{bot_info.username}\n"
            f"🆔 **Bot ID:** `{bot_info.id}`\n"
            f"📅 **Time:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")
    
    await idle()
    
    # Cleanup
    await db.close()
    await user_db.close()
    await app.stop()

if __name__ == "__main__":
    logger.info("🚀 Starting Telegram Downloader Bot...")
    asyncio.get_event_loop().run_until_complete(main())
