import os
import json
import time
import urllib.request
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import ssl

PHOTO_TELEGRAM_TOKEN = os.environ.get("PHOTO_TELEGRAM_TOKEN")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_MEDIA_DB_ID = os.environ.get("NOTION_MEDIA_DB_ID", "3a96154b-d436-810e-a991-ca006eab15e7")
ROOT_FOLDER_ID = "1F4bG6AA8huu2Co7wcbF4es4yGJ15fdhX"
CREDENTIALS_FILE = "google_credentials.json"

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
        print(f"❌ Error enviando a Telegram: {e}")

def get_drive_service():
    scopes = ['https://www.googleapis.com/auth/drive.readonly']
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return build('drive', 'v3', credentials=creds)

def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{NOTION_MEDIA_DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
    pages = {}
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            for page in res.get("results", []):
                page_id = page["id"]
                props = page.get("properties", {})
                url_prop = props.get("Ссылка на Google Диск", {}).get("url", "")
                if url_prop:
                    match = re.search(r'folders/([a-zA-Z0-9_-]+)', url_prop)
                    if match:
                        folder_id = match.group(1)
                        pages[folder_id] = page_id
    except Exception as e:
        print(f"⚠️ Error querying Notion: {e}")
    return pages

def archive_notion_page(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    payload = {"archived": True}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="PATCH")
    try:
        urllib.request.urlopen(req, context=ctx)
    except Exception as e:
        print(f"❌ Error archiving Notion page {page_id}: {e}")

def create_notion_page(title, folder_id, count, first_thumb):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing"
    page_payload = {
        "parent": {"type": "database_id", "database_id": NOTION_MEDIA_DB_ID},
        "icon": {"type": "emoji", "emoji": "📸"},
        "cover": {"type": "external", "external": {"url": first_thumb}} if first_thumb else None,
        "properties": {
            "Название Фотосессии": {"title": [{"type": "text", "text": {"content": title}}]},
            "Ссылка на Google Диск": {"url": folder_url},
            "Статус Обработки": {"select": {"name": "Превью Готовы 📸"}}
        },
        "children": [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": f"💡 FOTO SESIÓN REAL: {title} ({count} fotos en total)"}}],
                    "icon": {"emoji": "📸"}
                }
            }
        ]
    }
    if not page_payload["cover"]:
        del page_payload["cover"]

    data = json.dumps(page_payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("id")
    except Exception as e:
        print(f"❌ Error creating Notion page for {title}: {e}")
        return None

def append_notion_blocks(page_id, blocks):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    batch_size = 50
    for start in range(0, len(blocks), batch_size):
        chunk = blocks[start:start+batch_size]
        data = json.dumps({"children": chunk}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
        try:
            urllib.request.urlopen(req, context=ctx)
        except Exception as e:
            print(f"❌ Error appending blocks to {page_id}: {e}")

def get_folder_items(service, folder_id):
    items = []
    page_token = None
    while True:
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, thumbnailLink)",
            pageToken=page_token,
            pageSize=1000
        ).execute()
        items.extend(results.get('files', []))
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return items

def build_hierarchy(service, folder_id, folder_name, depth=2):
    items = get_folder_items(service, folder_id)
    blocks = []
    photos = []
    folders = []
    
    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            folders.append(item)
        elif item['mimeType'].startswith('image/'):
            photos.append(item)
            
    total_photos = len(photos)
    
    if depth > 1: # Don't add a header for the root session itself
        heading_type = f"heading_{min(depth, 3)}"
        blocks.append({
            "object": "block",
            "type": heading_type,
            heading_type: {
                "rich_text": [{"type": "text", "text": {"content": f"📁 {folder_name} ({len(photos)} fotos)"}}]
            }
        })
        
    for i, photo in enumerate(photos):
        thumb = photo.get('thumbnailLink', '').replace('=s220', '=w400')
        if not thumb:
            thumb = f"https://drive.google.com/thumbnail?id={photo['id']}&sz=w400"
        single_file_url = f"https://drive.google.com/file/d/{photo['id']}/view?usp=sharing"
        blocks.append({
            "object": "block",
            "type": "image",
            "image": {"type": "external", "external": {"url": thumb}}
        })
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"📷 Foto #{i+1} de {len(photos)} | "}},
                    {"type": "text", "text": {"content": "📥 Открыть / Скачать", "link": {"url": single_file_url}}}
                ]
            }
        })

    for folder in folders:
        sub_blocks, sub_photos = build_hierarchy(service, folder['id'], folder['name'], depth + 1)
        blocks.extend(sub_blocks)
        total_photos += sub_photos
        
    return blocks, total_photos

def sync_all(chat_id):
    send_telegram_message(chat_id, "📸 *Iniciando sincronización profunda de Google Drive a Notion...*")
    try:
        service = get_drive_service()
        notion_pages = get_notion_pages() # folder_id -> page_id
        
        sessions = get_folder_items(service, ROOT_FOLDER_ID)
        session_folders = [s for s in sessions if s['mimeType'] == 'application/vnd.google-apps.folder']
        current_session_ids = set([s['id'] for s in session_folders])
        
        # 1. Archive deleted sessions
        archived_count = 0
        for g_id, p_id in notion_pages.items():
            if g_id not in current_session_ids:
                archive_notion_page(p_id)
                archived_count += 1
                print(f"Archived Notion page {p_id} (Folder {g_id} not found in GDrive)")
        
        # 2. Sync active sessions
        synced_names = []
        for session in session_folders:
            s_id = session['id']
            s_name = session['name']
            
            if s_id in notion_pages:
                print(f"Session {s_name} already exists. Skipping full rebuild to avoid rate limits.")
                synced_names.append(f"• 📁 `{s_name}` _(Ya existe)_")
                continue
                
            blocks, total_photos = build_hierarchy(service, s_id, s_name, depth=1)
            
            first_thumb = ""
            for b in blocks:
                if b["type"] == "image":
                    first_thumb = b["image"]["external"]["url"]
                    break
                    
            p_id = create_notion_page(s_name, s_id, total_photos, first_thumb)
            if p_id:
                append_notion_blocks(p_id, blocks)
                synced_names.append(f"• 📁 `{s_name}` ({total_photos} fotos) ✨ _(Sincronizado)_")
                
        msg = (
            "✅ *SINCRONIZACIÓN COMPLETADA*\n\n"
            f"🗑️ Sesiones archivadas (borradas en Drive): `{archived_count}`\n"
            f"📊 Total sesiones actuales: `{len(session_folders)}`\n\n"
            + "\n".join(synced_names)
        )
        send_telegram_message(chat_id, msg)
        
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Error en sincronización: {e}")
        print(f"Error: {e}")

def process_sync_async(chat_id):
    threading.Thread(target=sync_all, args=(chat_id,), daemon=True).start()

def run_photo_bot():
    print("🚀 TEJA VUH Photo Sync Bot iniciado (Google Drive API + Subfolders + Auto-Delete)!")
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
                            send_telegram_message(chat_id, "👋 Envía /sync o cualquier texto para sincronizar.")
                        else:
                            process_sync_async(chat_id)
        except Exception as e:
            time.sleep(2)
        time.sleep(0.5)

def start_bot():
    threading.Thread(target=run_photo_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Running Health Check Server on port {port}...")
    start_bot()
    server = HTTPServer(("0.0.0.0", port), PhotoHealthHandler)
    server.serve_forever()
