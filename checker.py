import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape as html_escape
from urllib.parse import urlparse

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

EPG_URL = "https://github.com/dgomp/epg-iptv/releases/latest/download/epg_latest.xml"

CHECKER_AGENTS = [
    "Mozilla/5.0 WINK/1.34.1 (AndroidTV/6.1.1) HlsWinkPlayer",
    "Mozilla/5.0 WINK/1.31.1 (AndroidTV/7.1.1) HlsWinkPlayer",
    "WINK/1.28.2 (AndroidTV/9) HlsWinkPlayer",
    "ru.rt.video.player.hls.HlsWinkPlayer",
    "HlsWinkPlayer",
    "Wink/1.31.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 6.0; Wink_Share_SE) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.92 Mobile Safari/537.36",
    "VLC/3.0.20 LibVLC/3.0.20",
]

# Увеличили до 8 потоков на хост для ускорения
host_locks: dict[str, threading.Semaphore] = defaultdict(lambda: threading.Semaphore(8))
host_locks_guard = threading.Lock()


def log(msg):
    print(msg)
    sys.stdout.flush()


def get_host(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return url


def get_host_lock(host):
    with host_locks_guard:
        return host_locks[host]


def m3u_clean(s):
    if not s:
        return ""
    return s.replace('"', "'").replace("\r", " ").replace("\n", " ").strip()


def _attempt(url, user_agent, use_range, timeout):
    headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Connection": "close",
    }
    if use_range:
        headers["Range"] = "bytes=0-1024"

    host = get_host(url)
    lock = get_host_lock(host)

    start = time.time()
    try:
        with lock:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                if resp.status not in (200, 206):
                    return False, 999.0, f"status_{resp.status}"
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" in ctype:
                    return False, 999.0, "html_stub"
                chunk = resp.read(1024)
                if not chunk:
                    return False, 999.0, "empty_body"
        return True, round(time.time() - start, 3), "ok"
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return False, 999.0, "http_403"
        return False, 999.0, f"http_{e.code}"
    except Exception:
        return False, 999.0, "network_error"


def check_stream(ch, retry=False):
    url = ch.get("url")
    saved_ua = ch.get("user_agent")
    
    agents_to_try = list(CHECKER_AGENTS)
    
    if saved_ua:
        if saved_ua in agents_to_try:
            agents_to_try.remove(saved_ua)
        agents_to_try.insert(0, saved_ua)
        
    got_403 = False
    last_403_ua = None
    
    for ua in agents_to_try:
        use_range = not retry
        timeout = 5 if retry else 3  # <--- УМЕНЬШИЛИ ТАЙМАУТЫ (было 7 и 5)
        
        ok, latency, reason = _attempt(url, ua, use_range, timeout)
        
        if ok:
            ch["user_agent"] = ua
            return ch, True, latency
            
        if reason == "http_403":
            got_403 = True
            last_403_ua = ua
            continue  # Если 403 - пробуем следующий UA
        elif reason == "html_stub":
            continue  # Если HTML-заглушка - тоже пробуем следующий UA
        else:
            # Если таймаут, 404, network_error - сервер мертв. Менять UA бесполезно.
            break
            
    if got_403:
        ch["user_agent"] = last_403_ua
        return ch, True, 999.0
        
    return ch, False, 999.0


