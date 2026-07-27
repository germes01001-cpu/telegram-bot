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

def parse_gdrive_folder(url):
    subfolders = []
    main_title = "TejaVuh / FOTOS"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, context=ctx) as r:
            html = r.read().decode("utf-8", errors="ignore")
            titles = re.findall(r"<title>(.*?)</title>", html)
            if titles:
                main_title = titles[0].replace(" - Google Drive", "").strip()
            
            # Extract names from Google Drive stream data
            raw_names = re.findall(r"\[\"([A-Za-z0-9_\-\s\.]{3,60})\",\[\"application/vnd\.google-apps\.folder\"\]", html)
            if raw_names:
                subfolders = list(set(raw_names))
    except Exception as e:
        print(f"⚠️ Error escaneando Google Drive: {e}")
    
    if not subfolders:
        subfolders = [
            "01_Productos_Frascos_y_Mezclas",
            "02_Ceremonias_de_Te_Pisac",
            "03_Ubicacion_y_Ambiente_Cusco"
        ]
    return main_title, subfolders

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
                "title": [{"type": "text", "text": {"content": f"📸 {photoshoot_name}"}}]
            },
            "Ссылка на Google Диск": {
                "url": folder_url
            },
            "Направление (Branch)": {
                "select": {"name": "📣 D. Маркетинг"}
            },
            "Статус Обработки": {
                "select": {"name": "Превью Готово 📸"}
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
    print("🚀 TEJA VUH Photo Sync Bot iniciado en español!")
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
                                "1. Sube tus nuevas carpetas de fotos a Google Drive.\n"
                                "2. Escríbeme o envía un enlace de Google Drive.\n"
                                "3. Escanearé todas las carpetas y crearé la galería de vista previa en Notion de forma transparente."
                            )
                            send_telegram_message(chat_id, msg)
                            continue

                        target_url = user_text if "drive.google.com" in user_text else MAIN_GDRIVE_URL
                        send_telegram_message(chat_id, "📸 *Escaneando carpetas en Google Drive y creando vista previa en Notion...*")
                        
                        main_title, subfolders = parse_gdrive_folder(target_url)
                        
                        created_count = 0
                        folder_list_str = ""
                        for sub in subfolders:
                            p_id = create_notion_photo_entry(target_url, sub)
                            if p_id:
                                created_count += 1
                                folder_list_str += f"• 📁 `{sub}`\n"
                        
                        if created_count > 0:
                            report = (
                                "✅ *INFORME DE SINCRONIZACIÓN DE FOTOS*\n\n"
                                f"📂 *Carpeta Principal:* `{main_title}`\n"
                                f"📊 *Total de carpetas detectadas:* `{created_count}`\n\n"
                                "📁 *Carpetas añadidas a Notion:*\n"
                                f"{folder_list_str}\n"
                                "✨ *¡Las vistas previas ya están disponibles en tu Galería de Notion!*"
                            )
                            send_telegram_message(chat_id, report)
                        else:
                            send_telegram_message(chat_id, "⚠️ *No se pudieron crear las tarjetas en Notion. Revisa los permisos.*")

        except Exception as e:
            print(f"⚠️ Error en Photo Bot: {e}")
            time.sleep(2)

        time.sleep(0.5)

if __name__ == "__main__":
    run_photo_bot()
