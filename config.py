import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# PayPal
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID")

# Firebase (tu panel 8BP)
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL", "https://aimengine-62132-default-rtdb.firebaseio.com")

# Precios
PRICES = {
    1: float(os.getenv("PRICE_1_DAY", 2.00)),
    3: float(os.getenv("PRICE_3_DAYS", 5.00)),
    7: float(os.getenv("PRICE_7_DAYS", 10.00)),
    30: float(os.getenv("PRICE_30_DAYS", 25.00)),
}

# URL pública (para webhooks)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
