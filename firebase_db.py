import aiohttp
from datetime import datetime, timedelta
from config import FIREBASE_DB_URL


def path_key(key: str) -> str:
    """Firebase no permite ciertos caracteres en las keys de los nodos"""
    return (
        key.replace(".", "_")
        .replace("#", "_")
        .replace("$", "_")
        .replace("[", "_")
        .replace("]", "_")
    )


async def create_license(
    key: str,
    days: int,
    note: str = "Comprada por Telegram Bot",
    max_devices: int = 1,
    game_type: str = "8ball",
) -> dict:
    """
    Crea una licencia exactamente como lo hace tu panel 8BP
    (nodo /licenses/{key})
    """
    now = datetime.utcnow()
    expires_at = (now + timedelta(days=days)).isoformat() + "Z"
    created_at = now.isoformat() + "Z"

    data = {
        "key": key,
        "status": "active",
        "game_type": game_type,
        "max_devices": max_devices,
        "note": note,
        "created_at": created_at,
        "expires_at": expires_at,
        "hwid": "",
        "devices": {},
        "features": "",
        "active_devices": 0,
    }

    url = f"{FIREBASE_DB_URL}/licenses/{path_key(key)}.json"

    async with aiohttp.ClientSession() as session:
        async with session.put(url, json=data) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                raise Exception(f"Error al guardar licencia en Firebase: {resp.status} → {text}")
            return data


async def get_license(key: str) -> dict | None:
    """Obtiene una licencia por su key (opcional, para verificaciones)"""
    url = f"{FIREBASE_DB_URL}/licenses/{path_key(key)}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data if data else None
