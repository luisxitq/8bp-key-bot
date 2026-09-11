import aiohttp
import base64
from config import PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE

BASE = (
    "https://api-m.sandbox.paypal.com"
    if PAYPAL_MODE == "sandbox"
    else "https://api-m.paypal.com"
)


async def get_access_token() -> str:
    auth = base64.b64encode(
        f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()
    ).decode()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="grant_type=client_credentials",
        ) as resp:
            data = await resp.json()
            if "access_token" not in data:
                raise Exception(f"Error obteniendo token de PayPal: {data}")
            return data["access_token"]


async def create_order(amount: float, custom_id: str) -> dict:
    """
    Crea una orden de PayPal.
    custom_id se usa para identificar al usuario y los días (user_id:days)
    """
    token = await get_access_token()

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "USD",
                    "value": f"{amount:.2f}",
                },
                "custom_id": custom_id,
            }
        ],
        "application_context": {
            "return_url": "https://t.me/",  # se puede mejorar
            "cancel_url": "https://t.me/",
            "user_action": "PAY_NOW",
            "brand_name": "8BP Keys",
        },
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as resp:
            data = await resp.json()
            if "id" not in data:
                raise Exception(f"Error creando orden PayPal: {data}")
            return data


async def capture_order(order_id: str) -> dict:
    token = await get_access_token()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        ) as resp:
            return await resp.json()
