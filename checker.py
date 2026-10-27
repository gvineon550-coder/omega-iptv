import json
import urllib.request
import ssl
import datetime

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Маскировка бота при проверке каналов
CHECKER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "SmartIPTV/1.0 (Samsung Smart TV; Tizen)",
    "Kodi/21.0 (Linux; Android 12)"
]

# Чистый UA для вашего плеера (прописывается в playlist.m3u)
PLAYLIST_USER_AGENT = "VLC/3.0.20 LibVLC/3.0.20"

def check_stream(url):
    for ua in CHECKER_AGENTS:
        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Range": "bytes=0-1024",
            "Connection": "close"
        }
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
                if resp.status in [200, 206, 302]:
                    return True
        except Exception:
            continue
    return False

def main():
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels = json.load(f)
    except FileNotFoundError:
        print("[!] Файл channels.json не найден!")
        return

    valid_channels = []
    print(f"[*] Стелс-проверка {len(channels)} каналов с категориями...")

    for i, ch in enumerate(channels):
        is_working = check_stream(ch["url"])
        status = "WORKING" if is_working else "DEAD"
        print(f"[{i+1}/{len(channels)}] {status} -> [{ch['group']}] {ch['name']}")
        if is_working:
            valid_channels.append(ch)

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
    <h1>⚡ Omega IPTV Status (Categorized)</h1>
    <p>Автоматический стелс-чекер IPTV с категориями. Обновление каждые 6 часов.</p>
    <a class="btn" href="playlist.m3u">Скачать рабочий M3U плейлист</a>
    <h2>Рабочие каналы ({len(valid_channels)}):</h2>
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

    # Генерация README.md с вашим аккаунтом Gvineon550-coder
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    readme_content = f"""# ⚡ Omega IPTV Auto-Checker (Categorized)

Автоматический парсер, стелс-чекер и генератор плейлистов с категориями для российских и русскоязычных IPTV-каналов (`iptv-org`). Работает на GitHub Actions.

## 📊 Статус системы
* **Последнее обновление:** `{now}`
* **Всего проверено:** `{len(channels)}`
* **Рабочих каналов:** `{len(valid_channels)}`

---

## 🔗 Ссылки
* **Прямая ссылка на M3U:** `https://raw.githubusercontent.com/Gvineon550-coder/omega-iptv/main/playlist.m3u`
* **Веб-панель (GitHub Pages):** [Открыть сайт статуса](https://Gvineon550-coder.github.io/omega-iptv/)
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)

    print(f"[+] Готово! Рабочих каналов: {len(valid_channels)}, README и плейлист обновлены.")

if __name__ == "__main__":
    main()
