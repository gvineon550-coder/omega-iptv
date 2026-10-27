import urllib.request
import re
import json

URLS = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u"
]

def guess_category(name):
    name_lower = name.lower()
    if any(w in name_lower for w in ["спорт", "матч", "футбол", "хоккей", "боец", "arena", "sport"]):
        return "Спорт"
    elif any(w in name_lower for w in ["кино", "фильм", "сериал", "премиум", "cinema", "serial", "movie", "rtl", "fox"]):
        return "Кино и Сериалы"
    elif any(w in name_lower for w in ["новост", "вести", "ррб", "рбк", "известия", "news"]):
        return "Новости"
    elif any(w in name_lower for w in ["дет", "мульт", "карусель", "disney", "nickelodeon", "kids"]):
        return "Детские"
    elif any(w in name_lower for w in ["познавательн", "история", "наука", "discovery", "nat geo", "animal", "rtdoc"]):
        return "Познавательные"
    elif any(w in name_lower for w in ["музык", "mtv", "ru.tv", "муз-тв", "music"]):
        return "Музыка"
    return "Общие"

def parse_playlist():
    channels = []
    seen_urls = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        "Referer": "https://iptv-org.github.io/"
    }

    for url in URLS:
        print(f"[*] Загрузка базы с {url}...")
        req = urllib.request.Request(url, headers=headers)
        
        current_title = "Unknown"
        current_group = "Общие"
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                lines = response.read().decode("utf-8", errors="ignore").splitlines()
                for line in lines:
                    line = line.strip()
                    if line.startswith("#EXTINF:"):
                        group_match = re.search(r'group-title="([^"]+)"', line, re.IGNORECASE)
                        if group_match:
                            current_group = group_match.group(1).strip()
                        
                        name_match = re.search(r',(.+)$', line)
                        if name_match:
                            current_title = name_match.group(1).strip()
                            if not current_group or current_group.lower() in ["undefined", "general"]:
                                current_group = guess_category(current_title)
                    
                    elif line and not line.startswith("#"):
                        if line not in seen_urls:
                            seen_urls.add(line)
                            channels.append({
                                "name": current_title,
                                "group": current_group,
                                "url": line
                            })
        except Exception as e:
            print(f"[!] Ошибка загрузки {url}: {e}")

    print(f"[*] Всего уникальных каналов с категориями: {len(channels)}")
    return channels[:300]

if __name__ == "__main__":
    data = parse_playlist()
    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("[+] Парсинг и дедупликация завершены")
