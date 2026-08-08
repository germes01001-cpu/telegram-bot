import os
import json
import time
import urllib.request
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import re
import ssl
import traceback

# Try to import Google API libraries
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

PHOTO_TELEGRAM_TOKEN = os.environ.get("PHOTO_TELEGRAM_TOKEN")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_MEDIA_DB_ID = os.environ.get("NOTION_MEDIA_DB_ID", "3a96154b-d436-810e-a991-ca006eab15e7")
ROOT_FOLDER_ID = "1F4bG6AA8huu2Co7wcbF4es4yGJ15fdhX"
CREDENTIALS_FILE = "google_credentials.json"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ============================================================
# GLOBAL DEBUG CHAT ID — used to send errors to Telegram
# ============================================================
DEBUG_CHAT_ID = None

class PhotoHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"TEJA VUH Photo Sync Engine is Active!")

    def log_message(self, format, *args):
        return

def send_telegram_message(chat_id, text):
    if not chat_id or not PHOTO_TELEGRAM_TOKEN:
        print(f"Cannot send telegram: chat_id={chat_id}, token={'SET' if PHOTO_TELEGRAM_TOKEN else 'MISSING'}")
        return
    url = f"https://api.telegram.org/bot{PHOTO_TELEGRAM_TOKEN}/sendMessage"
    headers = {"Content-Type": "application/json"}
    # Truncate if too long for Telegram (max 4096 chars)
    if len(text) > 4000:
        text = text[:4000] + "\n... (обрезано)"
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
        # If markdown fails, try without parse_mode
        payload["parse_mode"] = None
        del payload["parse_mode"]
        payload["text"] = text.replace("*", "").replace("`", "").replace("_", "")
        data = json.dumps(payload).encode("utf-8")
        req2 = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            urllib.request.urlopen(req2, context=ctx)
        except Exception as e2:
            print(f"FATAL: Cannot send to Telegram at all: {e2}")

def send_debug(text):
    """Send debug/error message to Telegram"""
    global DEBUG_CHAT_ID
    if DEBUG_CHAT_ID:
        send_telegram_message(DEBUG_CHAT_ID, text)
    print(text)

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
        error_detail = ""
        try:
            error_detail = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
        except:
            error_detail = str(e)
        send_debug(f"ERROR get_notion_pages: {error_detail}")
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
        error_detail = ""
        try:
            error_detail = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
        except:
            error_detail = str(e)
        send_debug(f"ERROR archive page {page_id}: {error_detail}")

def create_notion_page(title, folder_id, count, first_thumb):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing"
    
    # Build properties — only title and URL (minimal, safe)
    properties = {
        "Название Фотосессии": {"title": [{"type": "text", "text": {"content": title}}]},
        "Ссылка на Google Диск": {"url": folder_url}
    }
    
    page_payload = {
        "parent": {"type": "database_id", "database_id": NOTION_MEDIA_DB_ID},
        "icon": {"type": "emoji", "emoji": "📸"},
        "properties": properties,
        "children": [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": f"FOTO SESSION: {title} ({count} fotos en total)"}}],
                    "icon": {"emoji": "📸"}
                }
            }
        ]
    }
    
    # Only add cover if we have a valid thumbnail
    if first_thumb and first_thumb.startswith("http"):
        page_payload["cover"] = {"type": "external", "external": {"url": first_thumb}}

    data = json.dumps(page_payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            page_id = res.get("id")
            send_debug(f"OK Created page: {title} (id: {page_id})")
            return page_id
    except Exception as e:
        error_detail = ""
        try:
            error_detail = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
        except:
            error_detail = str(e)
        send_debug(f"ERROR creating page '{title}': {error_detail}")
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
            error_detail = ""
            try:
                error_detail = e.read().decode("utf-8") if hasattr(e, 'read') else str(e)
            except:
                error_detail = str(e)
            send_debug(f"ERROR appending blocks batch {start}: {error_detail}")

def get_folder_items(service, folder_id):
    items = []
    page_token = None
    while True:
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, thumbnailLink, webContentLink)",
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
    photos = []
    folders = []
    
    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            folders.append(item)
        elif item['mimeType'].startswith('image/'):
            photos.append(item)
            
    # Process subfolders recursively first
    sub_blocks = []
    total_sub_photos = 0
    for folder in folders:
        s_blocks, s_photos = build_hierarchy(service, folder['id'], folder['name'], depth + 1)
        sub_blocks.extend(s_blocks)
        total_sub_photos += s_photos
        
    total_photos = len(photos) + total_sub_photos
    
    # Skip empty folder branches
    if total_photos == 0 and depth > 1:
        return [], 0
        
    blocks = []
    
    # Generate heading with correct total
    if depth > 1:
        heading_type = f"heading_{min(depth, 3)}"
        prefix = "📁 " if depth == 2 else ("📂 " if depth == 3 else "📄 ")
        blocks.append({
            "object": "block",
            "type": heading_type,
            heading_type: {
                "rich_text": [{"type": "text", "text": {"content": f"{prefix}{folder_name} ({total_photos} fotos)"}}]
            }
        })
        
    for i, photo in enumerate(photos):
        web_link = photo.get('webContentLink', '')
        thumb = web_link if web_link else f"https://drive.google.com/uc?export=download&id={photo['id']}"
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
                    {"type": "text", "text": {"content": f"Foto #{i+1} de {len(photos)} en {folder_name} | "}},
                    {"type": "text", "text": {"content": "Abrir / Descargar", "link": {"url": single_file_url}}}
                ]
            }
        })

    # Add subfolder blocks
    blocks.extend(sub_blocks)
        
    return blocks, total_photos

