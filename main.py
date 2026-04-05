import os
import asyncio
import logging
import shutil
import tempfile
import random
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv

load_dotenv()

# Local imports
from api import (
    get_drama_detail, get_all_episodes, get_latest_dramas,
    get_popular, get_top_rated, search_dramas, get_watch_info
)
from downloader import download_all_episodes
from merge import merge_episodes
from uploader import upload_drama

# Configuration (Use environment variables or replace these directly)
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
AUTO_CHANNEL = int(os.environ.get("AUTO_CHANNEL", ADMIN_ID)) # Default post to admin
PROCESSED_FILE = "processed.json"

# Initialize state
def load_processed():
    if os.path.exists(PROCESSED_FILE):
        import json
        with open(PROCESSED_FILE, "r") as f:
            try:
                return set(json.load(f))
            except:
                return set()
    return set()

def save_processed(data):
    import json
    with open(PROCESSED_FILE, "w") as f:
        json.dump(list(data), f)

processed_ids = load_processed()

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Bot State
class BotState:
    is_auto_running = True
    is_processing = False

# Initialize client
client = TelegramClient('dramabox_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

def get_panel_buttons():
    status_text = "🟢 RUNNING" if BotState.is_auto_running else "🔴 STOPPED"
    return [
        [Button.inline("▶️ Start Auto", b"start_auto"), Button.inline("⏹ Stop Auto", b"stop_auto")],
        [Button.inline(f"📊 Status: {status_text}", b"status")]
    ]

@client.on(events.NewMessage(pattern='/update'))
async def update_bot(event):
    if event.sender_id != ADMIN_ID:
        return
    import subprocess
    import sys
    
    status_msg = await event.reply("🔄 Menarik pembaruan dari GitHub...")
    try:
        # Run git pull
        result = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True)
        await status_msg.edit(f"✅ Repositori berhasil di-pull:\n```\n{result.stdout}\n```\n\nSedang memulai ulang sistem (Restarting)...")
        
        # Restart the script forcefully replacing the current process image
        os.execl(sys.executable, sys.executable, *sys.argv)
    except Exception as e:
        await status_msg.edit(f"❌ Gagal melakukan update: {e}")

@client.on(events.NewMessage(pattern='/panel'))
async def panel(event):
    if event.chat_id != ADMIN_ID:
        return
    await event.reply("🎛 **StarShort Control Panel**", buttons=get_panel_buttons())

@client.on(events.CallbackQuery())
async def panel_callback(event):
    if event.sender_id != ADMIN_ID:
        return
        
    data = event.data
    
    try:
        if data == b"start_auto":
            BotState.is_auto_running = True
            await event.answer("Auto-mode started!")
            await event.edit("🎛 **StarShort Control Panel**", buttons=get_panel_buttons())
        elif data == b"stop_auto":
            BotState.is_auto_running = False
            await event.answer("Auto-mode stopped!")
            await event.edit("🎛 **StarShort Control Panel**", buttons=get_panel_buttons())
        elif data == b"status":
            await event.answer(f"Status: {'Running' if BotState.is_auto_running else 'Stopped'}")
            await event.edit("🎛 **StarShort Control Panel**", buttons=get_panel_buttons())
    except Exception as e:
        if "message is not modified" in str(e).lower() or "Message string and reply markup" in str(e):
            pass # Ignore if button is already in that state
        else:
            logger.error(f"Callback error: {e}")

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Welcome to StarShort Downloader Bot! 🎉\n\nGunakan perintah `/download {ID}` untuk mendownload, atau `/cari {judul}` untuk mencari drama.")

