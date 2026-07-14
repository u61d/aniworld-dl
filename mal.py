import requests
from typing import Optional, Dict


class MALClient:
    BASE_URL = "https://api.jikan.moe/v4"

    def __init__(self):
        self.session = requests.Session()

    def search_anime(self, query: str) -> Optional[Dict[str, str]]:
        try:
            res = self.session.get(
                f"{self.BASE_URL}/anime", params={"q": query, "limit": 10}, timeout=10
            )
            res.raise_for_status()
            data = res.json()

            if not data.get("data"):
                return None

            # prefer tv types with multiple episodes
            for anime in data["data"]:
                if anime["type"] == "TV" and anime.get("episodes", 0) > 1:
                    return {
                        "status": anime.get("status", "Unknown"),
                        "aired": anime.get("aired", {}).get("string", "Unknown"),
                        "rating": anime.get("rating", "Unknown"),
                    }

            # fallback to the first result if no main series found
            anime = data["data"][0]
            return {
                "status": anime.get("status", "Unknown"),
                "aired": anime.get("aired", {}).get("string", "Unknown"),
                "rating": anime.get("rating", "Unknown"),
            }

        except Exception:
            return None
