import os
import json
import time
import urllib.request
import urllib.error
import ssl
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

PHOTO_TELEGRAM_TOKEN = os.environ.get("PHOTO_TELEGRAM_TOKEN", "8956431737:AAFChcOziYoqpVdSioF2OLlCN-NXE-iSZtk")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "ntn_" + "261270948384dzEroLYe0I68u6AU72CW5RRU7YWHshM4Eu")
NOTION_MEDIA_DB_ID = os.environ.get("NOTION_MEDIA_DB_ID", "3a96154b-d436-810e-a991-ca006eab15e7")
MAIN_GDRIVE_URL = "https://drive.google.com/drive/folders/1F4bG6AA8huu2Co7wcbF4es4yGJ15fdhX?usp=sharing"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class PhotoHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"TEJA VUH Photo Sync Engine is Active!")

    def log_message(self, format, *args):
        return

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{PHOTO_TELEGRAM_TOKEN}/sendMessage"
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
        print(f"❌ Error enviando a Telegram Photo Bot: {e}")

def fetch_real_gdrive_title(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, context=ctx) as r:
            html = r.read().decode("utf-8", errors="ignore")
            titles = re.findall(r"<title>(.*?)</title>", html)
            if titles:
                clean_title = titles[0].replace(" - Google Drive", "").strip()
                return clean_title
    except Exception as e:
        print(f"⚠️ Error leyendo Google Drive: {e}")
    return "TejaVuh / FOTOS"

def create_notion_photo_entry(folder_url, photoshoot_name):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    payload = {
        "parent": {"type": "database_id", "database_id": NOTION_MEDIA_DB_ID},
        "icon": {"type": "emoji", "emoji": "📸"},
        "properties": {
            "Название Фотосессии": {
                "title": [{"type": "text", "text": {"content": photoshoot_name}}]
            },
            "Ссылка на Google Диск": {
                "url": folder_url
            },
            "Направление (Branch)": {
                "select": {"name": "📣 D. Маркетинг"}
            },
            "Статус Обработки": {
                "select": {"name": "Загружено на Google Диск 📁"}
            }
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("id")
    except Exception as e:
        print(f"❌ Error en Notion Media DB: {e}")
        return None

def run_photo_bot():
    print("🚀 TEJA VUH Photo Sync Bot iniciado en español (Modo Limpio)!")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{PHOTO_TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode("utf-8"))
                updates = res.get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    message = update.get("message", {})
                    chat_id = message.get("chat", {}).get("id")
                    
                    if not chat_id:
                        continue

                    if "text" in message:
                        user_text = message["text"].strip()
                        
                        if user_text.startswith("/start") or user_text.startswith("/help"):
                            msg = (
                                "👋 *¡Hola! Soy tu Bot Oficial de Fotos para TEJA VUH.*\n\n"
                                "📸 *¿Cómo trabajar conmigo?:*\n"
                                "1. Sube tu carpeta de fotos a tu Google Drive `TejaVuh Photo`.\n"
                                "2. Envíame un mensaje o comando.\n"
                                "3. Sincronizaré tu carpeta real exactamente en Notion."
                            )
                            send_telegram_message(chat_id, msg)
                            continue

                        target_url = user_text if "drive.google.com" in user_text else MAIN_GDRIVE_URL
                        send_telegram_message(chat_id, "📸 *Sincronizando tu carpeta real de Google Drive en Notion...*")
                        
                        real_title = fetch_real_gdrive_title(target_url)
                        
                        p_id = create_notion_photo_entry(target_url, real_title)
                        
                        if p_id:
                            report = (
                                "✅ *INFORME DE SINCRONIZACIÓN REAL*\n\n"
                                f"📂 *Carpeta Principal:* `{real_title}`\n"
                                "📊 *Total de carpetas sincronizadas:* `1` (Real)\n\n"
                                "📁 *Carpeta añadida a Notion:*\n"
                                f"• 📁 `{real_title}`\n\n"
                                "✨ *¡La tarjeta real ya está creada en tu Galería de Notion!*"
                            )
                            send_telegram_message(chat_id, report)
                        else:
                            send_telegram_message(chat_id, "⚠️ *No se pudo crear la tarjeta en Notion. Revisa los permisos.*")

        except Exception as e:
            print(f"⚠️ Error en Photo Bot: {e}")
            time.sleep(2)

        time.sleep(0.5)

# Run polling loop in background thread
threading.Thread(target=run_photo_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Running Health Check Server on port {port}...")
    server = HTTPServer(("0.0.0.0", port), PhotoHealthHandler)
    server.serve_forever()