@client.on(events.NewMessage(pattern=r'/cari (.+)'))
async def on_search(event):
    if event.sender_id != ADMIN_ID:
        return
        
    query = event.pattern_match.group(1).strip()
    status_msg = await event.reply(f"🔍 Mencari drama untuk judul: **{query}**...")
    
    results = await search_dramas(query)
    if results is None:
        await status_msg.edit(f"❌ Error saat mengakses API untuk: `{query}`.")
        return
        
    # StarShort search response is usually a list
    dramas = results if isinstance(results, list) else results.get("data", []) if isinstance(results, dict) else []
    
    if not dramas:
        await status_msg.edit(f"❌ Tidak ditemukan hasil untuk: `{query}`.")
        return
        
    text = f"🔍 **Hasil Pencarian StarShort:** `{query}`\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, d in enumerate(dramas[:15]): 
        title = d.get('title') or d.get('bookName') or d.get('name', 'Tanpa Judul')
        id_ = d.get('id') or d.get('bookId') or d.get('bookid', '???')
        text += f"{i+1}. **{title}**\n   └ ID: `/download {id_}`\n\n"
        
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "💡 *Tip: Klik pada perintah /download di atas untuk menyalin ID.*"
    await status_msg.edit(text)

@client.on(events.NewMessage(pattern=r'/download (\w+)'))
async def on_download(event):
    chat_id = event.chat_id
    
    # Check admin
    if chat_id != ADMIN_ID:
        await event.reply("❌ Maaf, perintah ini hanya untuk admin.")
        return
        
    if BotState.is_processing:
        await event.reply("⚠️ Sedang memproses drama lain. Tunggu hingga selesai.")
        return
        
    book_id = event.pattern_match.group(1)
    
    # 1. Fetch data
    detail = await get_drama_detail(book_id)
    if not detail:
        await event.reply(f"❌ Gagal mendapatkan detail drama `{book_id}`.")
        return
        
    episodes_list = await get_all_episodes(book_id) # Only numbers and price
    if not episodes_list:
        await event.reply(f"❌ Drama `{book_id}` tidak memiliki episode.")
        return
    
    title = detail.get("title") or detail.get("bookName") or detail.get("name") or f"Drama_{book_id}"
    
    status_msg = await event.reply(f"🎬 Drama: **{title}**\n📽 Total Episodes: {len(episodes_list)}\n\n⏳ Sedang mengambil info video dan download...")
    
    BotState.is_processing = True
    processed_ids.add(book_id)
    save_processed(processed_ids)
    
    await process_drama_full(book_id, chat_id, status_msg)
    BotState.is_processing = False

async def process_drama_full(book_id, chat_id, status_msg=None):
    """Common drama processing logic updated for StarShort."""
    detail = await get_drama_detail(book_id)
    raw_episodes = await get_all_episodes(book_id)
    
    if not detail or not raw_episodes:
        if status_msg: await status_msg.edit(f"❌ Detail atau Episode `{book_id}` tidak ditemukan.")
        return False

    title = detail.get("title") or detail.get("bookName") or detail.get("name") or f"Drama_{book_id}"
    description = detail.get("description") or detail.get("intro") or detail.get("introduction") or "No description available."
    poster = detail.get("cover") or detail.get("coverWap") or detail.get("poster") or ""
    
    # Setup temp directory
    temp_dir = tempfile.mkdtemp(prefix=f"starshort_{book_id}_")
    video_dir = os.path.join(temp_dir, "episodes")
    os.makedirs(video_dir, exist_ok=True)
    
    try:
        # Pre-fetch watch info for all episodes
        if status_msg: await status_msg.edit(f"🔍 Merangkum info video untuk **{title}**...")
        
        full_episodes = []
        for ep in raw_episodes:
            ep_num = ep.get("episode")
            watch_info = await get_watch_info(book_id, ep_num)
            if watch_info and watch_info.get("video_url"):
                full_episodes.append({
                    "episode": ep_num,
                    "video_url": watch_info["video_url"]
                })
        
        if not full_episodes:
            if status_msg: await status_msg.edit("❌ Gagal mengambil URL video episode.")
            return False
            
        if status_msg: await status_msg.edit(f"🎬 Men-download {len(full_episodes)} episode **{title}**...")
        
        # Download
        success = await download_all_episodes(full_episodes, video_dir)
        if not success:
            if status_msg: await status_msg.edit("❌ Download Gagal.")
            return False

        # Merge
        output_video_path = os.path.join(temp_dir, f"{title}.mp4")
        merge_success = merge_episodes(video_dir, output_video_path)
        if not merge_success:
            if status_msg: await status_msg.edit("❌ Merge Gagal.")
            return False

        # Upload
        upload_success = await upload_drama(
            client, chat_id, 
            title, description, 
            poster, output_video_path
        )
        
        if upload_success:
            if status_msg: await status_msg.delete()
            return True
        else:
            if status_msg: await status_msg.edit("❌ Upload Gagal.")
            return False
            
    except Exception as e:
        logger.error(f"Error processing {book_id}: {e}")
        if status_msg: await status_msg.edit(f"❌ Error: {e}")
        return False
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

