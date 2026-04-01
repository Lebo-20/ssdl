import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo
import logging

logger = logging.getLogger(__name__)

async def upload_progress(current, total, event, msg_text="Uploading..."):
    """Callback function for upload progress."""
    percentage = (current / total) * 100
    try:
        # Avoid flood by updating every few percentages
        if int(percentage) % 10 == 0:
            await event.edit(f"{msg_text} {percentage:.1f}%")
    except:
        pass

async def upload_drama(client: TelegramClient, chat_id: int, 
                       title: str, description: str, 
                       poster_url: str, video_path: str):
    """
    Uploads the drama information and merged video to Telegram.
    """
    try:
        # 1. Send Poster + Description
        caption = f"🎬 **{title}**\n\n📝 **Sinopsis:**\n{description[:500]}..." # Limit caption length
        
        # Send Photo with Caption
        sent_info = await client.send_file(
            chat_id,
            poster_url,
            caption=caption,
            parse_mode='html'
        )
        
        # 2. Upload Video
        # Determine if it should be document or video file
        # Telegram usually handles this, but Telethon allows specifying 'force_document'
        is_document = os.path.getsize(video_path) > 50 * 1024 * 1024 # > 50MB
        
        status_msg = await client.send_message(chat_id, "📤 Sedang mengupload video ke Telegram...")
        
        await client.send_file(
            chat_id,
            video_path,
            caption=f"🎥 Full Episode: {title}",
            force_document=is_document,
            progress_callback=lambda c, t: upload_progress(c, t, status_msg, "Upload Video:"),
            supports_streaming=True
        )
        
        await status_msg.delete()
        logger.info(f"Successfully uploaded {title} to Telegram")
        return True
    except Exception as e:
        logger.error(f"Failed to upload to Telegram: {e}")
        return False
