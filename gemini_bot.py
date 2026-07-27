import os
import json
import time
import base64
import urllib.request
import urllib.error
import ssl
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

TELEGRAM_TOKEN = "8979159757:AAHQrGKa7DNZF2QgUzMdUZvvYDuF1iF2qvY"
NOTION_API_KEY = "ntn_" + "261270948384dzEroLYe0I68u6AU72CW5RRU7YWHshM4Eu"
MASTER_PLAN_DB_ID = "3a86154b-d436-81a7-a0db-f369dde96027"
GEMINI_API_KEY = "AQ." + "Ab8RN6LchXqGxtyxGl71ZocNNXOcnIlKj3_Xe2esHM4_R4HisQ"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SYSTEM_PROMPT = """Ты — системный аналитик и AI-менеджер проектов чайного бренда TEJA VUH. 
Твоя единственная задача: получать сырые текстовые (или расшифрованные голосовые) заметки пользователя и превращать их в строго структурированный JSON для создания страницы-задачи в базе данных Notion (Master Plan).

АБСОЛЮТНЫЕ ПРАВИЛА ВЫВОДА:
1. Ты возвращаешь ТОЛЬКО валидный JSON. 
2. Запрещен любой обычный текст до или после JSON. Запрещены markdown-блоки (не используй ```json ... ```, выдавай чистый текст в фигурных скобках).
3. Соблюдай строгие значения для полей-селекторов (копируй символ в символ, включая эмодзи и пробелы), иначе API Notion выдаст ошибку.

СТРУКТУРА JSON, КОТОРУЮ ТЫ ДОЛЖЕН СГЕНЕРИРОВАТЬ:
{
  "Task Name": "Краткое и понятное название задачи (суть в 3-7 словах)",
  "Branch": "Строго одно значение из списка доступных",
  "Priority": "Строго одно значение из списка приоритетов",
  "Status": "Строго одно значение из списка статусов",
  "Content": "Подробное описание задачи, контекст и детали, переданные пользователем. Если информации много, структурируй ее."
}

ДОСТУПНЫЕ ЗНАЧЕНИЯ ДЛЯ ПОЛЯ "Branch" (Выбери наиболее подходящее по смыслу):
- "📥 Inbox" (Используй по умолчанию, если категория неясна)
- "🔧 A. Инфраструктура"
- "📦 B. Продукт"
- "🌐 C. Сайт"
- "📣 D. Маркетинг"
- "💰 E. Продажи"
- "🤖 F. Боты"
- "❤️ G. Club del Té"
- "🌍 H. Международные"
- "🏠 I. Операции"
- "🆕 J. Новые продукты"
- "🚀 K. Франшиза"

ДОСТУПНЫЕ ЗНАЧЕНИЯ ДЛЯ ПОЛЯ "Priority":
- "High 🔴" (Если пользователь говорит "срочно", "важно", "горит")
- "Medium 🟡" (Стандартный приоритет по умолчанию)
- "Low 🟢" (Если это просто идея на будущее или не горит)

ДОСТУПНЫЕ ЗНАЧЕНИЯ ДЛЯ ПОЛЯ "Status":
- "Backlog" (По умолчанию для всех новых задач)
- "In Progress 🚀" (Если пользователь указывает, что задача уже выполняется)
- "AI Review 🤖" (Если требуется анализ или задача ставится для ИИ)
- "Done ✅"
- "Paused ⏸️"
"""

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - TEJA VUH AI Assistant Active")

    def log_message(self, format, *args):
        return

def self_keep_alive(port):
    time.sleep(10)
    print(f"⏰ AI Assistant Self-Keep-Alive active on port {port}!")
    while True:
        try:
            url = f"http://127.0.0.1:{port}/"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as response:
                pass
        except Exception:
            pass
        time.sleep(180)

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

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    headers = {"Content-Type": "application/json"}
    payload = {"chat_id": chat_id, "text": text}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, context=ctx)
    except Exception as e:
        print(f"❌ Error al enviar mensaje a Telegram: {e}")

def transcribe_audio_to_text(oga_bytes):
    models = ["gemini-flash-lite-latest", "gemini-flash-latest"]
    audio_b64 = base64.b64encode(oga_bytes).decode("utf-8")
    for model_name in models:
        for attempt in range(2):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                body = {
                    "contents": [{
                        "parts": [
                            {"inline_data": {"mime_type": "audio/ogg", "data": audio_b64}},
                            {"text": "Transcribe este mensaje de audio con precisión en el idioma hablado (español, inglés o ruso). Devuelve ÚNICAMENTE el texto exacto dicho en el audio, sin comentarios adicionales ni introducciones."}
                        ]
                    }]
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
                print(f"⚠️ Error en modelo {model_name}: {e}")
                time.sleep(0.5)
    return None

def analyze_with_gemini(text):
    models = ["gemini-flash-latest", "gemini-2.0-flash-lite", "gemini-flash-lite-latest"]
    for model_name in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            body = {
                "contents": [
                    {"parts": [{"text": f"USER REQUEST:\n{text}"}]}
                ],
                "system_instruction": {
                    "parts": [{"text": SYSTEM_PROMPT}]
                }
            }
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode("utf-8"))
                candidates = res.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        raw_json = parts[0].get("text", "").strip()
                        # Очистка маркдауна, если ИИ все же его добавил
                        if raw_json.startswith("```json"):
                            raw_json = raw_json[7:]
                        if raw_json.startswith("```"):
                            raw_json = raw_json[3:]
                        if raw_json.endswith("```"):
                            raw_json = raw_json[:-3]
                        return json.loads(raw_json.strip())
        except Exception as e:
            print(f"⚠️ Error {model_name}: {e}")
            time.sleep(1)
    return None

