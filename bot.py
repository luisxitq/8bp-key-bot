import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage

from fastapi import FastAPI, Request
import uvicorn

from config import BOT_TOKEN, ADMIN_IDS, PRICES, BASE_URL
from paypal import create_order, capture_order
from key_generator import generate_key
from firebase_db import create_license

# ====================== LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ====================== BOT ======================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Pedidos pendientes: order_id → {user_id, days}
pending_orders: dict[str, dict] = {}


# ====================== HANDLERS ======================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 Día  —  $2.00", callback_data="buy:1")],
            [InlineKeyboardButton(text="3 Días —  $5.00", callback_data="buy:3")],
            [InlineKeyboardButton(text="7 Días — $10.00", callback_data="buy:7")],
            [InlineKeyboardButton(text="30 Días — $25.00", callback_data="buy:30")],
        ]
    )
    await message.answer(
        "🔑 *8BP Key Shop*\n\n"
        "Selecciona la duración de la key que deseas comprar:\n\n"
        "Las keys se generan automáticamente y aparecen en el panel admin.",
        reply_markup=kb,
        parse_mode="Markdown",
    )


@dp.callback_query(F.data.startswith("buy:"))
async def process_buy(callback: CallbackQuery):
    try:
        days = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Opción inválida", show_alert=True)
        return

    price = PRICES.get(days)
    if price is None:
        await callback.answer("Duración no disponible", show_alert=True)
        return

    user_id = callback.from_user.id
    custom_id = f"{user_id}:{days}"

    try:
        order = await create_order(price, custom_id)
    except Exception as e:
        logger.error(f"Error creando orden PayPal: {e}")
        await callback.message.answer("❌ Error al crear el pago. Intenta de nuevo más tarde.")
        await callback.answer()
        return

    order_id = order["id"]
    pending_orders[order_id] = {"user_id": user_id, "days": days}

    # Buscamos el link de aprobación
    approve_link = None
    for link in order.get("links", []):
        if link.get("rel") == "approve":
            approve_link = link.get("href")
            break

    if not approve_link:
        await callback.message.answer("❌ No se pudo generar el link de pago.")
        await callback.answer()
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Pagar con PayPal", url=approve_link)],
            [InlineKeyboardButton(text="🔄 Ya pagué (verificar)", callback_data=f"check:{order_id}")],
        ]
    )

    await callback.message.answer(
        f"✅ *Orden creada*\n\n"
        f"⏱ Duración: *{days} días*\n"
        f"💰 Precio: *${price:.2f} USD*\n\n"
        f"Haz clic en el botón para pagar con PayPal.\n"
        f"La key se enviará automáticamente cuando el pago se confirme.",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("check:"))
async def check_payment(callback: CallbackQuery):
    order_id = callback.data.split(":")[1]
    await callback.answer(
        "El pago se confirma automáticamente por webhook.\n"
        "Si ya pagaste, espera unos segundos.",
        show_alert=True,
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        f"🔧 *Panel Admin Bot*\n\n"
        f"Pedidos pendientes en memoria: `{len(pending_orders)}`\n"
        f"Webhook URL: `{BASE_URL}/paypal-webhook`",
        parse_mode="Markdown",
    )


# ====================== WEBHOOK PAYPAL ======================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arrancamos el bot en background
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "8BP KeyBot running", "webhook": "/paypal-webhook"}


@app.post("/paypal-webhook")
async def paypal_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "invalid json"}

    event_type = data.get("event_type")
    logger.info(f"PayPal event: {event_type}")

    # Eventos que nos interesan
    if event_type in ("CHECKOUT.ORDER.APPROVED", "PAYMENT.CAPTURE.COMPLETED"):
        resource = data.get("resource", {})
        order_id = resource.get("id") or resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")

        if not order_id:
            # Intentamos sacar el order_id de otra forma
            if "supplementary_data" in resource:
                order_id = resource["supplementary_data"].get("related_ids", {}).get("order_id")

        if not order_id:
            logger.warning("No se pudo obtener order_id del webhook")
            return {"status": "no order_id"}

        # Intentamos capturar (si aún no está capturado)
        try:
            result = await capture_order(order_id)
        except Exception as e:
            logger.error(f"Error capturando orden {order_id}: {e}")
            # Puede que ya esté capturado, seguimos intentando sacar custom_id
            result = resource

        status = result.get("status")
        if status not in ("COMPLETED", "APPROVED"):
            # A veces el evento ya viene capturado
            if event_type == "PAYMENT.CAPTURE.COMPLETED":
                status = "COMPLETED"
            else:
                logger.info(f"Orden {order_id} status={status}, ignorando")
                return {"status": "ignored"}

        # Extraemos custom_id (user_id:days)
        custom_id = None
        try:
            # Diferentes lugares donde puede venir
            if "purchase_units" in result:
                custom_id = result["purchase_units"][0].get("custom_id")
            if not custom_id and "purchase_units" in resource:
                custom_id = resource["purchase_units"][0].get("custom_id")
            if not custom_id:
                custom_id = resource.get("custom_id")
        except Exception:
            pass

        if not custom_id or ":" not in str(custom_id):
            # Fallback: miramos en pending_orders
            if order_id in pending_orders:
                info = pending_orders.pop(order_id)
                user_id = info["user_id"]
                days = info["days"]
            else:
                logger.warning(f"No se encontró custom_id ni pending para {order_id}")
                return {"status": "no custom_id"}
        else:
            user_id_str, days_str = str(custom_id).split(":", 1)
            user_id = int(user_id_str)
            days = int(days_str)
            pending_orders.pop(order_id, None)

        # Generamos y guardamos la key
        key = generate_key()
        try:
            await create_license(
                key=key,
                days=days,
                note=f"Comprada por Telegram | User ID: {user_id}",
                max_devices=1,
                game_type="8ball",
            )
            logger.info(f"Key creada: {key} para user {user_id} ({days} días)")
        except Exception as e:
            logger.error(f"Error creando licencia: {e}")
            try:
                await bot.send_message(
                    user_id,
                    "❌ Hubo un error al generar tu key. Contacta al administrador con el ID de pago.",
                )
            except Exception:
                pass
            return {"status": "error creating license"}

        # Enviamos la key al usuario
        try:
            await bot.send_message(
                user_id,
                f"✅ *¡Pago confirmado!*\n\n"
                f"🔑 Tu Key:\n`{key}`\n\n"
                f"⏱ Duración: *{days} días*\n"
                f"📱 Dispositivos máximos: *1*\n\n"
                f"La key ya está activa en el panel y lista para usar.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"No se pudo enviar mensaje al usuario {user_id}: {e}")

        # Notificamos a los admins
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🛒 *Nueva venta*\n\n"
                    f"User: `{user_id}`\n"
                    f"Key: `{key}`\n"
                    f"Días: *{days}*\n"
                    f"Order: `{order_id}`",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

    return {"status": "ok"}


# ====================== MAIN ======================
if __name__ == "__main__":
    logger.info("Iniciando 8BP KeyBot...")
    logger.info(f"Webhook URL debe ser: {BASE_URL}/paypal-webhook")
    uvicorn.run(app, host="0.0.0.0", port=8000)
