import json
import urllib.request
import os
import re
import sys
from urllib.parse import urlparse

def log(msg):
    print(msg)
    sys.stdout.flush()

def normalize_name(name):
    name = name.lower().strip()
    name = re.sub(r'\b(hd|sd|4k|fhd|hq|1080p|720p|576i)\b', '', name)
    name = re.sub(r'[^а-яa-z0-9]', '', name)
    return name

def is_valid_url(url):
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
    name_lower = str(name).lower()
    group_lower = str(current_group).lower()

    if any(k in name_lower for k in ['shop', 'магазин', 'покупк', 'ювелир', 'home shopping', 'top shop']):
        return 'Магазины'

    federal_keywords = [
        'первый', 'россия 1', 'россия-1', 'нтв', 'матч тв', 'пятый канал', '5 канал', 
        'отр', 'тв центр', 'твц', 'рен тв', 'спас', 'стс', 'домашний', 'тв-3', 'тв3', 
        'пятница', 'звезда', 'мир', 'тнт', 'муз тв', 'ю', 'че', 'суббота', 'солнце', 'ю-тв'
    ]
    if any(k in name_lower for k in federal_keywords) and not 'регион' in name_lower:
        return 'Федеральные'

    regional_keywords = [
        'гтрк', 'регион', 'область', 'край', 'москва 24', 'санкт-петербург', 
        'сибир', 'урал', 'кубан', 'дон', 'ника', 'телеканал санкт', 'региональный'
    ]
    if any(k in name_lower for k in regional_keywords) or 'local' in group_lower or 'regional' in group_lower:
        return 'Региональные'

    sports_keywords = ['спорт', 'матч!', 'футбол', 'хоккей', 'бой', 'бокс', 'ufc', 'formula', 'sport', 'fight', 'racing', 'nfl', 'nba', 'кхл', 'рпл', 'arena', 'extreme']
    if any(k in name_lower for k in sports_keywords) or 'sport' in group_lower or 'спорт' in group_lower:
        return 'Спорт'
        
    music_keywords = ['музык', 'mtv', 'ru.tv', 'bridge', 'music', 'vh1', 'mcm', 'muz', 'europa plus', 'рекорд', 'chanson', 'strana', 'energy', 'ля-минор']
    if any(k in name_lower for k in music_keywords) or 'music' in group_lower or 'музыка' in group_lower:
        return 'Музыка'

    kids_keywords = ['детск', 'мульт', 'карусель', 'disney', 'nickelodeon', 'kids', 'baby', 'animation', 'cartoon', 'радость моя', 'tiji', 'gulli', 'mult', 'никилодеон']
    if any(k in name_lower for k in kids_keywords) or 'kids' in group_lower or 'детские' in group_lower or 'animation' in group_lower:
        return 'Детские'

    news_keywords = ['новост', 'вести', 'известия', 'рнв', 'соловьев', 'news', 'рбк', 'cnn', 'bbc', 'euronews', 'мир 24', 'коммерсант', 'rbc']
    if any(k in name_lower for k in news_keywords) or 'news' in group_lower or 'новости' in group_lower:
        return 'Новости'

    movie_keywords = ['кино', 'фильм', 'сериал', 'movie', 'film', 'series', 'cinema', 'премиум', 'строго', 'paramount', 'hbo', 'mediateka', 'кинопремьера', 'fox', 'tv1000', 'amedia', 'мост', 'картин', 'русский роман', 'эгоист']
    if any(k in name_lower for k in movie_keywords) or any(g in group_lower for g in ['movies', 'series', 'кино', 'фильмы']):
        return 'Кино и Сериалы'

    doc_keywords = ['познавательн', 'история', 'наук', 'discovery', 'national geographic', 'animal', 'science', 'travel', 'documentary', 'docu', 'viasat explore', 'nature', 'outdoor', 'auto', 'education', 'охота', 'рыбалка', 'живая природа', 'наука', 'живой']
    if any(k in name_lower for k in doc_keywords) or any(g in group_lower for g in ['documentary', 'science', 'travel', 'education', 'outdoor']):
        return 'Познавательные'

    religious_keywords = ['религ', 'пасха', 'спас', 'religious', 'god', 'bible', 'союз', 'троица']
    if any(k in name_lower for k in religious_keywords) or 'religious' in group_lower:
        return 'Религиозные'

    fun_keywords = ['развлекательн', 'comedy', 'lifestyle', 'fashion', 'relax', 'entertainment', 'cooking', 'family', 'ржд', 'юмор', 'пельмени', 'наша rasha']
    if any(k in name_lower for k in fun_keywords) or any(g in group_lower for g in ['entertainment', 'lifestyle', 'cooking', 'family']):
        return 'Развлекательные'

    return 'Общие'