def build_index_html(dashboard_data, active_count, total):
    channels_json = json.dumps(dashboard_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ru" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IPTV Auto Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script>tailwind.config = {{ darkMode: 'class' }}</script>
    <style>
        .spark {{ display: inline-flex; align-items: flex-end; gap: 1px; height: 14px; }}
        .spark i {{ display: inline-block; width: 3px; border-radius: 1px; }}
        .spark i.on  {{ background: #22c55e; }}
        .spark i.off {{ background: #475569; }}
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <header class="bg-gray-800 border-b border-gray-700 sticky top-0 z-50 p-4 shadow-md">
        <div class="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
            <h1 class="text-2xl font-bold bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">📺 IPTV Control Center</h1>
            <div class="flex items-center gap-3 w-full md:w-auto">
                <input type="text" id="searchInput" placeholder="Поиск каналов..." class="bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 w-full md:w-64 focus:outline-none focus:border-blue-500">
                <button onclick="toggleTheme()" class="bg-gray-700 p-2 rounded-lg hover:bg-gray-600 transition">🌓</button>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto p-4 md:p-6 space-y-6">
        <div class="bg-gray-800 p-4 rounded-xl border border-gray-700 flex flex-wrap gap-4 justify-between items-center">
            <div>
                <h3 class="font-semibold text-lg">Прямые ссылки плейлиста</h3>
                <p class="text-sm text-gray-400">Используйте в TiviMate, OTT Navigator или VLC</p>
                <p class="text-xs text-gray-500 mt-1">Активных: {active_count} из {total}</p>
            </div>
            <div class="flex gap-2">
                <button onclick="copyToClipboard(window.location.origin + window.location.pathname.replace('index.html', '') + 'playlist.m3u')" class="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-sm font-medium transition">📋 Копировать M3U</button>
                <button onclick="copyToClipboard('{EPG_URL}')" class="bg-indigo-600 hover:bg-indigo-500 px-4 py-2 rounded-lg text-sm font-medium transition">⚡ Копировать EPG</button>
            </div>
        </div>

        <div class="flex flex-wrap items-center gap-3">
            <div id="categoryFilters" class="flex flex-wrap gap-2 flex-1"></div>
            <label class="flex items-center gap-2 bg-gray-800 border border-gray-700 px-3 py-2 rounded-lg text-sm cursor-pointer select-none">
                <input type="checkbox" id="stableOnly" class="accent-blue-500">
                <span>Только стабильные (≥80%)</span>
            </label>
        </div>

        <div id="channelsGrid" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4"></div>
        <div id="emptyState" class="hidden text-center text-gray-500 py-10">Ничего не найдено</div>
    </main>

    <div id="playerModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm hidden z-50 flex items-center justify-center p-4">
        <div class="bg-gray-800 rounded-2xl w-full max-w-3xl overflow-hidden border border-gray-700 shadow-2xl">
            <div class="flex justify-between items-center p-4 border-b border-gray-700">
                <h3 id="modalTitle" class="font-bold text-lg">Плеер</h3>
                <button onclick="closePlayer()" class="text-gray-400 hover:text-white text-xl font-bold">&times;</button>
            </div>
            <div class="relative aspect-video bg-black">
                <video id="videoPlayer" controls autoplay class="w-full h-full"></video>
            </div>
        </div>
    </div>

    <script>
        const channelsData = {channels_json};
        let currentCategory = 'All';
        let hls = null;
        let currentFiltered = [];

        function esc(s) {{
            return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
        }}

        function sparkline(history) {{
            if (!history || !history.length) return '<span class="spark"></span>';
            const maxH = 14;
            const bars = history.map(v => {{
                const h = v ? maxH : Math.max(2, maxH / 3);
                const cls = v ? 'on' : 'off';
                return `<i class="${{cls}}" style="height:${{h}}px"></i>`;
            }}).join('');
            return `<span class="spark" title="${{history.join('')}}">${{bars}}</span>`;
        }}

        function renderCategories() {{
            const container = document.getElementById('categoryFilters');
            const categories = ['All', ...new Set(channelsData.map(c => c.group))];
            container.innerHTML = categories.map(cat => `
                <button data-cat="${{esc(cat)}}" class="category-btn ${{cat === currentCategory ? 'bg-blue-600' : 'bg-gray-800 hover:bg-gray-700'}} border border-gray-700 px-4 py-2 rounded-lg text-sm font-medium transition">
                    ${{cat === 'All' ? 'Все каналы' : esc(cat)}}
                </button>
            `).join('');
            container.querySelectorAll('.category-btn').forEach(btn => {{
                btn.addEventListener('click', () => filterCategory(btn.dataset.cat));
            }});
        }}

        function filterCategory(cat) {{
            currentCategory = cat;
            renderCategories();
            renderChannels();
        }}

        function renderChannels() {{
            const search = document.getElementById('searchInput').value.toLowerCase();
            const stableOnly = document.getElementById('stableOnly').checked;
            const grid = document.getElementById('channelsGrid');
            const empty = document.getElementById('emptyState');

            currentFiltered = channelsData.filter(c => {{
                const matchCat = currentCategory === 'All' || c.group === currentCategory;
                const matchSearch = c.name.toLowerCase().includes(search);
                const matchStable = !stableOnly || c.stability >= 80;
                return matchCat && matchSearch && matchStable;
            }});

            if (!currentFiltered.length) {{
                grid.innerHTML = '';
                empty.classList.remove('hidden');
                return;
            }}
            empty.classList.add('hidden');

            grid.innerHTML = currentFiltered.map((c, i) => `
                <div class="channel-card bg-gray-800 border border-gray-700 hover:border-blue-500 rounded-xl p-4 flex items-center gap-4 cursor-pointer transition transform hover:-translate-y-1" data-idx="${{i}}">
                    ${{c.logo
                        ? `<img src="${{esc(c.logo)}}" alt="" class="w-12 h-12 object-contain bg-gray-900 rounded-lg p-1" onerror="this.style.visibility='hidden'">`
                        : `<div class="w-12 h-12 bg-gray-900 rounded-lg"></div>`}}
                    <div class="overflow-hidden flex-1">
                        <h4 class="font-semibold truncate">${{esc(c.name)}}</h4>
                        <div class="flex items-center gap-2 mt-1">
                            <span class="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">${{esc(c.group)}}</span>
                            <span class="text-xs text-green-400 font-mono">${{c.latency < 999 ? c.latency + 's' : 'offline'}}</span>
                            ${{sparkline(c.history)}}
                        </div>
                    </div>
                </div>
            `).join('');

            grid.querySelectorAll('.channel-card').forEach(el => {{
                el.addEventListener('click', () => {{
                    const c = currentFiltered[parseInt(el.dataset.idx, 10)];
                    playChannel(c.url, c.name);
                }});
            }});
        }}

        function playChannel(url, name) {{
            const modal = document.getElementById('playerModal');
            const video = document.getElementById('videoPlayer');
            document.getElementById('modalTitle').innerText = name;
            modal.classList.remove('hidden');

            if (Hls.isSupported()) {{
                if (hls) hls.destroy();
                hls = new Hls();
                hls.loadSource(url);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, () => video.play());
            }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
                video.src = url;
                video.addEventListener('loadedmetadata', () => video.play());
            }}
        }}

        function closePlayer() {{
            const modal = document.getElementById('playerModal');
            const video = document.getElementById('videoPlayer');
            video.pause();
            video.src = "";
            if (hls) hls.destroy();
            modal.classList.add('hidden');
        }}

        function toggleTheme() {{
            document.documentElement.classList.toggle('dark');
        }}

        function copyToClipboard(text) {{
            navigator.clipboard.writeText(text);
            alert('Ссылка скопирована в буфер обмена!');
        }}

        document.getElementById('searchInput').addEventListener('input', renderChannels);
        document.getElementById('stableOnly').addEventListener('change', renderChannels);
        renderCategories();
        renderChannels();
    </script>
</body>
</html>"""


def main():
    log("[*] Запуск проверки каналов...")
    if not os.path.exists("channels.json"):
        raise SystemExit("[!] channels.json не найден. Сначала запустите parser.py")

    with open("channels.json", "r", encoding="utf-8") as f:
        channels = json.load(f)

    total = len(channels)
    if total == 0:
        raise SystemExit("[!] channels.json пуст — нечего проверять")

    log(f"[*] Всего каналов: {total}. Проверка (проход 1)...")

    checked = 0
    failed_channels = []
    ok_count = 0
    next_report = 0

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(check_stream, ch) for ch in channels]
        for future in as_completed(futures):
            ch, success, latency = future.result()
            checked += 1

            if success:
                ch["fail_count"] = 0
                ch["latency"] = latency
                ch["_first_pass_ok"] = True
                ok_count += 1
            else:
                ch["_first_pass_ok"] = False
                failed_channels.append(ch)

            percent = checked * 100 // total
            if percent >= next_report:
                filled = int(percent / 5)
                bar = "█" * filled + "░" * (20 - filled)
                log(f"[{bar}] {percent}% ({checked}/{total}) | Живых: {ok_count} | Упало: {len(failed_channels)}")
                next_report = percent + 5

    log(f"[*] Проход 1 завершён. Успешно: {ok_count}, провалов: {len(failed_channels)}")

    if failed_channels:
        log(f"[*] Ретрай для {len(failed_channels)} каналов (пауза 2с, мягкий режим)...")
        time.sleep(2)
        
        retry_ok = 0
        retry_checked = 0
        retry_total = len(failed_channels)
        next_report = 0

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(check_stream, ch, True) for ch in failed_channels]
            for future in as_completed(futures):
                ch, success, latency = future.result()
                retry_checked += 1
                
                if success:
                    retry_ok += 1
                    ch["fail_count"] = 0
                    ch["latency"] = latency
                    ch["_first_pass_ok"] = True
                    
                percent = retry_checked * 100 // retry_total
                if percent >= next_report:
                    filled = int(percent / 5)
                    bar = "█" * filled + "░" * (20 - filled)
                    log(f"[{bar}] {percent}% РЕТРАЙ ({retry_checked}/{retry_total}) | Восстановлено: {retry_ok}")
                    next_report = percent + 10
                    
        log(f"[*] Ретрай: восстановлено {retry_ok} из {len(failed_channels)}")

    for ch in channels:
        first_pass_ok = ch.pop("_first_pass_ok", False)
        history = ch.get("history", [])
        history.append(1 if first_pass_ok else 0)
        if len(history) > 10:
            history.pop(0)
        ch["history"] = history

        if not first_pass_ok:
            ch["fail_count"] = ch.get("fail_count", 0) + 1
            ch["latency"] = 999.0

    log("[+] Проверка завершена. Сохранение...")

    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

    active_channels = [c for c in channels if c.get("fail_count", 0) < 5]
    log(f"[*] Активных каналов после фильтрации: {len(active_channels)}")

    active_channels.sort(key=lambda x: (x.get("group", ""), x.get("name", "")))

    lines = [f'#EXTM3U url-tvg="{EPG_URL}"']
    for ch in active_channels:
        tvg_id_attr = f' tvg-id="{m3u_clean(ch["tvg_id"])}"' if ch.get("tvg_id") else ""
        logo_attr = f' tvg-logo="{m3u_clean(ch["logo"])}"' if ch.get("logo") else ""
        group = m3u_clean(ch.get("group", ""))
        name = m3u_clean(ch.get("name", ""))
        lines.append(f'#EXTINF:-1{tvg_id_attr}{logo_attr} group-title="{group}",{name}')
        
        ua = ch.get("user_agent") or "Wink/1.31.1"
        lines.append(f'#EXTVLCOPT:http-user-agent={ua}')
        
        lines.append(ch["url"])
    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    os.makedirs("playlists", exist_ok=True)
    categories = sorted({c["group"] for c in active_channels})
    for cat in categories:
        cat_channels = [c for c in active_channels if c["group"] == cat]
        cat_lines = [f'#EXTM3U url-tvg="{EPG_URL}"']
        for ch in cat_channels:
            tvg_id_attr = f' tvg-id="{m3u_clean(ch["tvg_id"])}"' if ch.get("tvg_id") else ""
            logo_attr = f' tvg-logo="{m3u_clean(ch["logo"])}"' if ch.get("logo") else ""
            group = m3u_clean(ch.get("group", ""))
            name = m3u_clean(ch.get("name", ""))
            cat_lines.append(f'#EXTINF:-1{tvg_id_attr}{logo_attr} group-title="{group}",{name}')
            
            ua = ch.get("user_agent") or "Wink/1.31.1"
            cat_lines.append(f'#EXTVLCOPT:http-user-agent={ua}')
            
            cat_lines.append(ch["url"])

        safe_name = re.sub(r'[^a-zа-я0-9]+', '_', cat.lower()).strip('_') or "other"
        with open(f"playlists/{safe_name}.m3u", "w", encoding="utf-8") as f:
            f.write("\n".join(cat_lines) + "\n")

    dashboard_data = []
    for c in active_channels:
        hist = c.get("history") or [0]
        stability = round(sum(hist) / len(hist) * 100) if hist else 0
        dashboard_data.append({
            "name": c["name"],
            "group": c["group"],
            "logo": c.get("logo", ""),
            "url": c["url"],
            "latency": c["latency"],
            "stability": stability,
            "history": hist,
        })

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(build_index_html(dashboard_data, len(active_channels), total))
    log("[+] index.html сгенерирован")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    latencies = [c["latency"] for c in active_channels if c.get("latency", 999) < 999]
    avg_ping = f"{round(sum(latencies) / len(latencies) * 1000)} ms" if latencies else "—"

    cat_counts = defaultdict(int)
    for c in active_channels:
        cat_counts[c["group"]] += 1

    cat_lines = "\n".join(
        f"* **{cat}:** `{n} каналов`"
        for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1])
    )

    readme = f"""# ⚡ Omega IPTV Auto-Checker (Wink Edition)

![Build Status](https://github.com/Gvineon550-coder/omega-iptv/actions/workflows/iptv.yml/badge.svg)

Профессиональный автоматический парсер, валидатор потоков и генератор плейлистов с пинг-аналитикой. Работает автономно на GitHub Actions.

## 📊 Статус системы
* **Последнее обновление:** `{now}`
* **Всего каналов в базе:** `{total}`
* **Активных каналов:** `{len(active_channels)}`
* **Средний пинг:** `{avg_ping}`

### 📂 Распределение по категориям
{cat_lines}

---

## 🔗 Ссылки для плеера
* **Прямая ссылка на M3U плейлист (с авто-EPG):**
  `https://raw.githubusercontent.com/Gvineon550-coder/omega-iptv/main/playlist.m3u`
* **Ссылка на телепрограмму (RU EPG):**
  `{EPG_URL}`

## 🌐 Веб-дашборд
* [Открыть интерактивную панель управления (GitHub Pages)](https://Gvineon550-coder.github.io/omega-iptv/)
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)
    log("[+] README.md сгенерирован")

    log(f"[+] Готово. Проверено: {total}, активных: {len(active_channels)}")


if __name__ == "__main__":
    main()
