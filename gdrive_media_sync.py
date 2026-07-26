import os
import json
import urllib.request
import urllib.error
import ssl
import re

api_key = "ntn_" + "261270948384dzEroLYe0I68u6AU72CW5RRU7YWHshM4Eu"
media_db_id = "3a96154b-d436-810e-a991-ca006eab15e7"
gdrive_folder_url = "https://drive.google.com/drive/folders/1F4bG6AA8huu2Co7wcbF4es4yGJ15fdhX?usp=sharing"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_gdrive_folder_title(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, context=ctx) as r:
            html = r.read().decode("utf-8", errors="ignore")
            titles = re.findall(r"<title>(.*?)</title>", html)
            if titles:
                clean_title = titles[0].replace(" - Google Drive", "").strip()
                return clean_title
    except Exception as e:
        print(f"⚠️ Ошибка получения заглавия Google Диска: {e}")
    return "TejaVuh / FOTOS"

def sync_folder_to_notion_media_db(folder_title, folder_url):
    print(f"🚀 Синхронизация папки Google Диска: '{folder_title}' ➔ Notion...")
    
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"type": "database_id", "database_id": media_db_id},
        "icon": {"type": "emoji", "emoji": "📁"},
        "properties": {
            "Название Фотосессии": {
                "title": [{"type": "text", "text": {"content": f"📁 Папка: {folder_title}"}}]
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
            print(f"✅ Успешно синхронизирована папка в Notion! Page ID: {res.get('id')}")
            return res.get("id")
    except Exception as e:
        print(f"❌ Ошибка синхронизации с Notion: {e}")
        return None

def main():
    title = fetch_gdrive_folder_title(gdrive_folder_url)
    sync_folder_to_notion_media_db(title, gdrive_folder_url)

if __name__ == "__main__":
    main()
