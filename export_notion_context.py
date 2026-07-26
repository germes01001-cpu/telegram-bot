import os
import json
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timezone, timedelta

api_key = "ntn_" + "261270948384dzEroLYe0I68u6AU72CW5RRU7YWHshM4Eu"
master_db_id = "3a86154b-d436-81a7-a0db-f369dde96027"
inbox_id = "3a76154bd4368016858ec7ef7b8afebc"
media_db_id = "3a96154b-d436-810e-a991-ca006eab15e7"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def query_notion_database(db_id):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {"page_size": 100}
    all_pages = []
    has_more = True
    next_cursor = None

    while has_more:
        if next_cursor:
            payload["start_cursor"] = next_cursor
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode("utf-8"))
                all_pages.extend(res.get("results", []))
                has_more = res.get("has_more", False)
                next_cursor = res.get("next_cursor")
        except Exception as e:
            print(f"❌ Ошибка запроса к БД {db_id}: {e}")
            break
    return all_pages

def query_inbox_blocks():
    url = f"https://api.notion.com/v1/blocks/{inbox_id}/children"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("results", [])
    except Exception as e:
        print(f"❌ Ошибка запроса к Inbox: {e}")
        return []

def generate_master_context():
    print("🚀 Генерация Единого Контекста Знаний TEJA VUH...")
    now_str = datetime.now(tz=timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S")
    
    md_lines = [
        "# 🍵 TEJA VUH — ЕДИНЫЙ ПАНОРАМНЫЙ КОНТЕКСТ ЗНАНИЙ (Single Source of Truth)",
        f"*Дата выгрузки: {now_str} (GMT-5)*",
        "*Синхронизация: Antigravity + Gemini + NotebookLM*",
        "",
        "---",
        "",
        "## 1. ФИЛОСОФИЯ И КОНЦЕПЦИЯ БРЕНДА",
        "- **Бренд**: TEJA VUH (Спешелти-чай, церемонии, музыка Tejabu).",
        "- **Локации**: Перу (Писак, Куско, Лима, Священная Долина Инков).",
        "- **Ядро**: Премиальный чай, гармония, чайные церемонии, авторские купажи, сопутствующий мерч и музыка.",
        "",
        "---",
        "",
        "## 2. ТЕКУЩИЕ ЗАМЕТКИ И ИДЕИ ИЗ INBOX"
    ]

    inbox_blocks = query_inbox_blocks()
    if inbox_blocks:
        for b in inbox_blocks:
            b_type = b.get("type")
            if b_type in ("to_do", "paragraph"):
                rich_texts = b.get(b_type, {}).get("rich_text", [])
                if rich_texts:
                    text_val = rich_texts[0].get("text", {}).get("content", "")
                    md_lines.append(f"- {text_val}")
    else:
        md_lines.append("- (Заметок пока нет)")

    md_lines.extend([
        "",
        "---",
        "",
        "## 3. МЕДИА-АРХИВ И ФОТОСЕССИИ (Google Диск)"
    ])

    media_pages = query_notion_database(media_db_id)
    if media_pages:
        for p in media_pages:
            props = p.get("properties", {})
            title_list = props.get("Название Фотосессии", {}).get("title", [])
            name = title_list[0].get("text", {}).get("content", "Фотосессия") if title_list else "Фотосессия"
            url_val = props.get("Ссылка на Google Диск", {}).get("url", "")
            branch_obj = props.get("Направление (Branch)", {}).get("select")
            branch = branch_obj.get("name") if branch_obj else "Маркетинг"
            md_lines.append(f"- **[{name}]** ({branch}) — [Ссылка на Google Диск]({url_val})")
    else:
        md_lines.append("- (Медиа-записи пока нет)")

    md_lines.extend([
        "",
        "---",
        "",
        "## 4. ГЕНЕРАЛЬНЫЙ ПЛАН ЗАДАЧ (MASTER PLAN)"
    ])

    master_pages = query_notion_database(master_db_id)
    branch_groups = {}
    for p in master_pages:
        props = p.get("properties", {})
        title_list = props.get("Task Name", {}).get("title", [])
        task_name = title_list[0].get("text", {}).get("content") if title_list else "Без названия"
        code_list = props.get("Code", {}).get("rich_text", [])
        code = code_list[0].get("text", {}).get("content") if code_list else ""
        branch_obj = props.get("Branch", {}).get("select")
        branch = branch_obj.get("name") if branch_obj else "Разное"
        status_obj = props.get("Status", {}).get("select")
        status = status_obj.get("name") if status_obj else "Backlog"
        phase_obj = props.get("Phase", {}).get("select")
        phase = phase_obj.get("name") if phase_obj else "Фундамент"
        
        full_title = f"[{code}] {task_name}" if code else task_name
        item_str = f"- **{full_title}** — Статус: `{status}` | Фаза: `{phase}`"
        
        if branch not in branch_groups:
            branch_groups[branch] = []
        branch_groups[branch].append(item_str)

    for b_name, t_list in sorted(branch_groups.items()):
        md_lines.append(f"\n### Ветка: {b_name} ({len(t_list)} задач)")
        md_lines.extend(t_list)

    final_md = "\n".join(md_lines)
    
    output_path = "/Volumes/DATA/TejaVuhAG/TEJA_VUH_Full_Context.md"
    desktop_path = "/Users/macbookpro/Desktop/TEJA_VUH_Full_Context.md"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_md)
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.write(final_md)

    print(f"✅ Единый Контекст Знаний сгенерирован!\n  └─ Файл: {desktop_path}\n  └─ Всего строк: {len(md_lines)}")

if __name__ == "__main__":
    generate_master_context()