async def auto_mode_loop():
    """Auto scanner using StarShort endpoints."""
    global processed_ids
    logger.info("🚀 StarShort Auto-Mode Monitoring Started.")
    
    is_initial_run = True
    while True:
        if not BotState.is_auto_running:
            await asyncio.sleep(5)
            continue
            
        try:
            interval = 5 if is_initial_run else 15
            logger.info(f"🔍 Scanning StarShort (Next scan in {interval}m)...")
            
            # Combine latest, hot, recommended and trending
            all_potential = []
            
            async def safe_fetch(coro):
                try:
                    res = await coro
                    if isinstance(res, list): return res
                    if isinstance(res, dict): return res.get("data", [])
                    return []
                except Exception as e:
                    logger.error(f"Fetch error: {e}")
                    return []

            # Fetch page 1 and 2 for each category to get more content
            categories = [
                get_latest_dramas(page=1),
                get_latest_dramas(page=2),
                get_popular(page=1),
                get_popular(page=2),
                get_top_rated(page=1),
                get_top_rated(page=2),
                get_trending()
            ]

            results = await asyncio.gather(*[safe_fetch(cat) for cat in categories])
            
            combined = []
            seen_ids = set()
            for res_list in results:
                for d in res_list:
                    bid = str(d.get("id") or d.get("bookId") or d.get("bookid", ""))
                    if bid and bid not in seen_ids:
                        combined.append(d)
                        seen_ids.add(bid)
            
            new_found_list = []
            for d in combined:
                bid = str(d.get("id") or d.get("bookId") or d.get("bookid", ""))
                if bid and bid not in processed_ids:
                    new_found_list.append(d)

            random.shuffle(new_found_list)
            
            if not new_found_list:
                logger.info("ℹ️ No new dramas found in this scan.")
            
            for drama in new_found_list:
                if not BotState.is_auto_running:
                    break
                    
                book_id = str(drama.get("id") or drama.get("bookId") or drama.get("bookid", ""))
                title = drama.get("title") or drama.get("bookName") or "Unknown"
                
                # Mark as processed immediately to avoid re-trying on failure
                processed_ids.add(book_id)
                save_processed(processed_ids)
                
                logger.info(f"✨ StarShort Discovery: {title} ({book_id}). Starting process...")
                
                try:
                    await client.send_message(ADMIN_ID, f"🆕 **Auto-System StarShort: Drama Baru!**\n🎬 `{title}`\n🆔 `{book_id}`\n⏳ Memproses video...")
                except: pass
                
                BotState.is_processing = True
                success = await process_drama_full(book_id, AUTO_CHANNEL)
                BotState.is_processing = False
                
                if success:
                    logger.info(f"✅ Finished {title}")
                    try:
                        await client.send_message(ADMIN_ID, f"✅ Sukses Auto-Post StarShort: **{title}**.")
                    except: pass
                else:
                    logger.error(f"❌ Failed to process {title}")
                    # DO NOT stop auto-mode anymore. Just log and notify.
                    try:
                        await client.send_message(ADMIN_ID, f"⚠️ **Gagal Auto-Post**: `{title}` (ID: `{book_id}`).\nMelanjutkan ke drama berikutnya...")
                    except: pass
                    # continue to next drama
                    
                await asyncio.sleep(15) 
                
            is_initial_run = False
            for _ in range(interval * 60):
                if not BotState.is_auto_running: break
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"⚠️ Error in auto loop: {e}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    logger.info("Initializing StarShort Auto-Bot...")
    client.loop.create_task(auto_mode_loop())
    logger.info("Bot is active.")
    client.run_until_disconnected()
