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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8878684146:AAF7BgYn--MszhQxU3F4mx0_Qyw1YueCZIQ")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "ntn_" + "261270948384dzEroLYe0I68u6AU72CW5RRU7YWHshM4Eu")
NOTION_INBOX_ID = os.environ.get("NOTION_INBOX_ID", "3a76154bd4368016858ec7ef7b8afebc")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6JkYBUpsrDcb9G8YGHKPVjd4Km-LE1jgpsKF5Zw5fSBtA")

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
        return  # Suppress logs

def transcribe_audio_gemini(oga_bytes):
    try:
        audio_b64 = base64.b64encode(oga_bytes).decode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={GEMINI_API_KEY}"
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
                            "text": "Расшифруй это аудиосообщение на русском языке. Верни ТОЛЬКО точный текст сказанного без дополнительных комментариев."
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
                    return parts[0].get("text", "").strip()
    except Exception as e:
        print(f"❌ Ошибка расшифровки Gemini: {e}")
    return None

def download_telegram_file(file_path):
    url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            return response.read()
    except Exception as e:
        print(f"❌ Ошибка скачивания файла {file_path}: {e}")
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
        print(f"❌ Ошибка получения file_path: {e}")
    return None

def add_item_to_notion_inbox(text, source_type="text", msg_timestamp=None):
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
    bullet_text = f"{icon_emoji} [{now_str}] {text}"

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
                print(f"✅ Сохранено в Notion Inbox: {bullet_text}")
                return True
    except Exception as e:
        print(f"❌ Ошибка отправки в Notion: {e}")
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
        print(f"❌ Ошибка отправки в Telegram: {e}")

def run_telegram_bot():
    print("🚀 Облачный Бот TEJA VUH 24/7 запущен!")
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
                    
                    if not chat_id:
                        continue

                    # 1. Текстовые сообщения
                    if "text" in message:
                        user_text = message["text"]
                        if user_text.startswith("/start"):
                            send_telegram_message(chat_id, "👋 Привет! Я ваш голосовой ИИ-помощник TEJA VUH. Наговаривайте голосовые сообщения или пишите текстом — я расшифрую голос и отправлю аккуратную задачу в ваш Notion Inbox!")
                            continue
                        
                        if add_item_to_notion_inbox(user_text, "text", msg_date):
                            send_telegram_message(chat_id, f"✅ Текстовая задача сохранена в Notion Inbox!\n\n💡 {user_text}")

                    # 2. Голосовые сообщения
                    elif "voice" in message or "audio" in message:
                        voice_info = message.get("voice") or message.get("audio")
                        file_id = voice_info.get("file_id")
                        
                        send_telegram_message(chat_id, "🎙️ Расшифровываю голос...")
                        
                        file_path = get_telegram_file_path(file_id)
                        if file_path:
                            audio_bytes = download_telegram_file(file_path)
                            if audio_bytes:
                                transcribed_text = transcribe_audio_gemini(audio_bytes)
                                if transcribed_text:
                                    add_item_to_notion_inbox(transcribed_text, "voice", msg_date)
                                    send_telegram_message(chat_id, f"✅ Голосовая запись расшифрована и сохранена в Notion Inbox!\n\n🎙️ {transcribed_text}")
                                else:
                                    fallback = "Голосовая заметка (не удалось разобрать слова)"
                                    add_item_to_notion_inbox(fallback, "voice", msg_date)
                                    send_telegram_message(chat_id, "⚠️ Запись сохранена, но расшифровка не удалась.")
                            else:
                                send_telegram_message(chat_id, "❌ Не удалось скачать аудиофайл.")
                        else:
                            send_telegram_message(chat_id, "❌ Не удалось получить файл с сервера Telegram.")

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
