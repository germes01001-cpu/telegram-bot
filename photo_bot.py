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

def get_existing_notion_titles():
    url = f"https://api.notion.com/v1/databases/{NOTION_MEDIA_DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
    existing_titles = set()
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            for page in res.get("results", []):
                props = page.get("properties", {})
                title_prop = props.get("Название Фотосессии", {}).get("title", [])
                if title_prop:
                    existing_titles.add(title_prop[0].get("text", {}).get("content", "").strip())
    except Exception as e:
        print(f"⚠️ Error al consultar títulos existentes en Notion: {e}")
    return existing_titles

def get_all_subfolders_and_files(main_url):
    results = []
    try:
        req = urllib.request.Request(main_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, context=ctx) as r:
            html = r.read().decode("utf-8", errors="ignore")
            raw_subfolders = re.findall(r"\"([A-Za-z0-9_\-]{33})\"", html)
            clean_subfolders = [s for s in set(raw_subfolders) if s != "1F4bG6AA8huu2Co7wcbF4es4yGJ15fdhX"]
            
            for sf_id in clean_subfolders:
                sf_url = f"https://drive.google.com/drive/folders/{sf_id}?usp=sharing"
                req_sf = urllib.request.Request(sf_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
                try:
                    with urllib.request.urlopen(req_sf, context=ctx) as r_sf:
                        sf_html = r_sf.read().decode("utf-8", errors="ignore")
                        titles = re.findall(r"<title>(.*?)</title>", sf_html)
                        sf_title = titles[0].replace(" - Google Drive", "").strip() if titles else f"Sesion_{sf_id[:6]}"
                        sf_title = sf_title.replace("&amp;", "&")
                        
                        file_ids = list(set(re.findall(r"\"([0-9A-Za-z_\-]{33})\"", sf_html)))
                        clean_file_ids = [f for f in file_ids if f not in ("1F4bG6AA8huu2Co7wcbF4es4yGJ15fdhX", sf_id)]
                        
                        results.append({
                            "title": sf_title,
                            "url": sf_url,
                            "file_ids": clean_file_ids
                        })
                except Exception as e_sf:
                    print(f"⚠️ Error leyendo subcarpeta {sf_id}: {e_sf}")
    except Exception as e:
        print(f"⚠️ Error al escanear carpeta principal: {e}")
    return results

def sync_subfolder_to_notion(sf_data):
    title = sf_data["title"]
    url_link = sf_data["url"]
    file_ids = sf_data["file_ids"]
    count = len(file_ids)
    
    first_thumb = f"https://drive.google.com/thumbnail?id={file_ids[0]}&sz=w400" if file_ids else ""
    
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    page_payload = {
        "parent": {"type": "database_id", "database_id": NOTION_MEDIA_DB_ID},
        "icon": {"type": "emoji", "emoji": "📸"},
        "cover": {
            "type": "external",
            "external": {"url": first_thumb}
        },
        "properties": {
            "Название Фотосессии": {
                "title": [{"type": "text", "text": {"content": title}}]
            },
            "Ссылка на Google Диск": {
                "url": url_link
            },
            "Количество Фото": {
                "number": count
            },
            "Статус": {
                "select": {"name": "Превью Готовы 📸"}
            }
        },
        "children": [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"💡 FOTO SESIÓN REAL: {title} ({count} fotos en total)"}}
                    ],
                    "icon": {"emoji": "📸"}
                }
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"🖼️ Vista previa de imágenes ({count} archivos)"}}
                    ]
                }
            }
        ]
    }
    
    data = json.dumps(page_payload).encode("utf-8")
    req_p = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req_p, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            new_page_id = res.get("id")
            
            # Batch append all visual image blocks in chunks of 20 with DIRECT SINGLE FILE VIEW/DOWNLOAD LINK!
            batch_size = 20
            for start in range(0, count, batch_size):
                chunk = file_ids[start:start+batch_size]
                batch_children = []
                for idx, f_id in enumerate(chunk):
                    global_idx = start + idx + 1
                    thumb_url = f"https://drive.google.com/thumbnail?id={f_id}&sz=w400"
                    # DIRECT VIEW LINK SPECIFICALLY FOR THIS FILE ID!
                    single_file_url = f"https://drive.google.com/file/d/{f_id}/view?usp=sharing"
                    
                    batch_children.append({
                        "object": "block",
                        "type": "image",
                        "image": {
                            "type": "external",
                            "external": {"url": thumb_url}
                        }
                    })
                    batch_children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {f"content": f"📷 Foto #{global_idx} de {count} | "}},
                                {"type": "text", "text": {"content": "📥 Открыть / Скачать именно это фото", "link": {"url": single_file_url}}}
                            ]
                        }
                    })
                
                b_data = json.dumps({"children": batch_children}).encode("utf-8")
                req_b = urllib.request.Request(url=f"https://api.notion.com/v1/blocks/{new_page_id}/children", data=b_data, headers=headers, method="PATCH")
                urllib.request.urlopen(req_b, context=ctx)
                
            return new_page_id
    except Exception as e:
        print(f"❌ Error creando sesión {title} en Notion: {e}")
        return None

def process_sync_async(chat_id):
    send_telegram_message(chat_id, "📸 *¡Escaneando tu Google Drive en tiempo real y creando galerías en Notion!...*")
    
    existing_titles = get_existing_notion_titles()
    subfolders = get_all_subfolders_and_files(MAIN_GDRIVE_URL)
    synced_names = []
    
    for sf in subfolders:
        title = sf["title"]
        if title in existing_titles:
            print(f"⏭️ Omitiendo subcarpeta existente: {title}")
            synced_names.append(f"• 📁 `{title}` ({len(sf['file_ids'])} fotos) _(Ya existente)_")
            continue
            
        p_id = sync_subfolder_to_notion(sf)
        if p_id:
            synced_names.append(f"• 📁 `{title}` ({len(sf['file_ids'])} fotos) ✨ _(Nueva)_")
            
    if synced_names:
        list_str = "\n".join(synced_names)
        report = (
            "✅ *INFORME DE SINCRONIZACIÓN AUTOMÁTICA DE FOTOS*\n\n"
            f"📊 *Total de carpetas en tu Google Drive:* `{len(subfolders)}`\n\n"
            f"{list_str}\n\n"
            "✨ *¡Todas las tarjetas reales y descargas directas están listas sin duplicados en tu Galería de Notion!*"
        )
        send_telegram_message(chat_id, report)
    else:
        send_telegram_message(chat_id, "⚠️ *No se detectaron subcarpetas en tu Google Drive.*")

def run_photo_bot():
    print("🚀 TEJA VUH Photo Sync Bot iniciado 24/7 (Modo Без дубликатов + Ссылка на конкретный файл)!")
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
                                "1. Sube tus carpetas a Google Drive `TejaVuh Photo`.\n"
                                "2. Envíame cualquier mensaje o `/sync`.\n"
                                "3. Escanearé tus carpetas y crearé las galerías sin duplicados en Notion."
                            )
                            send_telegram_message(chat_id, msg)
                            continue

                        # Trigger background processing so Telegram never timeouts
                        threading.Thread(target=process_sync_async, args=(chat_id,), daemon=True).start()

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
