import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo
import logging
import httpx
import subprocess
import tempfile

logger = logging.getLogger(__name__)

async def upload_progress(current, total, event, msg_text="Uploading..."):
    """Callback function for upload progress."""
    percentage = (current / total) * 100
    try:
        # Avoid flood by updating every 10%
        if int(percentage) % 10 == 0:
            await event.edit(f"{msg_text} {percentage:.1f}%")
    except:
        pass

async def upload_drama(client: TelegramClient, chat_id: int, 
                       title: str, description: str, 
                       poster_url: str, video_path: str, retries: int = 3):
    """
    Uploads the drama information and merged video to Telegram with retry logic.
    """
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Upload Attempt {attempt}/{retries} for {title}...")
            
            # 1. Send Poster + Description (only on first attempt or if retry needed)
            caption = f"🎬 **{title}**\n\n📝 **Sinopsis:**\n{description[:800]}..."
            
            poster_path = None
            if poster_url:
                try:
                    # Increased timeout for poster download to 60s
                    async with httpx.AsyncClient(timeout=60) as http_client:
                        resp = await http_client.get(poster_url)
                        if resp.status_code == 200:
                            poster_path = os.path.join(tempfile.gettempdir(), f"poster_{attempt}_{title[:10].replace(' ','_')}.jpg")
                            with open(poster_path, "wb") as pf:
                                pf.write(resp.content)
                except Exception as e:
                    logger.warning(f"Failed to download poster (Attempt {attempt}): {e}")
            
            # Send as photo
            await client.send_file(
                chat_id,
                poster_path or poster_url or video_path, # Fallback to video path if no poster
                caption=caption,
                parse_mode='md',
                force_document=False
            )
            
            if poster_path and os.path.exists(poster_path):
                os.remove(poster_path)
            
            status_msg = await client.send_message(chat_id, "📤 Ekstraksi info video...")
            
            # 2. Extract Video Info (Duration, W, H)
            duration = 0
            width = 0
            height = 0
            try:
                ffprobe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
                output = subprocess.check_output(ffprobe_cmd, text=True).strip().split('\n')
                if len(output) >= 3:
                    width = int(output[0])
                    height = int(output[1])
                    duration = int(float(output[2]))
            except Exception as e:
                logger.warning(f"Failed to extract video info: {e}")

            # 3. Extract Thumbnail
            thumb_path = os.path.join(tempfile.gettempdir(), f"thumb_{attempt}_{os.path.basename(video_path)}.jpg")
            try:
                subprocess.run(["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:01.000", "-vframes", "1", thumb_path], capture_output=True)
                if not os.path.exists(thumb_path):
                    thumb_path = None
            except Exception as e:
                logger.warning(f"Failed to generate thumbnail: {e}")
                thumb_path = None

            await status_msg.edit(f"📤 Mengunggah video (Batch {attempt})...")
            
            video_attributes = [
                DocumentAttributeVideo(
                    duration=duration,
                    w=width,
                    h=height,
                    supports_streaming=True
                )
            ]
            
            # 4. Upload Video (Main Upload)
            # We use a very long timeout for large files if needed. 
            # Telethon handles this internally but we set it explicitly if possible.
            await client.send_file(
                chat_id,
                video_path,
                caption=f"🎥 Full Episode: {title}",
                force_document=False,
                thumb=thumb_path,
                attributes=video_attributes,
                progress_callback=lambda c, t: upload_progress(c, t, status_msg, "Upload Video:"),
                supports_streaming=True
            )
            
            await status_msg.delete()
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
                
            logger.info(f"Successfully uploaded {title} (Attempt {attempt})")
            return True # Exit function on success
            
        except Exception as e:
            logger.error(f"Error on upload attempt {attempt}: {e}")
            if attempt < retries:
                wait_time = 10 * attempt
                logger.info(f"Retrying upload in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                return False
    return False
