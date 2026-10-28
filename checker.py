import json
import urllib.request
import ssl
import datetime
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

CHECKER_AGENTS = [
    "Wink/1.31.1",
    "hlswinkplayer",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 6.0; Wink_Share_SE) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.92 Mobile Safari/537.36",
    "VLC/3.0.20 LibVLC/3.0.20"
]

PLAYLIST_USER_AGENT = "Wink/1.31.1"
host_ua_cache = {}

def get_host(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return url

def is_protected_channel(name):
    """Определяет, является ли канал тайм-шифтом (+2, +4 и т.д.) 
       или важной вариацией, которую нельзя вырезать."""
    if re.search(r'\+\d+', name) or re.search(r'\(\+\d+\)', name) or re.search(r'\-\d+', name):
        return True
    return False

def check_stream(ch):
    global host_ua_cache
    host = get_host(ch["url"])
    is_protected = is_protected_channel(ch["name"])

    agents_to_try = list(CHECKER_AGENTS)
    
    if ch.get("user_agent"):
        if ch["user_agent"] in agents_to_try:
            agents_to_try.remove(ch["user_agent"])
        agents_to_try.insert(0, ch["user_agent"])

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
            timeout_val = 3.5 if is_protected else 2.5
            with urllib.request.urlopen(req, timeout=timeout_val, context=ctx) as resp:
                if resp.status in [200, 206, 302, 403]:
                    host_ua_cache[host] = ua
                    return ch, True
        except Exception:
            continue
            
    if is_protected:
        return ch, True

    return ch, False

def main():
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels = json.load(f)
    except FileNotFoundError:
        print("[!] Файл channels.json не найден!")
        return

    total = len(channels)
    print(f"\033[1;36m[*] Запуск умной параллельной проверки ВСЕХ {total} каналов...\033[0m")

    valid_channels = []
    checked_count = 0

    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(check_stream, ch): ch for ch in channels}
        
        for future in as_completed(futures):
            checked_count += 1
            ch, is_working = future.result()
            
            if is_working:
                valid_channels.append(ch)

            percent = int((checked_count / total) * 100)
            filled = int(percent / 5)
            bar = "█" * filled + "░" * (20 - filled)
            
            # Цветовое оформление для GitHub Actions (ANSI)
            if is_working:
                status_text = "\033[1;32m[WORKING]\033[0m"
            else:
                status_text = "\033[1;31m[DEAD]   \033[0m"
                
            bar_colored = f"\033[1;34m[{bar}]\033[0m"
            print(f"{bar_colored} \033[1;33m{percent}%\033[0m ({checked_count}/{total}) | {status_text} -> \033[1;36m[{ch['group']}]\033[0m {ch['name']}")

    # Генерация M3U плейлиста
    m3u_content = "#EXTM3U\n"
    for ch in valid_channels:
        ua_to_use = ch.get("user_agent") if ch.get("user_agent") else PLAYLIST_USER_AGENT
        m3u_content += f"#EXTVLCOPT:http-user-agent={ua_to_use}\n"
        logo_attr = f' tvg-logo="{ch["logo"]}"' if ch.get("logo") else ""
        m3u_content += f"#EXTINF:-1{logo_attr} group-title=\"{ch['group']}\",{ch['name']}\n{ch['url']}\n"

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)

    # Генерация HTML для сайта статуса
    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omega IPTV Status</title>
    <style>
        body {{ font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; max-width: 800px; margin: auto; }}
        h1 {{ color: #38bdf8; }}
        .card {{ background: #1e293b; padding: 12px 15px; margin-bottom: 10px; border-radius: 8px; border-left: 4px solid #22c55e; display: flex; align-items: center; gap: 12px; word-break: break-all; }}
        .logo {{ width: 32px; height: 32px; object-fit: contain; background: #334155; border-radius: 4px; padding: 2px; flex-shrink: 0; }}
        .btn {{ display: inline-block; background: #0ea5e9; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-bottom: 20px; }}
        .badge {{ background: #334155; color: #38bdf8; padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; white-space: nowrap; }}
    </style>
</head>
<body>
    <h1>⚡ Omega IPTV Status (Wink Edition)</h1>
    <p>Автоматический чекер IPTV с поддержкой тайм-шифтов и умными логотипами.</p>
    <a class="btn" href="playlist.m3u">Скачать рабочий M3U плейлист</a>
    <h2>Рабочие каналы ({len(valid_channels)} из {total}):</h2>
    <div>
"""
    for ch in valid_channels:
        logo_img = f'<img class="logo" src="{ch["logo"]}" onerror="this.style.display=\'none\'">' if ch.get("logo") else '<div class="logo"></div>'
        html_content += f'        <div class="card">{logo_img}<div><span class="badge">{ch["group"]}</span> <strong>{ch["name"]}</strong><br><small style="color: #94a3b8;">{ch["url"]}</small></div></div>\n'

    html_content += """    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # Генерация README.md
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    readme_content = f"""# ⚡ Omega IPTV Auto-Checker (Wink Edition)

Автоматический парсер, стелс-чекер и генератор плейлистов. Работает на GitHub Actions.

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

    print(f"\033[1;32m[+] Готово! Проверено: {total}, Рабочих каналов: {len(valid_channels)}\033[0m")

if __name__ == "__main__":
    main()
