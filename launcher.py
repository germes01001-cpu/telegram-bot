import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import cloud_bot
import gemini_bot
import photo_bot
import time

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK - TEJA VUH Unified Server Active (2 Bots Running)")

    def log_message(self, format, *args):
        return

def self_keep_alive(port):
    time.sleep(10)
    print(f"⏰ Unified Self-Keep-Alive active on port {port}!")
    import urllib.request
    while True:
        try:
            # Ping Render's external URL to keep the load balancer awake
            url = os.environ.get("RENDER_EXTERNAL_URL", f"http://127.0.0.1:{port}/")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as response:
                pass
        except Exception:
            pass
        time.sleep(180)

if __name__ == "__main__":
    print("🚀 TEJA VUH Unified Server is starting...")
    
    # 1. Запускаем первый бот (Inbox / Заметки)
    print("➡️ Запуск cloud_bot (Inbox)...")
    cloud_bot.start_bot()
    
    # 2. Запускаем второй бот (AI-Ассистент / Master Plan)
    print("➡️ Запуск gemini_bot (AI Manager)...")
    gemini_bot.start_bot()

    # 3. Запускаем третий бот (Фото-синхронизатор)
    print("➡️ Запуск photo_bot (Photo Sync)...")
    photo_bot.start_bot()

    # 4. Запускаем единый сервер проверки здоровья для Render
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Running Unified Health Check Server on port {port}...")
    
    threading.Thread(target=self_keep_alive, args=(port,), daemon=True).start()
    
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()