def sync_all(chat_id):
    global DEBUG_CHAT_ID
    DEBUG_CHAT_ID = chat_id
    
    # ============================================================
    # STEP 0: Pre-flight checks
    # ============================================================
    checks = []
    checks.append(f"NOTION_API_KEY: {'SET' if NOTION_API_KEY else 'MISSING'}")
    checks.append(f"PHOTO_TELEGRAM_TOKEN: {'SET' if PHOTO_TELEGRAM_TOKEN else 'MISSING'}")
    checks.append(f"NOTION_MEDIA_DB_ID: {NOTION_MEDIA_DB_ID}")
    checks.append(f"ROOT_FOLDER_ID: {ROOT_FOLDER_ID}")
    checks.append(f"google_credentials.json exists: {os.path.exists(CREDENTIALS_FILE)}")
    checks.append(f"Google API libs available: {GOOGLE_API_AVAILABLE}")
    
    send_telegram_message(chat_id, "DIAGNOSTICS - Pre-flight:\n" + "\n".join(checks))
    
    if not NOTION_API_KEY:
        send_telegram_message(chat_id, "FATAL: NOTION_API_KEY is not set in Environment Variables on Render!")
        return
    if not GOOGLE_API_AVAILABLE:
        send_telegram_message(chat_id, "FATAL: Google API libraries not installed! Check requirements.txt")
        return
    if not os.path.exists(CREDENTIALS_FILE):
        send_telegram_message(chat_id, "FATAL: google_credentials.json not found! Add it as Secret File on Render.")
        return
    
    send_telegram_message(chat_id, "Starting sync...")
    
    try:
        # ============================================================
        # STEP 1: Connect to Google Drive
        # ============================================================
        service = get_drive_service()
        send_telegram_message(chat_id, "OK: Connected to Google Drive API")
        
        # ============================================================
        # STEP 2: Read existing Notion pages
        # ============================================================
        notion_pages = get_notion_pages()
        send_telegram_message(chat_id, f"OK: Found {len(notion_pages)} existing pages in Notion DB\nFolder IDs: {list(notion_pages.keys())}")
        
        # ============================================================
        # STEP 3: Read Google Drive folders
        # ============================================================
        sessions = get_folder_items(service, ROOT_FOLDER_ID)
        session_folders = [s for s in sessions if s['mimeType'] == 'application/vnd.google-apps.folder']
        current_session_ids = set([s['id'] for s in session_folders])
        
        folder_info = [f"  {s['name']} (id: {s['id'][:12]}...)" for s in session_folders]
        send_telegram_message(chat_id, f"OK: Found {len(session_folders)} folders on Google Drive:\n" + "\n".join(folder_info))
        
        # ============================================================
        # STEP 4: Archive deleted sessions
        # ============================================================
        archived_count = 0
        for g_id, p_id in notion_pages.items():
            if g_id not in current_session_ids:
                archive_notion_page(p_id)
                archived_count += 1
        
        # ============================================================
        # STEP 5: Sync new sessions
        # ============================================================
        synced_names = []
        for session in session_folders:
            s_id = session['id']
            s_name = session['name']
            
            if s_id in notion_pages:
                synced_names.append(f"SKIP: {s_name} (already exists)")
                continue
            
            send_telegram_message(chat_id, f"Syncing: {s_name}...")
            
            blocks, total_photos = build_hierarchy(service, s_id, s_name, depth=1)
            
            first_thumb = ""
            for b in blocks:
                if b["type"] == "image":
                    first_thumb = b["image"]["external"]["url"]
                    break
                    
            p_id = create_notion_page(s_name, s_id, total_photos, first_thumb)
            if p_id:
                append_notion_blocks(p_id, blocks)
                synced_names.append(f"NEW: {s_name} ({total_photos} fotos)")
            else:
                synced_names.append(f"FAILED: {s_name}")
                
        msg = (
            "SYNC COMPLETE\n\n"
            f"Archived: {archived_count}\n"
            f"Total folders: {len(session_folders)}\n\n"
            + "\n".join(synced_names)
        )
        send_telegram_message(chat_id, msg)
        
    except Exception as e:
        tb = traceback.format_exc()
        send_telegram_message(chat_id, f"FATAL ERROR:\n{tb}")
        print(f"Error: {tb}")

def process_sync_async(chat_id):
    threading.Thread(target=sync_all, args=(chat_id,), daemon=True).start()

def run_photo_bot():
    print("TEJA VUH Photo Sync Bot started (DIAGNOSTIC MODE)!")
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
                            send_telegram_message(chat_id, "TEJA VUH Photo Bot (DIAGNOSTIC MODE)\nSend /sync to start")
                        else:
                            process_sync_async(chat_id)
        except Exception as e:
            time.sleep(2)
        time.sleep(0.5)

def start_bot():
    threading.Thread(target=run_photo_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"Running Health Check Server on port {port}...")
    start_bot()
    server = HTTPServer(("0.0.0.0", port), PhotoHealthHandler)
    server.serve_forever()
