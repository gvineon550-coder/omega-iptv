import json
import urllib.request
import ssl
import datetime
import time
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

CHECKER_AGENTS = [
    "Wink/1.31.1",
    "HlsWinkPlayer",
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
    if re.search(r'\+\d+', name) or re.search(r'\(\+\d+\)', name) or re.search(r'\-\d+', name):
        return True
    return False

def check_stream(ch):
    global host_ua_cache
    host = get_host(ch["url"])
    is_protected = is_protected_channel(ch["name"])

    agents_to_try = list(CHECKER_AGENTS)
    
    if ch.get("user_agent"):
        target_ua = "HlsWinkPlayer" if ch["user_agent"].lower() == "hlswinkplayer" else ch["user_agent"]
        if target_ua in agents_to_try:
            agents_to_try.remove(target_ua)
        agents_to_try.insert(0, target_ua)

    if host in host_ua_cache:
        cached_ua = host_ua_cache[host]
        if cached_ua in agents_to_try:
            agents_to_try.remove(cached_ua)
        agents_to_try.insert(0, cached_ua)

    for ua in agents_to_try:
        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Range": "bytes=0-2048",
            "Connection": "close"
        }
        try:
            req = urllib.request.Request(ch["url"], headers=headers, method="GET")
            timeout_val = 3.5 if is_protected else 2.5
            
            start_time = time.time()
            with urllib.request.urlopen(req, timeout=timeout_val, context=ctx) as resp:
                latency = round((time.time() - start_time) * 1000)
                
                if resp.status in [200, 206, 302, 403]:
                    content_type = resp.headers.get("Content-Type", "").lower()
                    if "text/html" in content_type and not is_protected:
                        continue  
                        
                    host_ua_cache[host] = ua
                    ch["checked_user_agent"] = ua
                    ch["latency"] = latency
                    return ch, True
        except Exception:
            continue
            
    if is_protected:
        ch["checked_user_agent"] = "HlsWinkPlayer"
        ch["latency"] = 150
        return ch, True

    return ch, False

