import httpx
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://drakula.dramabos.my.id/api/flextv"
AUTH_CODE = "A8D6AB170F7B89F2182561D3B32F390D"

async def _fetch(url: str, params: dict = None):
    """Generic fetch helper."""
    if params is None:
        params = {}
    
    params.setdefault("lang", "id")
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
    url = f"{BASE_URL}/home"
    return await _fetch(url, {"page": page})

async def get_popular(page: int = 1):
    url = f"{BASE_URL}/popular"
    return await _fetch(url, {"page": page})

async def get_top_rated(page: int = 1):
    url = f"{BASE_URL}/top-rated"
    return await _fetch(url, {"page": page})

async def get_latest_dramas(page: int = 1):
    url = f"{BASE_URL}/latest"
    return await _fetch(url, {"page": page})

async def search_dramas(query: str, page: int = 1):
    url = f"{BASE_URL}/search"
    return await _fetch(url, {"q": query, "page": page})

async def get_drama_detail(drama_id: str):
    url = f"{BASE_URL}/detail/{drama_id}"
    return await _fetch(url)

async def get_all_episodes(drama_id: str):
    """Fetches full episodes list for a given drama ID."""
    url = f"{BASE_URL}/episodes/{drama_id}/videos"
    return await _fetch(url)
