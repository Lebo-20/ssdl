import os
import subprocess
import logging
import time

logger = logging.getLogger(__name__)

def merge_episodes(video_dir: str, output_path: str, retries: int = 3):
    """
    Merges all .mp4 files in video_dir into a single output_path file.
    Includes retry logic for robustness.
    """
    files = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
    if not files:
        logger.error("No mp4 files found for merge.")
        return False
        
    files.sort() 
    
    list_file_path = os.path.join(video_dir, "list.txt")
    with open(list_file_path, "w") as f:
        for file in files:
            f.write(f"file '{file}'\n")

    command = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file_path,
        "-c", "copy",
        output_path
    ]
    
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"FFmpeg Merge Attempt {attempt}/{retries}...")
            
            # Execute ffmpeg
            process = subprocess.run(command, capture_output=True, text=True)
            if process.returncode == 0:
                logger.info(f"Successfully merged episodes into {output_path}")
                return True
            else:
                logger.warning(f"FFmpeg failed (Attempt {attempt}):\n{process.stderr}")
                if attempt < retries:
                    time.sleep(5)
        except Exception as e:
            logger.error(f"Logic error during merge attempt {attempt}: {e}")
            if attempt < retries:
                time.sleep(5)
                
    return False