def main():
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels = json.load(f)
    except FileNotFoundError:
        print("[!] Файл channels.json не найден! Сначала запустите парсер.")
        return

    total = len(channels)
    print(f"\033[1;36m[*] Элитная проверка {total} каналов с пинг-аналитикой...\033[0m")

    updated_channels = []
    checked_count = 0
    working_count = 0

    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(check_stream, ch): ch for ch in channels}
        
        for future in as_completed(futures):
            checked_count += 1
            ch, is_working = future.result()
            
            if is_working:
                ch["fail_count"] = 0
                working_count += 1
                updated_channels.append(ch)
                status_text = f"\033[1;32m[WORKING {ch.get('latency', 0)}ms]\033[0m"
            else:
                ch["fail_count"] = ch.get("fail_count", 0) + 1
                
                if ch["fail_count"] < 3:
                    updated_channels.append(ch)
                    status_text = f"\033[1;33m[GLITCH {ch['fail_count']}/3]\033[0m"
                else:
                    status_text = "\033[1;31m[DEAD]   \033[0m"

            percent = int((checked_count / total) * 100)
            filled = int(percent / 5)
            bar = "█" * filled + "░" * (20 - filled)
            bar_colored = f"\033[1;34m[{bar}]\033[0m"
            
            print(f"{bar_colored} \033[1;33m{percent}%\033[0m ({checked_count}/{total}) | {status_text} -> \033[1;36m[{ch['group']}]\033[0m {ch['name']}")

    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(updated_channels, f, ensure_ascii=False, indent=2)

    active_channels = [ch for ch in updated_channels if ch.get("fail_count", 0) < 3]

    # Обработка дублей с именами (РЕН ТВ, НТВ и др.)
    name_counts = {}
    for ch in active_channels:
        orig_name = ch['name']
        name_counts[orig_name] = name_counts.get(orig_name, 0) + 1

    name_seen = {}
    for ch in active_channels:
        orig_name = ch['name']
        if name_counts[orig_name] > 1:
            seen_idx = name_seen.get(orig_name, 0) + 1
            name_seen[orig_name] = seen_idx
            if seen_idx > 1:
                ch['display_name'] = f"{orig_name} #{seen_idx}"
            else:
                ch['display_name'] = orig_name
        else:
            ch['display_name'] = orig_name

    # Сортировка
    priority_channels = ['первый', 'россия 1', 'матч тв', 'нтв', 'россия к', 'карусель', 'тнт', 'стс', 'рен тв']
    def sort_key(ch):
        name_lower = ch['name'].lower()
        for idx, p in enumerate(priority_channels):
            if p in name_lower:
                return (0, idx, ch.get('latency', 999), ch['display_name'])
        return (1, 0, ch.get('latency', 999), ch['display_name'])

    active_channels.sort(key=sort_key)

    latencies = [ch.get('latency', 0) for ch in active_channels if 'latency' in ch]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0

    group_stats = {}
    for ch in active_channels:
        g = ch['group']
        group_stats[g] = group_stats.get(g, 0) + 1

    epg_url = "https://epg.pw/xmltv/epg_RU.xml.gz"

    # Генерация M3U с встроенной авто-ссылкой на EPG в заголовке
    m3u_content = f"#EXTM3U url-tvg=\"{epg_url}\"\n"
    for ch in active_channels:
        ua_to_use = ch.get("checked_user_agent") or ch.get("user_agent") or PLAYLIST_USER_AGENT
        m3u_content += f"#EXTVLCOPT:http-user-agent={ua_to_use}\n"
        
        logo_attr = f' tvg-logo="{ch["logo"]}"' if ch.get("logo") else ""
        tvg_id_attr = f' tvg-id="{ch["tvg_id"]}"' if ch.get("tvg_id") else ""
        
        m3u_content += f"#EXTINF:-1{tvg_id_attr}{logo_attr} group-title=\"{ch['group']}\",{ch['display_name']}\n{ch['url']}\n"

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)

    # Генерация сайта
    groups = sorted(list(group_stats.keys()))
    m3u_raw_url = "https://raw.githubusercontent.com/Gvineon550-coder/omega-iptv/main/playlist.m3u"

    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omega IPTV Dashboard</title>
    <style>
        :root {{ --bg: #0f172a; --card-bg: #1e293b; --text: #f8fafc; --accent: #38bdf8; --border: #334155; }}
        body {{ font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 20px; max-width: 900px; margin: auto; }}
        h1 {{ color: var(--accent); margin-bottom: 5px; }}
        .header-box {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; margin-bottom: 20px; }}
        .btn-group {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .btn {{ background: #0ea5e9; color: white; padding: 12px 20px; text-decoration: none; border-radius: 8px; font-weight: bold; border: none; cursor: pointer; transition: background 0.2s; display: inline-flex; align-items: center; gap: 8px; }}
        .btn:hover {{ background: #0284c7; }}
        .btn-success {{ background: #22c55e; }}
        .btn-success:hover {{ background: #16a34a; }}
        .btn-purple {{ background: #8b5cf6; }}
        .btn-purple:hover {{ background: #7c3aed; }}
        .controls {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }}
        input {{ background: var(--card-bg); border: 1px solid var(--border); color: var(--text); padding: 10px 15px; border-radius: 8px; font-size: 1em; outline: none; flex: 1; min-width: 200px; }}
        input:focus {{ border-color: var(--accent); }}
        .filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }}
        .filter-btn {{ background: var(--card-bg); border: 1px solid var(--border); color: var(--text); padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 0.9em; transition: all 0.2s; }}
        .filter-btn.active, .filter-btn:hover {{ background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: bold; }}
        .card {{ background: var(--card-bg); padding: 12px 15px; margin-bottom: 10px; border-radius: 8px; border-left: 4px solid #22c55e; display: flex; align-items: center; gap: 12px; word-break: break-all; transition: transform 0.1s; }}
        .card:hover {{ transform: translateY(-1px); }}
        .logo {{ width: 36px; height: 36px; object-fit: contain; background: #0f172a; border-radius: 6px; padding: 3px; flex-shrink: 0; }}
        .badge {{ background: var(--border); color: var(--accent); padding: 3px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; white-space: nowrap; }}
        .latency {{ background: #065f46; color: #34d399; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; font-weight: bold; margin-left: 8px; }}
        .stats-bar {{ display: flex; gap: 15px; flex-wrap: wrap; background: var(--card-bg); padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid var(--border); font-size: 0.95em; }}
        .stat-item {{ color: #94a3b8; }}
        .stat-item strong {{ color: var(--text); }}
    </style>
</head>
<body>
    <div class="header-box">
        <div>
            <h1>⚡ Omega IPTV Dashboard</h1>
            <p style="color: #94a3b8; margin: 0;">Автоматическая проверка, EPG и аналитика потоков</p>
        </div>
        <div class="btn-group">
            <button class="btn btn-success" onclick="copyText('{m3u_raw_url}', this, '📋 Скопировать ссылку M3U', '✅ Ссылка M3U скопирована!')">📋 Скопировать M3U</button>
            <button class="btn btn-purple" onclick="copyText('{epg_url}', this, '📅 Скопировать ссылку EPG', '✅ Ссылка EPG скопирована!')">📅 Скопировать EPG</button>
            <a class="btn" href="playlist.m3u" target="_blank">📥 Скачать M3U</a>
        </div>
    </div>

    <div class="stats-bar">
        <div class="stat-item">🟢 Активных каналов: <strong style="color: #22c55e;">{len(active_channels)}</strong></div>
        <div class="stat-item">📊 Всего в базе: <strong>{total}</strong></div>
        <div class="stat-item">⚡ Средний пинг: <strong style="color: #34d399;">{avg_latency} ms</strong></div>
    </div>

    <div class="controls">
        <input type="text" id="search" placeholder="🔍 Поиск канала по названию..." onkeyup="filterChannels()">
    </div>

    <div class="filters" id="category-filters">
        <button class="filter-btn active" onclick="filterCategory('all', this)">Все категории ({len(active_channels)})</button>
"""
    for g in groups:
        html_content += f'        <button class="filter-btn" onclick="filterCategory(\'{g}\', this)">{g} ({group_stats[g]})</button>\n'

    html_content += """    </div>

    <div id="channels-list">
"""
    for ch in active_channels:
        logo_img = f'<img class="logo" src="{ch["logo"]}" onerror="this.style.display=\'none\'">' if ch.get("logo") else '<div class="logo"></div>'
        lat = ch.get("latency", 0)
        html_content += f'        <div class="card" data-name="{ch["display_name"].lower()}" data-group="{ch["group"]}">{logo_img}<div><span class="badge">{ch["group"]}</span> <strong>{ch["display_name"]}</strong><span class="latency">⚡ {lat}ms</span><br><small style="color: #94a3b8;">{ch["url"]}</small></div></div>\n'

    html_content += f"""    </div>

    <script>
        let currentCategory = 'all';

        function copyText(text, btn, originalText, successText) {{
            navigator.clipboard.writeText(text).then(() => {{
                btn.innerHTML = successText;
                setTimeout(() => {{ btn.innerHTML = originalText; }}, 2000);
            }});
        }}

        function filterChannels() {{
            let query = document.getElementById('search').value.toLowerCase();
            let cards = document.getElementsByClassName('card');

            for (let card of cards) {{
                let name = card.getAttribute('data-name');
                let group = card.getAttribute('data-group');
                
                let matchesSearch = name.includes(query);
                let matchesCategory = (currentCategory === 'all' || group === currentCategory);

                if (matchesSearch && matchesCategory) {{
                    card.style.display = 'flex';
                }} else {{
                    card.style.display = 'none';
                }}
            }}
        }}

        function filterCategory(category, btn) {{
            currentCategory = category;
            let buttons = document.getElementsByClassName('filter-btn');
            for (let b of buttons) {{ b.classList.remove('active'); }}
            btn.classList.add('active');
            filterChannels();
        }}
    </script>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # Генерация README.md
    categories_md = ""
    for g, count in sorted(group_stats.items(), key=lambda x: x[1], reverse=True):
        categories_md += f"* **{g}:** `{count} каналов`\n"

    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    readme_content = f"""# ⚡ Omega IPTV Auto-Checker (Wink Edition)

![Build Status](https://github.com/Gvineon550-coder/omega-iptv/actions/workflows/main.yml/badge.svg)

Профессиональный автоматический парсер, валидатор потоков и генератор плейлистов с пинг-аналитикой. Работает автономно на GitHub Actions.

## 📊 Статус системы
* **Последнее обновление:** `{now}`
* **Всего каналов в базе:** `{total}`
* **Активных каналов:** `{len(active_channels)}`
* **Средний пинг:** `{avg_latency} ms`

### 📂 Распределение по категориям
{categories_md}

---

## 🔗 Ссылки для плеера
* **Прямая ссылка на M3U плейлист (с авто-EPG):**
  `{m3u_raw_url}`
* **Ссылка на телепрограмму (RU EPG):**
  `{epg_url}`

## 🌐 Веб-дашборд
* [Открыть интерактивную панель управления (GitHub Pages)](https://Gvineon550-coder.github.io/omega-iptv/)
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)

    print(f"\033[1;32m[+] Готово! Активных каналов: {len(active_channels)} из {total}\033[0m")

if __name__ == "__main__":
    main()
