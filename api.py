import httpx
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://drakula.dramabos.my.id/api/starshort"
AUTH_CODE = "A8D6AB170F7B89F2182561D3B32F390D"

async def _fetch(url: str, params: dict = None):
    """Generic fetch helper with StarShort parameter names."""
    if params is None:
        params = {}
    
    params.setdefault("locale", "id") # StarShort uses locale instead of lang
    params.setdefault("code", AUTH_CODE)
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Recursive extraction of data
            while isinstance(data, dict) and data.get("success") and "data" in data:
                data = data["data"]
            
            return data
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

async def get_home(page: int = 1):
    # StarShort doesn't have a direct /home, we use recommended or hot
    return await get_trending()

async def get_popular(page: int = 1):
    """Popular/Hot dramas."""
    url = f"{BASE_URL}/content/hot"
    return await _fetch(url, {"p": page})

async def get_top_rated(page: int = 1):
    """Top rated/Recommended dramas."""
    url = f"{BASE_URL}/content/recommended"
    return await _fetch(url, {"p": page})

async def get_trending():
    url = f"{BASE_URL}/content/trending"
    return await _fetch(url)

async def get_latest_dramas(page: int = 1):
    url = f"{BASE_URL}/content/latest"
    return await _fetch(url, {"p": page}) # StarShort uses p instead of page

async def search_dramas(query: str, page: int = 1):
    url = f"{BASE_URL}/search"
    return await _fetch(url, {"keyword": query, "p": page}) # uses keyword instead of q

async def get_drama_detail(drama_id: str):
    url = f"{BASE_URL}/show/{drama_id}"
    return await _fetch(url)

async def get_all_episodes(drama_id: str):
    """Fetches full episodes list for a given drama ID."""
    url = f"{BASE_URL}/show/{drama_id}/episodes"
    data = await _fetch(url)
    if isinstance(data, dict) and "episodes" in data:
        return data["episodes"]
    return []

async def get_watch_info(drama_id: str, episode: int):
    """Fetches video URL for a specific episode."""
    url = f"{BASE_URL}/watch/{drama_id}/{episode}"
    return await _fetch(url)
