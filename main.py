import httpx2
from fastapi import FastAPI, Request, Response
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

app = FastAPI()

# --- CONFIGURATION (Replace with your keys) ---
GEMINI_API_KEY = "PASTE_YOUR_GEMINI_API_KEY_HERE"
WHATSAPP_TOKEN = "PASTE_YOUR_META_TEMPORARY_TOKEN_HERE"
PHONE_NUMBER_ID = "PASTE_YOUR_META_PHONE_NUMBER_ID_HERE"
VERIFY_TOKEN = "bakery_secret_123"  # You invent this password for Meta webhook setup

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=60000),
)

class CakeOrderExtraction(BaseModel):
    flavor: str = Field(description="Cake flavor, e.g., Black Forest, Chocolate Truffle, Butterscotch")
    weight_kg: float = Field(description="Weight in kg, e.g., 0.5, 1.0, 2.0")
    is_eggless: bool = Field(description="True if eggless, False otherwise")
    is_custom_design: bool = Field(description="True if photo cake, fondant, or special theme")
    message_on_cake: str = Field(description="Text to write on the cake, or 'None'")
    pickup_time: str = Field(description="Requested pickup day and time")

MENU_PRICES_PER_KG = {
    "black forest": 600,
    "pineapple": 550,
    "butterscotch": 650,
    "chocolate truffle": 800,
}

def parse_and_price_cake(message: str) -> str:
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=(
            "You are a friendly bakery assistant in Andhra Pradesh. Extract cake details from this "
            f"English or Telugu-English message:\n\n{message}"
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CakeOrderExtraction,
        ),
    )
    order = CakeOrderExtraction.model_validate_json(response.text)

    base_rate = MENU_PRICES_PER_KG.get(order.flavor.lower(), 700)
    total_price = int(base_rate * order.weight_kg) + (50 if order.is_eggless else 0)
    needs_token = order.is_custom_design or order.weight_kg >= 2.0 or total_price >= 1000
    payment_note = "₹150 UPI Token Advance required" if needs_token else "Pay at Pickup (₹0 Advance)"

    return (
        f"🎂 *Order Summary Received!*\n"
        f"• *Flavor:* {order.flavor} ({'Eggless' if order.is_eggless else 'Regular'})\n"
        f"• *Weight:* {order.weight_kg} kg\n"
        f"• *Message:* {order.message_on_cake}\n"
        f"• *Pickup:* {order.pickup_time}\n"
        f"• *Total:* ₹{total_price}\n"
        f"• *Payment:* {payment_note}\n\n"
        f"Reply *YES* to confirm your booking!"
    )

async def send_whatsapp_reply(to_number: str, text: str):
    url = f"https://facebook.com{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx2.AsyncClient() as http_client:
        await http_client.post(url, headers=headers, json=payload)

# 1. Meta Webhook Verification Endpoint (GET)
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    return Response(status_code=403)

# 2. Incoming WhatsApp Messages Endpoint (POST)
@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            msg = entry["messages"][0]
            sender_number = msg["from"]
            if msg["type"] == "text":
                user_text = msg["text"]["body"]
                reply_text = parse_and_price_cake(user_text)
                await send_whatsapp_reply(sender_number, reply_text)
    except Exception as e:
        print("Webhook Error:", e)
    return {"status": "ok"}
