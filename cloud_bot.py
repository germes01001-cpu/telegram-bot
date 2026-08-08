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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_INBOX_ID = os.environ.get("NOTION_INBOX_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - TEJA VUH Ideas Bot Active")

    def log_message(self, format, *args):
        return

def self_keep_alive(port):
    """Pings local health check server every 3 minutes so Render free container never sleeps."""
    time.sleep(10)
    print(f"⏰ Self-Keep-Alive active on port {port}!")
    while True:
        try:
            url = f"http://127.0.0.1:{port}/"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as response:
                pass
        except Exception as e:
            pass
        time.sleep(180)

def transcribe_audio_gemini(oga_bytes):
    models = ["gemini-flash-lite-latest", "gemini-flash-latest"]
    audio_b64 = base64.b64encode(oga_bytes).decode("utf-8")
    
    for model_name in models:
        for attempt in range(2):
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
            except Exception as e:
                time.sleep(1)
                
    return "[Error en la transcripción de audio (Gemini falló)]"

def send_telegram_message(chat_id, text):
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    headers = {"Content-Type": "application/json"}
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, context=ctx)
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

def create_notion_inbox_item(text):
    if not NOTION_API_KEY or not NOTION_INBOX_ID:
        return None
        
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # Check if text is a link
    is_link = text.startswith("http://") or text.startswith("https://")
    
    # Create an emoji based on content type
    icon_emoji = "🔗" if is_link else "📝"
    
    # Use first sentence as title, rest as body
    lines = text.split('\n', 1)
    title = lines[0][:50] + ("..." if len(lines[0]) > 50 else "")
    
    payload = {
        "parent": {"type": "database_id", "database_id": NOTION_INBOX_ID},
        "icon": {"type": "emoji", "emoji": icon_emoji},
        "properties": {
            "Имя": {
                "title": [
                    {
                        "text": {
                            "content": title
                        }
                    }
                ]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": text,
                                "link": {"url": text} if is_link else None
                            }
                        }
                    ]
                }
            }
        ]
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("url")
    except Exception as e:
        print(f"Error creando en Notion: {e}")
        return None

def download_telegram_file(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            file_path = res.get("result", {}).get("file_path")
            
            if file_path:
                dl_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
                dl_req = urllib.request.Request(dl_url)
                with urllib.request.urlopen(dl_req, context=ctx) as dl_res:
                    return dl_res.read()
    except Exception as e:
        print(f"Error descargando archivo de Telegram: {e}")
    return None

def process_update(update):
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    
    if not chat_id:
        return

    text_to_save = ""

    if "text" in message:
        text = message["text"].strip()
        if text.startswith("/start"):
            send_telegram_message(chat_id, "👋 ¡Hola! Soy el bot de captura rápida de TEJA VUH.\n\nEnvíame texto, enlaces o notas de voz y los guardaré directamente en tu bandeja de entrada de Notion (INBOX).")
            return
        else:
            text_to_save = text

    elif "voice" in message:
        send_telegram_message(chat_id, "🎙️ Transcribiendo audio...")
        file_id = message["voice"]["file_id"]
        oga_bytes = download_telegram_file(file_id)
        if oga_bytes:
            text_to_save = transcribe_audio_gemini(oga_bytes)
            send_telegram_message(chat_id, f"📝 *Transcripción:*\n_{text_to_save}_")
        else:
            send_telegram_message(chat_id, "❌ Error descargando el audio.")
            return

    if text_to_save:
        notion_url = create_notion_inbox_item(text_to_save)
        if notion_url:
            send_telegram_message(chat_id, f"✅ Guardado en Notion:\n[Abrir en Notion]({notion_url})")
        else:
            send_telegram_message(chat_id, "❌ Error guardando en Notion.")

def run_telegram_bot():
    print("🚀 TEJA VUH Ideas Bot (Voice + Text -> Notion) iniciado!")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=30"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode("utf-8"))
                updates = res.get("result", [])
                
                for update in updates:
                    offset = update["update_id"] + 1
                    # Procesar cada mensaje en un hilo separado para no bloquear
                    threading.Thread(target=process_update, args=(update,), daemon=True).start()
                    
        except Exception as e:
            time.sleep(2)
        time.sleep(1)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Running Health Check Server on port {port}...")
    
    # Iniciar bot en hilo secundario
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    
    # Keep alive para Render
    threading.Thread(target=self_keep_alive, args=(port,), daemon=True).start()

    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()
