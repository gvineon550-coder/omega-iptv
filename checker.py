import json
import urllib.request
import ssl
import datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Список агентов: Wink, hlswinkplayer, стандартные браузеры и VLC
CHECKER_AGENTS = [
    "Wink/1.31.1",
    "hlswinkplayer",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 6.0; Wink_Share_SE) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.92 Mobile Safari/537.36",
    "VLC/3.0.20 LibVLC/3.0.20"
]

PLAYLIST_USER_AGENT = "Wink/1.31.1" # Основной UA для итогового плейлиста

# Глобальный кэш для успешных User-Agent по доменам (хостам)
host_ua_cache = {}

def get_host(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return url

def check_stream(ch):
    global host_ua_cache
    host = get_host(ch["url"])
    
    # Формируем порядок проверки: если для этого хоста уже найден рабочий UA, ставим его первыми
    agents_to_try = list(CHECKER_AGENTS)
    if host in host_ua_cache:
        cached_ua = host_ua_cache[host]
        if cached_ua in agents_to_try:
            agents_to_try.remove(cached_ua)
        agents_to_try.insert(0, cached_ua)

    for ua in agents_to_try:
        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Range": "bytes=0-1024",
            "Connection": "close"
        }
        try:
            req = urllib.request.Request(ch["url"], headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=2.5, context=ctx) as resp:
                if resp.status in [200, 206, 302]:
                    # Запоминаем успешный UA для всего хоста!
                    host_ua_cache[host] = ua
                    return ch, True
        except Exception:
            continue
            
    return ch, False

def main():
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels = json.load(f)
    except FileNotFoundError:
        print("[!] Файл channels.json не найден!")
        return

    # ВАЖНО: Никаких срезов нет, берем все каналы до единого!
    total = len(channels)
    print(f"[*] Умная параллельная проверка ВСЕХ {total} каналов с кэшированием хостов...")

    valid_channels = []
    checked_count = 0

    # Параллельная проверка в 30 потоков
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(check_stream, ch): ch for ch in channels}
        
        for future in as_completed(futures):
            checked_count += 1
            ch, is_working = future.result()
            
            if is_working:
                valid_channels.append(ch)

            # Прогресс-бар
            percent = int((checked_count / total) * 100)
            filled = int(percent / 5)
            bar = "█" * filled + "░" * (20 - filled)
            status_text = "WORKING" if is_working else "DEAD    "
            print(f"[{bar}] {percent}% ({checked_count}/{total}) | {status_text} -> [{ch['group']}] {ch['name']}")

    # Генерация M3U плейлиста
    m3u_content = "#EXTM3U\n"
    for ch in valid_channels:
        m3u_content += f"#EXTVLCOPT:http-user-agent={PLAYLIST_USER_AGENT}\n"
        m3u_content += f"#EXTINF:-1 group-title=\"{ch['group']}\",{ch['name']}\n{ch['url']}\n"

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)

    # Генерация HTML для GitHub Pages
    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omega IPTV Status</title>
    <style>
        body {{ font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; max-width: 800px; margin: auto; }}
        h1 {{ color: #38bdf8; }}
        .card {{ background: #1e293b; padding: 15px; margin-bottom: 10px; border-radius: 8px; border-left: 4px solid #22c55e; word-break: break-all; }}
        .btn {{ display: inline-block; background: #0ea5e9; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-bottom: 20px; }}
        .badge {{ background: #334155; color: #38bdf8; padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>⚡ Omega IPTV Status (Wink Edition)</h1>
    <p>Автоматический стелс-чекер IPTV с категориями и кэшированием хостов.</p>
    <a class="btn" href="playlist.m3u">Скачать рабочий M3U плейлист</a>
    <h2>Рабочие каналы ({len(valid_channels)} из {total}):</h2>
    <div>
"""
    for ch in valid_channels:
        html_content += f'        <div class="card"><span class="badge">{ch["group"]}</span> <strong>{ch["name"]}</strong><br><small style="color: #94a3b8;">{ch["url"]}</small></div>\n'

    html_content += """    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # Генерация README.md
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    readme_content = f"""# ⚡ Omega IPTV Auto-Checker (Wink Edition)

Автоматический парсер, стелс-чекер и генератор плейлистов с поддержкой Wink и кэшированием хостов. Работает на GitHub Actions.

## 📊 Статус системы
* **Последнее обновление:** `{now}`
* **Всего проверено:** `{total}`
* **Рабочих каналов:** `{len(valid_channels)}`

---

## 🔗 Ссылки
* **Прямая ссылка на M3U:** `https://raw.githubusercontent.com/Gvineon550-coder/omega-iptv/main/playlist.m3u`
* **Веб-панель (GitHub Pages):** [Открыть сайт статуса](https://Gvineon550-coder.github.io/omega-iptv/)
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)

    print(f"[+] Готово! Проверено: {total}, Рабочих каналов: {len(valid_channels)}, файлы обновлены.")

if __name__ == "__main__":
    main()
