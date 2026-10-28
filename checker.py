import json
import urllib.request
import time
import os

def check_stream(url, user_agent=None):
    start_time = time.time()
    headers = {"User-Agent": user_agent or "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            chunk = resp.read(1024)
            if chunk:
                latency = round(time.time() - start_time, 3)
                return True, latency
    except Exception:
        pass
    return False, 999.0

def main():
    if not os.path.exists("channels.json"):
        print("[!] channels.json не найден. Сначала запустите parser.py")
        return

    with open("channels.json", "r", encoding="utf-8") as f:
        channels = json.load(f)

    print(f"[*] Проверка {len(channels)} каналов...")

    for ch in channels:
        success, latency = check_stream(ch.get("url"), ch.get("user_agent"))
        
        # Обновляем историю стабильности (храним последние 10 запусков)
        history = ch.get("history", [])
        history.append(1 if success else 0)
        if len(history) > 10:
            history.pop(0)
        ch["history"] = history

        if success:
            ch["fail_count"] = 0
            ch["latency"] = latency
        else:
            ch["fail_count"] = ch.get("fail_count", 0) + 1
            ch["latency"] = 999.0

    # Сохраняем обновленные данные с историей и пингом в channels.json
    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

    # Фильтруем мертвые каналы (упавшие более 5 раз подряд)
    active_channels = [c for c in channels if c.get("fail_count", 0) < 5]

    # Сортируем внутри групп: сначала стабильные по истории, потом по пингу (скорости)
    active_channels.sort(key=lambda x: (-sum(x.get("history", [0])), x.get("latency", 999.0)))

    # 1. Генерация единого мастер-плейлиста
    master_m3u = '#EXTM3U url-tvg="https://epg.pw/xmltv/epg_RU.xml.gz"\n'
    for ch in active_channels:
        master_m3u += f'#EXTINF:-1 tvg-id="{ch["tvg_id"]}" tvg-logo="{ch["logo"]}" group-title="{ch["group"]}",{ch["name"]}\n'
        if ch.get("user_agent"):
            master_m3u += f'#EXTVLCOPT:http-user-agent={ch["user_agent"]}\n'
        master_m3u += f'{ch["url"]}\n'

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(master_m3u)

    # 2. Генерация раздельных плейлистов по категориям
    os.makedirs("playlists", exist_ok=True)
    categories = set(c["group"] for c in active_channels)
    for cat in categories:
        cat_channels = [c for c in active_channels if c["group"] == cat]
        cat_m3u = '#EXTM3U url-tvg="https://epg.pw/xmltv/epg_RU.xml.gz"\n'
        for ch in cat_channels:
            cat_m3u += f'#EXTINF:-1 tvg-id="{ch["tvg_id"]}" tvg-logo="{ch["logo"]}" group-title="{ch["group"]}",{ch["name"]}\n'
            if ch.get("user_agent"):
                cat_m3u += f'#EXTVLCOPT:http-user-agent={ch["user_agent"]}\n'
            cat_m3u += f'{ch["url"]}\n'
        
        filename = f"playlists/{cat.lower().replace(' ', '_')}.m3u"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(cat_m3u)

    # Подготовка данных для дашборда
    dashboard_data = [{
        "name": c["name"],
        "group": c["group"],
        "logo": c["logo"],
        "url": c["url"],
        "latency": c["latency"],
        "stability": round((sum(c.get("history", [0])) / len(c.get("history", [1]))) * 100)
    } for c in active_channels]

    # 3. Автоматическая генерация index.html с запеченными данными
    html_content = f"""<!DOCTYPE html>
<html lang="ru" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IPTV Auto Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script>tailwind.config = {{ darkMode: 'class' }}</script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen transition-colors duration-300">
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
            </div>
            <div class="flex gap-2">
                <button onclick="copyToClipboard(window.location.origin + window.location.pathname.replace('index.html', '') + 'playlist.m3u')" class="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-lg text-sm font-medium transition">📋 Копировать M3U</button>
                <button onclick="copyToClipboard('https://epg.pw/xmltv/epg_RU.xml.gz')" class="bg-indigo-600 hover:bg-indigo-500 px-4 py-2 rounded-lg text-sm font-medium transition">⚡ Копировать EPG</button>
            </div>
        </div>

        <div id="categoryFilters" class="flex flex-wrap gap-2">
            <button onclick="filterCategory('All')" class="category-btn bg-blue-600 px-4 py-2 rounded-lg text-sm font-medium transition">Все каналы</button>
        </div>

        <div id="channelsGrid" class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4"></div>
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
        const channelsData = {json.dumps(dashboard_data, ensure_ascii=False)};
        let currentCategory = 'All';
        let hls = null;

        function renderCategories() {{
            const container = document.getElementById('categoryFilters');
            const categories = ['All', ...new Set(channelsData.map(c => c.group))];
            container.innerHTML = categories.map(cat => `
                <button onclick="filterCategory('${{cat}}')" class="category-btn ${{cat === currentCategory ? 'bg-blue-600' : 'bg-gray-800 hover:bg-gray-700'}} border border-gray-700 px-4 py-2 rounded-lg text-sm font-medium transition">
                    ${{cat === 'All' ? 'Все каналы' : cat}}
                </button>
            `).join('');
        }}

        function filterCategory(cat) {{
            currentCategory = cat;
            renderCategories();
            renderChannels();
        }}

        function renderChannels() {{
            const search = document.getElementById('searchInput').value.toLowerCase();
            const grid = document.getElementById('channelsGrid');
            const filtered = channelsData.filter(c => {{
                const matchCat = currentCategory === 'All' || c.group === currentCategory;
                const matchSearch = c.name.toLowerCase().includes(search);
                return matchCat && matchSearch;
            }});

            grid.innerHTML = filtered.map(c => `
                <div onclick="playChannel('${{c.url}}', '${{c.name}}')" class="bg-gray-800 border border-gray-700 hover:border-blue-500 rounded-xl p-4 flex items-center gap-4 cursor-pointer transition transform hover:-translate-y-1">
                    <img src="${{c.logo || 'https://via.placeholder.com/48'}}" alt="" class="w-12 h-12 object-contain bg-gray-900 rounded-lg p-1" onerror="this.src='https://via.placeholder.com/48'">
                    <div class="overflow-hidden flex-1">
                        <h4 class="font-semibold truncate">${{c.name}}</h4>
                        <div class="flex items-center gap-2 mt-1">
                            <span class="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">${{c.group}}</span>
                            <span class="text-xs text-green-400 font-mono">${{c.latency < 999 ? c.latency + 's' : 'offline'}}</span>
                        </div>
                    </div>
                </div>
            `).join('');
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
        renderCategories();
        renderChannels();
    </script>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("[+] Проверка завершена. Плейлисты, структура и index.html полностью обновлены.")

if __name__ == "__main__":
    main()
