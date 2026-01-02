# In download_and_upload_link function, replace the download logic:

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
        logger.info(f"⬇️ Processing: {url[:60]}...")
        
        # Use the unified download router
        success, file_path, error = await downloader.download(
            url, download_path, progress_message
        )
        
        # Check for folder marker
        if success and file_path and file_path.startswith("TERABOX_FOLDER:"):
            return False, None  # Will be handled separately
        
        if not success or not file_path:
            logger.error(f"❌ Download failed: {error}")
            await progress_message.edit_text(f"❌ **Download Failed!**\n\n`{error}`")
            await uploader.send_log(client, user_id, username, url, "Unknown", "failed", error)
            return False, None
        
        # ... rest of the upload logic remains the same