def create_notion_page(task_json):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    # Безопасное извлечение полей с fallback-значениями
    task_name = task_json.get("Task Name", "Новая задача от ИИ")
    branch = task_json.get("Branch", "📥 Inbox")
    priority = task_json.get("Priority", "Medium 🟡")
    status = task_json.get("Status", "Backlog")
    content = task_json.get("Content", "")

    payload = {
        "parent": {"type": "database_id", "database_id": MASTER_PLAN_DB_ID},
        "icon": {"type": "emoji", "emoji": "🤖"},
        "properties": {
            "Task Name": {"title": [{"type": "text", "text": {"content": task_name}}]},
            "Branch": {"select": {"name": branch}},
            "Priority": {"select": {"name": priority}},
            "Status": {"select": {"name": status}}
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            }
        ]
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("url")
    except urllib.error.HTTPError as e:
        print(f"❌ Notion API Error: {e.code} - {e.read().decode()}")
    except Exception as e:
        print(f"❌ Notion API Error: {e}")
    return None

def process_message_async(chat_id, text_input=None, file_id=None):
    try:
        if file_id:
            send_telegram_message(chat_id, "🎙️ Анализирую голос...")
            file_path = get_telegram_file_path(file_id)
            if not file_path:
                send_telegram_message(chat_id, "❌ Ошибка: не удалось скачать аудио.")
                return
            audio_bytes = download_telegram_file(file_path)
            transcribed_text = transcribe_audio_to_text(audio_bytes)
            if not transcribed_text:
                send_telegram_message(chat_id, "❌ Не удалось распознать голос.")
                return
            user_request = transcribed_text
            send_telegram_message(chat_id, f"📝 Распознано:\n_{user_request}_")
        else:
            user_request = text_input
            send_telegram_message(chat_id, "🤖 AI-менеджер анализирует задачу...")

        # 1. Анализ через Gemini
        task_data = analyze_with_gemini(user_request)
        if not task_data:
            send_telegram_message(chat_id, "❌ Ошибка: ИИ не смог структурировать данные.")
            return

        # 2. Создание страницы в Notion
        send_telegram_message(chat_id, f"⚡ Создаю карточку в отделе {task_data.get('Branch')}...")
        page_url = create_notion_page(task_data)
        
        if page_url:
            success_msg = (
                f"✅ **Задача успешно создана!**\n\n"
                f"📌 **{task_data.get('Task Name')}**\n"
                f"📂 Отдел: {task_data.get('Branch')}\n"
                f"🚦 Статус: {task_data.get('Status')}\n"
                f"🔥 Приоритет: {task_data.get('Priority')}\n\n"
                f"[🔗 Открыть карточку в Notion]({page_url})"
            )
            send_telegram_message(chat_id, success_msg)
        else:
            send_telegram_message(chat_id, "❌ Ошибка создания страницы в Notion. Проверьте правильность названий категорий.")

    except Exception as e:
        print(f"❌ Error in process_message_async: {e}")
        send_telegram_message(chat_id, "❌ Произошла внутренняя ошибка сервера.")

def run_telegram_bot():
    print("🚀 AI Assistant Bot 24/7 (Gemini ↔ Notion) iniciado!")
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
                    
                    if not chat_id:
                        continue

                    if "text" in message:
                        user_text = message["text"]
                        if user_text.startswith("/start"):
                            send_telegram_message(chat_id, "👋 ¡Hola! Я твой умный AI-Ассистент TEJA VUH.\nНапиши мне задачу или отправь голосовое, и я сам разберу её, структурирую и создам полноценную карточку в нужном отделе Notion!")
                            continue
                        
                        threading.Thread(target=process_message_async, args=(chat_id, user_text, None), daemon=True).start()

                    elif "voice" in message or "audio" in message:
                        voice_info = message.get("voice") or message.get("audio")
                        file_id = voice_info.get("file_id")
                        threading.Thread(target=process_message_async, args=(chat_id, None, file_id), daemon=True).start()

        except Exception as e:
            time.sleep(2)
        time.sleep(0.5)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Running Health Check Server on port {port}...")
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    threading.Thread(target=self_keep_alive, args=(port,), daemon=True).start()
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()
