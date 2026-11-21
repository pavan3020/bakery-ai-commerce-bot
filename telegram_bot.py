import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import database

# --- 1. LOAD ENVIRONMENT VARIABLES FROM .env ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "0"))

# Initialize Cloud PostgreSQL (Supabase) or local SQLite
database.init_db()

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=60000),
)

PENDING_CARTS = {}

# --- 2. STRUCTURED AI SCHEMA ---
class CakeOrderExtraction(BaseModel):
    flavor: str = Field(description="Cake flavor, e.g., Black Forest, Chocolate Truffle, Butterscotch")
    weight_kg: float = Field(description="Weight in kg, e.g., 0.5, 1.0, 2.0")
    is_eggless: bool = Field(description="True if customer asked for eggless, False otherwise")
    is_custom_design: bool = Field(description="True if photo cake, fondant, or special theme design")
    message_on_cake: str = Field(description="Text to write on the cake, or 'None' if not specified")
    pickup_time: str = Field(description="Requested pickup day and time")

MENU_PRICES_PER_KG = {
    "black forest": 600,
    "pineapple": 550,
    "butterscotch": 650,
    "chocolate truffle": 800,
}

MODELS_TO_TRY = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"]

def analyze_cake_order(message: str, is_trusted: bool) -> dict | None:
    response = None
    for model_name in MODELS_TO_TRY:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=(
                    "You are a friendly bakery assistant in Andhra Pradesh. Extract cake details from this "
                    f"English or Telugu-English message accurately:\n\n{message}"
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CakeOrderExtraction,
                ),
            )
            break
        except Exception as e:
            print(f"{model_name} busy ({e}), trying fallback...")

    if response is None:
        return None

    order = CakeOrderExtraction.model_validate_json(response.text)
    base_rate = MENU_PRICES_PER_KG.get(order.flavor.lower(), 700)
    total_price = int(base_rate * order.weight_kg) + (50 if order.is_eggless else 0)

    needs_token = (
        not is_trusted
        and (order.is_custom_design or order.weight_kg >= 2.0 or total_price >= 1000)
    )
    advance_amount = 150 if needs_token else 0

    return {
        **order.model_dump(),
        "total_price": total_price,
        "advance_amount": advance_amount,
    }

# --- 3. TELEGRAM COMMANDS & HANDLERS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to Our Bakery AI Assistant!*\n\n"
        "Type your cake order naturally in *English or Telugu-English*.\n"
        "_Example:_ `1kg chocolate truffle eggless kavali Sunday 6pm ki, write Happy Birthday Ravi`\n\n"
        "_(Owner Mobile Command: type /orders to see today's kitchen queue)_",
        parse_mode="Markdown",
    )

async def owner_orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != OWNER_CHAT_ID:
        await update.message.reply_text("⛔ Unauthorized: Owner access only.")
        return

    orders = database.get_active_orders()
    if not orders:
        await update.message.reply_text("📋 No confirmed orders in the queue yet.")
        return

    lines = ["📋 *Active Kitchen Queue (Mobile Dashboard)*\n━━━━━━━━━━━━━━━━━━━━"]
    for o in orders:
        code, cust, flavor, wt, eggless, msg, pickup, total, adv = o
        lines.append(
            f"• *{code}* | {flavor} ({wt}kg, {'Eggless' if eggless else 'Reg'})\n"
            f"  ✍️ _{msg}_ | ⏰ {pickup}\n"
            f"  👤 {cust} | 💰 ₹{total} (Adv: ₹{adv})"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    customer_name = update.effective_user.first_name or "Customer"
    user_text = update.message.text.strip()

    if user_text.upper() == "CONFIRM":
        cart = PENDING_CARTS.pop(chat_id, None)
        if not cart:
            await update.message.reply_text("You don't have a pending order. Type your cake request first!")
            return

        order_code = database.save_confirmed_order(chat_id, customer_name, cart)

        await update.message.reply_text(
            f"🎉 *Booking Confirmed! Order ID: {order_code}*\n"
            f"We'll send a reminder 2 hours before *{cart['pickup_time']}*.\n"
            f"_(You are now a Verified Regular—future custom orders require ₹0 advance!)_",
            parse_mode="Markdown",
        )

        owner_alert = (
            f"🔔 *NEW CAKE ORDER ({order_code})*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Customer:* {customer_name}\n"
            f"🎂 *Cake:* {cart['flavor']} ({cart['weight_kg']} kg, {'Eggless 🟢' if cart['is_eggless'] else 'Regular'})\n"
            f"✍️ *Write:* {cart['message_on_cake']}\n"
            f"⏰ *Pickup:* {cart['pickup_time']}\n"
            f"💰 *Bill:* ₹{cart['total_price']} | *Advance:* ₹{cart['advance_amount']}"
        )
        await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=owner_alert, parse_mode="Markdown")
        return

    await update.message.reply_text("⏳ _Checking menu & calculating price..._", parse_mode="Markdown")
    trusted = database.is_trusted_customer(chat_id)
    order_data = analyze_cake_order(user_text, trusted)

    if not order_data:
        await update.message.reply_text("⚠️ AI is momentarily busy—please try again in 15 seconds!")
        return

    PENDING_CARTS[chat_id] = order_data

    if trusted:
        payment_note = "🌟 *Trusted Regular Perk: Pay at Pickup (₹0 Advance)*"
    elif order_data["advance_amount"] > 0:
        payment_note = f"💳 *₹{order_data['advance_amount']} UPI Token Required* (Custom / High-Value Cake)"
    else:
        payment_note = "✅ *Pay at Pickup (₹0 Advance)*"

    summary = (
        f"🎂 *Cake Order Summary*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Flavor:* {order_data['flavor']} ({'Eggless 🟢' if order_data['is_eggless'] else 'Regular'})\n"
        f"• *Weight:* {order_data['weight_kg']} kg\n"
        f"• *Message:* {order_data['message_on_cake']}\n"
        f"• *Pickup:* {order_data['pickup_time']}\n"
        f"• *Total:* ₹{order_data['total_price']}\n"
        f"• *Payment:* {payment_note}\n\n"
        f"Reply *CONFIRM* to lock in your order!"
    )
    await update.message.reply_text(summary, parse_mode="Markdown")

# --- 4. HEALTH SERVER FOR 24/7 RENDER CLOUD HOSTING ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bakery AI Bot is Healthy!")

def start_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

if __name__ == "__main__":
    print("🤖 Bakery Bot (Cloud PostgreSQL + Render Ready) is LIVE!")
    threading.Thread(target=start_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("orders", owner_orders_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
