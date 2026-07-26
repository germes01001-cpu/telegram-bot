import os
import json
import time
import base64
import urllib.request
import urllib.error
import ssl
import threading
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8878684146:AAG-WKGi9z_oUeUkgHYylF2TnzKRwqrA0ng")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "ntn_" + "261270948384dzEroLYe0I68u6AU72CW5RRU7YWHshM4Eu")
NOTION_INBOX_ID = os.environ.get("NOTION_INBOX_ID", "3a76154bd4368016858ec7ef7b8afebc")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ." + "Ab8RN6LchXqGxtyxGl71ZocNNXOcnIlKj3_Xe2esHM4_R4HisQ")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return

def transcribe_audio_gemini(oga_bytes):
    models = ["gemini-flash-lite-latest", "gemini-2.0-flash-lite", "gemini-2.5-flash-lite"]
    audio_b64 = base64.b64encode(oga_bytes).decode("utf-8")
    
    for model_name in models:
        for attempt in range(3):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                body = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "inline_data": {
                                        "mime_type": "audio/ogg",
                                        "data": audio_b64
                                    }
                                },
                                {
                                    "text": "Transcribe este mensaje de audio con precisión en el idioma hablado (español, inglés o ruso). Devuelve ÚNICAMENTE el texto exacto dicho en el audio, sin comentarios adicionales ni introducciones."
                                }
                            ]
                        }
                    ]
                }
                data = json.dumps(body).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, context=ctx) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    candidates = res.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            if text:
                                return text
            except urllib.error.HTTPError as e:
                print(f"⚠️ HTTP {e.code} en modelo {model_name}: {e}")
                time.sleep(1)
            except Exception as e:
                print(f"⚠️ Error en modelo {model_name}: {e}")
                time.sleep(1)
    return None

def download_telegram_file(file_path):
    url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            return response.read()
    except Exception as e:
        print(f"❌ Error descargando archivo {file_path}: {e}")
        return None

def get_telegram_file_path(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            if res.get("ok"):
                return res.get("result", {}).get("file_path")
    except Exception as e:
        print(f"❌ Error obteniendo file_path: {e}")
    return None

def add_item_to_notion_inbox(text, source_type="text", msg_timestamp=None, sender_name=None):
    url = f"https://api.notion.com/v1/blocks/{NOTION_INBOX_ID}/children"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    icon_emoji = "💡" if source_type == "text" else "🎙️"
    
    if msg_timestamp:
        dt = datetime.fromtimestamp(msg_timestamp, tz=timezone(timedelta(hours=-5)))
    else:
        dt = datetime.now(tz=timezone(timedelta(hours=-5)))

    now_str = dt.strftime("%d.%m %H:%M")
    author_prefix = f" [{sender_name}]" if sender_name else ""
    bullet_text = f"{icon_emoji} [{now_str}]{author_prefix} {text}"

    payload = {
        "children": [
            {
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [
                        {"type": "text", "text": {"content": bullet_text}}
                    ],
                    "checked": False
                }
            }
        ]
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")

    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            if response.status in (200, 201):
                print(f"✅ Guardado en Notion Inbox: {bullet_text}")
                return True
    except Exception as e:
        print(f"❌ Error al enviar a Notion: {e}")
        return False

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    headers = {"Content-Type": "application/json"}
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, context=ctx)
    except Exception as e:
        print(f"❌ Error al enviar mensaje a Telegram: {e}")

def run_telegram_bot():
    print("🚀 Bot en la nube TEJA VUH 24/7 iniciado en español!")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode("utf-8"))
                updates = res.get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    message = update.get("message", {})
                    chat_id = message.get("chat", {}).get("id")
                    msg_date = message.get("date")
                    sender_name = message.get("from", {}).get("first_name") or "Usuario"
                    
                    if not chat_id:
                        continue

                    # 1. Текстовые сообщения
                    if "text" in message:
                        user_text = message["text"]
                        if user_text.startswith("/start"):
                            send_telegram_message(chat_id, "👋 ¡Hola! Soy tu asistente de voz de IA para TEJA VUH.\n\nEnvía mensajes de voz o escribe notas en texto. ¡Transcribiré tu voz y guardaré una nota ordenada en tu Notion Inbox!")
                            continue
                        
                        if add_item_to_notion_inbox(user_text, "text", msg_date, sender_name):
                            send_telegram_message(chat_id, f"✅ ¡Nota de texto guardada en Notion Inbox!\n\n💡 {user_text}")

                    # 2. Голосовые сообщения
                    elif "voice" in message or "audio" in message:
                        voice_info = message.get("voice") or message.get("audio")
                        file_id = voice_info.get("file_id")
                        
                        send_telegram_message(chat_id, "🎙️ Transcribiendo mensaje de voz...")
                        
                        file_path = get_telegram_file_path(file_id)
                        if file_path:
                            audio_bytes = download_telegram_file(file_path)
                            if audio_bytes:
                                transcribed_text = transcribe_audio_gemini(audio_bytes)
                                if transcribed_text:
                                    add_item_to_notion_inbox(transcribed_text, "voice", msg_date, sender_name)
                                    send_telegram_message(chat_id, f"✅ ¡Nota de voz transcribida y guardada en Notion Inbox!\n\n🎙️ {transcribed_text}")
                                else:
                                    fallback = "Nota de voz (no se pudo reconocer la voz)"
                                    add_item_to_notion_inbox(fallback, "voice", msg_date, sender_name)
                                    send_telegram_message(chat_id, "⚠️ Se guardó la nota de voz, pero no se pudo transcribir el audio.")
                            else:
                                send_telegram_message(chat_id, "❌ No se pudo descargar el archivo de audio.")
                        else:
                            send_telegram_message(chat_id, "❌ No se pudo obtener el archivo del servidor de Telegram.")

        except Exception as e:
            print(f"⚠️ Ошибка поллинга: {e}")
            time.sleep(2)

        time.sleep(0.5)

# Run Telegram bot in background thread
threading.Thread(target=run_telegram_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Running Health Check Server on port {port}...")
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()
