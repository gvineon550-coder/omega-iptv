import json
import urllib.request
import os
import re
from urllib.parse import urlparse

def normalize_name(name):
    """Приводит название канала к единому виду для поиска дубликатов, логотипов и tvg-id"""
    name = name.lower().strip()
    name = re.sub(r'\b(hd|sd|4k|fhd|hq|1080p|720p|576i)\b', '', name)
    name = re.sub(r'[^а-яa-z0-9]', '', name)
    return name

def is_valid_url(url):
    """Отсекает заведомо мусорные и невалидные ссылки"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            return False
        host = parsed.netloc.lower()
        if not host or 'localhost' in host or '127.0.0.1' in host or '0.0.0.0' in host:
            return False
        bad_extensions = ['.html', '.php', '.asp', '.htm']
        if any(parsed.path.lower().endswith(ext) for ext in bad_extensions):
            return False
        return True
    except Exception:
        return False

def smart_categorize(name, current_group):
    """Автоматически распределяет каналы по понятным категориям"""
    name_lower = name.lower()
    
    if any(k in name_lower for k in ['спорт', 'матч', 'футбол', 'хоккей', 'бой', 'sport', 'fight']):
        return 'Спорт'
    elif any(k in name_lower for k in ['кино', 'фильм', 'премиум', 'cinema', 'movie', 'строго', 'тв-3', 'стс', 'тнт']):
        return 'Кино и Сериалы'
    elif any(k in name_lower for k in ['новост', 'вести', 'известия', 'рнв', 'соловьев', 'news']):
        return 'Новости'
    elif any(k in name_lower for k in ['детск', 'мульт', 'карусель', 'disney', 'nickelodeon', 'kids', 'baby']):
        return 'Детские'
    elif any(k in name_lower for k in ['познавательн', 'история', 'наук', 'discovery', 'national geographic', 'animal', 'science', 'viasat explore']):
        return 'Познавательные'
    elif any(k in name_lower for k in ['музык', 'mtv', 'ru.tv', 'bridge', 'music', 'vh1']):
        return 'Музыка'
    
    if not current_group or current_group.lower() in ['общие', 'general', 'uncategorized', 'other']:
        return 'Общие'
        
    return current_group

def load_iptv_org_epg_map():
    """Загружает официальную базу каналов iptv-org для сопоставления tvg-id"""
    epg_map = {}
    url = "https://iptv-org.github.io/api/channels.json"
    print("[*] Загрузка официальной базы tvg-id (iptv-org)...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            channels_data = json.loads(response.read().decode('utf-8'))
            for item in channels_data:
                channel_id = item.get("id")
                if not channel_id:
                    continue
                names_to_check = [item.get("name")] + item.get("alt_names", [])
                for alias in names_to_check:
                    if alias:
                        norm = normalize_name(alias)
                        if norm and norm not in epg_map:
                            epg_map[norm] = channel_id
        print(f"[+] База tvg-id успешно загружена. Записей: {len(epg_map)}")
    except Exception as e:
        print(f"[!] Не удалось загрузить базу tvg-id: {e}")
    return epg_map

def parse_m3u_from_url(url, source_index, global_logos_by_norm_name, epg_map):
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
            current_tvg_id = ""
            
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

                    tvg_match = re.search(r'tvg-id="([^"]+)"', line)
                    if tvg_match:
                        current_tvg_id = tvg_match.group(1)
                    else:
                        current_tvg_id = ""
                    
                    parts = line.split(',')
                    if len(parts) > 1:
                        current_name = parts[-1].strip()
                elif line and not line.startswith("#"):
                    if current_name:
                        if not is_valid_url(line):
                            current_name = ""
                            current_logo = ""
                            current_tvg_id = ""
                            continue

                        logo = current_logo
                        norm_name = normalize_name(current_name)
                        
                        if source_index == 2 and not logo:
                            if norm_name in global_logos_by_norm_name:
                                logo = global_logos_by_norm_name[norm_name]

                        if logo and norm_name and norm_name not in global_logos_by_norm_name:
                            global_logos_by_norm_name[norm_name] = logo

                        tvg_id = current_tvg_id
                        if not tvg_id and norm_name in epg_map:
                            tvg_id = epg_map[norm_name]

                        custom_ua = None
                        if re.search(r'[\+\-]\d+', current_name):
                            custom_ua = "HlsWinkPlayer"

                        final_group = smart_categorize(current_name, current_group)

                        channels.append({
                            "name": current_name,
                            "group": final_group,
                            "logo": logo,
                            "tvg_id": tvg_id,
                            "url": line,
                            "user_agent": custom_ua,
                            "norm_name": norm_name
                        })
                        current_name = ""
                        current_logo = ""
                        current_tvg_id = ""
    except Exception as e:
        print(f"[!] Ошибка при скачивании {url}: {e}")
    
    return channels

def main():
    old_fail_counts = {}
    if os.path.exists("channels.json"):
        try:
            with open("channels.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
                for ch in old_data:
                    if "url" in ch and "fail_count" in ch:
                        old_fail_counts[ch["url"]] = ch["fail_count"]
        except Exception:
            pass

    epg_map = load_iptv_org_epg_map()

    sources = [
        "https://iptv-org.github.io/iptv/countries/ru.m3u",
        "https://iptv-org.github.io/iptv/languages/rus.m3u",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u"
    ]
    
    all_channels = []
    global_logos_by_norm_name = {}

    for idx, src in enumerate(sources):
        print(f"[*] Загрузка базы с {src} (источник #{idx + 1})...")
        parsed = parse_m3u_from_url(src, idx, global_logos_by_norm_name, epg_map)
        print(f"[+] Найдено каналов в источнике: {len(parsed)}")
        all_channels.extend(parsed)

    unique_by_url = {}
    for ch in all_channels:
        if ch["url"] not in unique_by_url:
            ch["fail_count"] = old_fail_counts.get(ch["url"], 0)
            unique_by_url[ch["url"]] = ch
        else:
            if not unique_by_url[ch["url"]].get("logo") and ch.get("logo"):
                unique_by_url[ch["url"]]["logo"] = ch["logo"]
            if not unique_by_url[ch["url"]].get("tvg_id") and ch.get("tvg_id"):
                unique_by_url[ch["url"]]["tvg_id"] = ch["tvg_id"]

    unique_channels = {}
    for ch in unique_by_url.values():
        n_name = ch["norm_name"]
        if n_name not in unique_channels:
            unique_channels[n_name] = ch
        else:
            if not unique_channels[n_name].get("logo") and ch.get("logo"):
                unique_channels[n_name]["logo"] = ch["logo"]
            if not unique_channels[n_name].get("tvg_id") and ch.get("tvg_id"):
                unique_channels[n_name]["tvg_id"] = ch["tvg_id"]

    final_list = list(unique_channels.values())

    print(f"[*] Всего уникальных каналов после фильтрации: {len(final_list)}")

    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    
    print("[+] Парсинг завершен, данные сохранены в channels.json")

if __name__ == "__main__":
    main()
