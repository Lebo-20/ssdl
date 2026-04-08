import os
import asyncio
import httpx
import logging
import subprocess

logger = logging.getLogger(__name__)

async def download_file(client: httpx.AsyncClient, url: str, path: str, progress_callback=None, retries: int = 5):
    """Downloads a single file with potential progress tracking for direct MP4 with retries."""
    last_error = "Unknown Error"
    for attempt in range(1, retries + 1):
        try:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get("Content-Length", 0))
                download_size = 0
                
                with open(path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
                        download_size += len(chunk)
                        if progress_callback:
                            await progress_callback(download_size, total_size)
            return True, ""
        except Exception as e:
            last_error = str(e)
            logger.error(f"Attempt {attempt}/{retries} failed for {url}: {e}")
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
            if attempt < retries:
                await asyncio.sleep(5)
    return False, last_error

async def download_hls(url: str, path: str, retries: int = 5):
    """Downloads HLS (.m3u8) stream using ffmpeg with retries."""
    last_error = "FFmpeg Error"
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"HLS Download Attempt {attempt}/{retries} for {url[:50]}...")
            command = [
                "ffmpeg", "-y", "-i", url,
                "-c", "copy", "-bsf:a", "aac_adtstoasc",
                path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return True, ""
            else:
                stderr_text = stderr.decode()
                last_error = stderr_text[:200]
                logger.warning(f"FFmpeg HLS failed (Attempt {attempt}): {last_error}")
                if os.path.exists(path):
                    try: os.remove(path)
                    except: pass
                if attempt < retries:
                    await asyncio.sleep(5)
        except Exception as e:
            last_error = str(e)
            logger.error(f"Error during HLS attempt {attempt}: {e}")
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
            if attempt < retries:
                await asyncio.sleep(5)
    return False, last_error

async def download_all_episodes(episodes, download_dir: str, semaphore_count: int = 5):
    """
    Downloads all episodes concurrently.
    Returns (success, list_of_errors)
    """
    os.makedirs(download_dir, exist_ok=True)
    semaphore = asyncio.Semaphore(semaphore_count)
    all_errors = []

    async def limited_download(client, ep):
        async with semaphore:
            ep_num_val = ep.get('episode') or 'unk'
            ep_num = str(ep_num_val).zfill(3)
            filename = f"episode_{ep_num}.mp4"
            filepath = os.path.join(download_dir, filename)
            
            url = ep.get('video_url') or ep.get('url')
            
            if not url:
                err = f"No URL found for episode {ep_num}"
                logger.error(err)
                all_errors.append(f"Ep {ep_num}: {err}")
                return False
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                return True

            success = False
            error_msg = ""
            if ".m3u8" in url.lower():
                success, error_msg = await download_hls(url, filepath)
            else:
                success, error_msg = await download_file(client, url, filepath)
            
            if success:
                logger.info(f"Downloaded {filename}")
            else:
                final_err = f"Ep {ep_num} failed: {error_msg}"
                logger.error(final_err)
                all_errors.append(final_err)
            return success

    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        results = await asyncio.gather(*(limited_download(client, ep) for ep in episodes))
        return all(results), all_errors