def load_iptv_org_epg_map():
    epg_map = {}
    url = "https://iptv-org.github.io/api/channels.json"
    log("[*] Загрузка официальной базы tvg-id (iptv-org)...")
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
        log(f"[+] База tvg-id успешно загружена. Записей: {len(epg_map)}")
    except Exception as e:
        log(f"[!] Ошибка загрузки базы tvg-id: {e}")
    return epg_map

def parse_m3u_from_url(url, source_index, global_logos_by_norm_name, epg_map):
    log(f"[*] Скачивание плейлиста из источника #{source_index + 1}: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    channels = []
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
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
                    current_group = group_match.group(1) if group_match else "Общие"
                    logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                    current_logo = logo_match.group(1) if logo_match else ""
                    tvg_match = re.search(r'tvg-id="([^"]+)"', line)
                    current_tvg_id = tvg_match.group(1) if tvg_match else ""
                    
                    parts = line.split(',')
                    if len(parts) > 1:
                        current_name = parts[-1].strip()
                elif line and not line.startswith("#"):
                    if current_name:
                        if not is_valid_url(line):
                            current_name, current_logo, current_tvg_id = "", "", ""
                            continue

                        norm_name = normalize_name(current_name)
                        logo = current_logo
                        
                        if source_index == 2 and not logo:
                            if norm_name in global_logos_by_norm_name:
                                logo = global_logos_by_norm_name[norm_name]

                        if logo and norm_name and norm_name not in global_logos_by_norm_name:
                            global_logos_by_norm_name[norm_name] = logo

                        tvg_id = current_tvg_id
                        if not tvg_id or tvg_id == "None":
                            tvg_id = epg_map.get(norm_name, norm_name)

                        custom_ua = "HlsWinkPlayer" if re.search(r'[\+\-]\d+', current_name) else None
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
                        current_name, current_logo, current_tvg_id = "", "", ""
        log(f"[+] Источник #{source_index + 1} обработан. Найдено каналов: {len(channels)}")
    except Exception as e:
        log(f"[!] Ошибка при скачивании источника {url}: {e}")
    return channels

def main():
    log("[*] Запуск парсера каналов...")
    old_data_map = {}
    if os.path.exists("channels.json"):
        try:
            with open("channels.json", "r", encoding="utf-8") as f:
                old_list = json.load(f)
                for ch in old_list:
                    if "url" in ch:
                        old_data_map[ch["url"]] = ch
            log(f"[*] Загружен старый кэш. Каналов в кэше: {len(old_data_map)}")
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
        parsed = parse_m3u_from_url(src, idx, global_logos_by_norm_name, epg_map)
        all_channels.extend(parsed)

    unique_by_url = {}
    for ch in all_channels:
        url = ch["url"]
        if url not in unique_by_url:
            old_item = old_data_map.get(url, {})
            ch["fail_count"] = old_item.get("fail_count", 0)
            ch["latency"] = old_item.get("latency", 999.0)
            ch["history"] = old_item.get("history", [])
            unique_by_url[url] = ch
        else:
            if not unique_by_url[url].get("logo") and ch.get("logo"):
                unique_by_url[url]["logo"] = ch["logo"]

    final_list = list(unique_by_url.values())
    log(f"[*] Всего уникальных ссылок: {len(final_list)}")

    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    
    log("[+] Парсинг успешно завершен, данные сохранены в channels.json")

if __name__ == "__main__":
    main()
