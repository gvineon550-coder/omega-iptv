import json
import urllib.request
import re

def parse_m3u_from_url(url):
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
            
            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF:"):
                    # Ищем категорию (группу)
                    group_match = re.search(r'group-title="([^"]+)"', line)
                    if group_match:
                        current_group = group_match.group(1)
                    else:
                        current_group = "Общие"
                    
                    # Ищем название канала после запятой
                    parts = line.split(',')
                    if len(parts) > 1:
                        current_name = parts[-1].strip()
                elif line and not line.startswith("#"):
                    if current_name:
                        channels.append({
                            "name": current_name,
                            "group": current_group,
                            "url": line
                        })
                        current_name = ""
    except Exception as e:
        print(f"[!] Ошибка при скачивании {url}: {e}")
    
    return channels

def main():
    # Расширенный список мастер-листов iptv-org (Россия + Русский язык)
    sources = [
        "https://iptv-org.github.io/iptv/countries/ru.m3u",
        "https://iptv-org.github.io/iptv/languages/rus.m3u"
    ]
    
    all_channels = []
    for src in sources:
        print(f"[*] Загрузка базы с {src}...")
        parsed = parse_m3u_from_url(src)
        print(f"[+] Найдено каналов в источнике: {len(parsed)}")
        all_channels.extend(parsed)

    # Дедупликация по URL (чтобы избежать повторов)
    unique_channels = {}
    for ch in all_channels:
        if ch["url"] not in unique_channels:
            unique_channels[ch["url"]] = ch

    final_list = list(unique_channels.values())

    print(f"[*] Всего уникальных каналов после объединения: {len(final_list)}")

    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    
    print("[+] Парсинг завершен, все каналы сохранены в channels.json")

if __name__ == "__main__":
    main()
