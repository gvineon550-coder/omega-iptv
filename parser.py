import json
import urllib.request
import re

def parse_m3u_from_url(url, source_index, global_logos_by_name):
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    channels = []
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8', errors='ignore')
            
            lines = content.splitlines()
            current_group = "Общие"
            current_name = ""
            current_logo = ""
            
            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF:"):
                    group_match = re.search(r'group-title="([^"]+)"', line)
                    if group_match:
                        current_group = group_match.group(1)
                    else:
                        current_group = "Общие"
                    
                    logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                    if logo_match:
                        current_logo = logo_match.group(1)
                    else:
                        current_logo = ""
                    
                    parts = line.split(',')
                    if len(parts) > 1:
                        current_name = parts[-1].strip()
                elif line and not line.startswith("#"):
                    if current_name:
                        logo = current_logo
                        
                        # Если это третий источник (индекс 2, т.е. raw) и у него нет логотипа,
                        # пытаемся найти логотип по названию канала из других источников
                        if source_index == 2 and not logo:
                            if current_name in global_logos_by_name:
                                logo = global_logos_by_name[current_name]

                        # Если логотип нашелся, сохраняем его в глобальный словарь для будущих совпадений
                        if logo and current_name not in global_logos_by_name:
                            global_logos_by_name[current_name] = logo

                        # Определяем, нужен ли user-agent hlswinkplayer (если в названии есть + или -)
                        custom_ua = None
                        if re.search(r'[\+\-]\d+', current_name):
                            custom_ua = "hlswinkplayer"

                        channels.append({
                            "name": current_name,
                            "group": current_group,
                            "logo": logo,
                            "url": line,
                            "user_agent": custom_ua
                        })
                        current_name = ""
                        current_logo = ""
    except Exception as e:
        print(f"[!] Ошибка при скачивании {url}: {e}")
    
    return channels

def main():
    sources = [
        "https://iptv-org.github.io/iptv/countries/ru.m3u",
        "https://iptv-org.github.io/iptv/languages/rus.m3u",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u"  # Третий источник (raw)
    ]
    
    all_channels = []
    global_logos_by_name = {}

    # Сначала парсим первые два источника, чтобы собрать базу логотипов по именам каналов
    for idx, src in enumerate(sources):
        print(f"[*] Загрузка базы с {src} (источник #{idx + 1})...")
        parsed = parse_m3u_from_url(src, idx, global_logos_by_name)
        print(f"[+] Найдено каналов в источнике: {len(parsed)}")
        all_channels.extend(parsed)

    # Дедупликация по URL
    unique_channels = {}
    for ch in all_channels:
        if ch["url"] not in unique_channels:
            unique_channels[ch["url"]] = ch
        else:
            if not unique_channels[ch["url"]].get("logo") and ch.get("logo"):
                unique_channels[ch["url"]]["logo"] = ch["logo"]
            if not unique_channels[ch["url"]].get("user_agent") and ch.get("user_agent"):
                unique_channels[ch["url"]]["user_agent"] = ch["user_agent"]

    final_list = list(unique_channels.values())

    print(f"[*] Всего уникальных каналов: {len(final_list)}")

    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    
    print("[+] Парсинг завершен, все данные сохранены в channels.json")

if __name__ == "__main__":
    main()
