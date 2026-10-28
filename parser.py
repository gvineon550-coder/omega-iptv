import json
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse


def log(msg):
    print(msg)
    sys.stdout.flush()


def normalize_name(name):
    name = name.lower().strip()
    name = re.sub(r'\b(hd|sd|4k|fhd|hq|1080p|720p|576i|1080|720)\b', '', name)
    name = re.sub(r'[^а-яa-z0-9]', '', name)
    return name


def extract_display_name(extinf_line: str) -> str:
    """Название канала = всё после первой запятой ВНЕ кавычек."""
    in_quotes = False
    for i, ch in enumerate(extinf_line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ',' and not in_quotes:
            return extinf_line[i + 1:].strip()
    return ""


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


def _base_name(name_lower: str) -> str:
    """Убирает качество и скобки — для точного сравнения коротких названий."""
    s = re.sub(r'[\(\)\[\]]', ' ', name_lower)
    s = re.sub(r'\b(hd|sd|fhd|4k|1080p|720p|1080i|576i|576p|480p|480i)\b', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def smart_categorize(name, current_group):
    name_lower = str(name).lower()
    group_lower = str(current_group).lower()

    # 1. Магазины
    if any(k in name_lower for k in ['shop', 'магазин', 'покупк', 'ювелир',
                                       'home shopping', 'top shop', 'leomax', 'shopping live']):
        return 'Магазины'

    # 2. Детские
    kids_keywords = ['детск', 'мульт', 'disney', 'nickelodeon', 'nick jr', 'nicktoons',
                     'kids', 'baby', 'cartoon', 'радость моя', 'tiji', 'gulli', 'mult',
                     'никилодеон', 'сказки', 'карусель', 'carousel', 'kapitan fantastika',
                     'малыш', 'boomerang', 'unikum', 'detvora', 'tooku', 'anime', 'aqlvoy',
                     'тамыр', 'tamyr', 'ryzhiy']
    if any(k in name_lower for k in kids_keywords) or \
       any(g in group_lower for g in ['kids', 'детск', 'animation', 'cartoon']):
        return 'Детские'

    # 3. Спорт
    sports_keywords = ['спорт', 'матч!', 'футбол', 'хоккей', 'бой', 'бокс', 'ufc',
                       'formula', 'sport', 'fight', 'racing', 'nfl', 'nba', 'кхл',
                       'рпл', 'arena', 'extreme', 'шахмат', 'бильярд', 'setanta',
                       'eurosport', 'viju+ sport', 'khl', 'mma']
    if any(k in name_lower for k in sports_keywords) or \
       any(g in group_lower for g in ['sport', 'спорт']):
        return 'Спорт'

    # 4. Музыка
    music_keywords = ['музык', 'mtv', 'ru.tv', 'bridge', 'music', 'vh1', 'mcm', 'muz',
                      'europa plus', 'рекорд', 'chanson', 'energy', 'жара', 'ля-минор',
                      'mezzo', 'trace', 'classic music', '1hd', 'first music', 'muzzone',
                      'songtv', 'strana fm', 'радио']
    if any(k in name_lower for k in music_keywords) or \
       any(g in group_lower for g in ['music', 'музык']):
        return 'Музыка'

    # 5. Кино и Сериалы
    movie_keywords = ['кино', 'фильм', 'сериал', 'movie', 'film', 'series', 'cinema',
                      'премиум', 'paramount', 'hbo', 'медиатека', 'кинопремьера',
                      'fox', 'tv1000', 'amedia', 'мост', 'картин', 'русский роман',
                      'эгоист', 'строго', 'наше кино', 'советское кино', 'blokbaster',
                      'premialnoe', 'viju', 'start', 'star cinema', 'star family',
                      'illusion', 'kinosvidanie', 'kinopokaz', 'kinohit', 'kinomix',
                      'kinosemja', 'kinouzhas', 'kinopremyera', 'kinoseriya', 'kino tv',
                      'tv 21', 'kino 1', 'kino 2', 'dom kino', 'saphire', 'premier',
                      'serial', 'hit hd', 'hit (', 'hit ']
    if any(k in name_lower for k in movie_keywords) or \
       any(g in group_lower for g in ['movies', 'series', 'кино', 'фильм', 'cinema']):
        return 'Кино и Сериалы'

    # 6. Новости
    news_keywords = ['новост', 'вести', 'известия', 'соловьев', 'news', 'рбк', 'cnn',
                     'bbc', 'euronews', 'мир 24', 'коммерсант', 'rbc', 'current time',
                     'dw ', 'настоящее время', 't24', 'eurasia', '360° news', 'izvestia',
                     'russia 24', 'россия 24', 'крик', 'толк', 'ост вест']
    if any(k in name_lower for k in news_keywords) or \
       any(g in group_lower for g in ['news', 'новост']):
        return 'Новости'

    # 7. Познавательные
    doc_keywords = ['познавательн', 'история', 'наук', 'discovery', 'national geographic',
                    'nat geo', 'animal planet', 'science', 'travel', 'documentary', 'docu',
                    'viasat explore', 'viju explore', 'viju history', 'viju nature',
                    'nature', 'outdoor', 'охота', 'рыбалка', 'живая природа', 'живой',
                    '365 дней', 'da vinci', 'rtg', 'terra', 'еда', 'food', '365 days',
                    'дикая', 'dikaja', 'моя планета', 'moya planeta', 'наука 2.0',
                    'nauka', 'top secret', 'совершенно секретно', 'english class',
                    '365 day', 'зоопарк', 'zoopark', 'в мире животных']
    if any(k in name_lower for k in doc_keywords) or \
       any(g in group_lower for g in ['documentary', 'science', 'travel', 'education',
                                       'outdoor', 'history', 'познават']):
        return 'Познавательные'

    # 8. Религиозные
    religious_keywords = ['религ', 'спас', 'religious', 'god', 'bible', 'союз', 'троица',
                          'ортодокс', 'мусульман', 'hope channel', '3abn', 'angel tv',
                          'tv mana', 'manasat', 'vera 24', 'вера', 'huzur', 'спас']
    if any(k in name_lower for k in religious_keywords) or \
       any(g in group_lower for g in ['religious', 'религ']):
        return 'Религиозные'

    # 9. Региональные
    regional_keywords = ['гтрк', 'регион', 'область', 'край', 'москва 24',
                         'санкт-петербург', 'спб', 'сибир', 'урал', 'кубан', 'дон',
                         'ника тв', 'телеканал санкт', 'подмосковье', 'нижний новгород',
                         'казань', 'татарстан', 'башкорт', 'дагестан', 'ингушетия',
                         'осетия', 'чечня', 'ярославл', 'самара', 'саратов', 'краснодар',
                         'красноярск', 'хабаровск', 'владивосток', 'архангельск',
                         'мурманск', 'тюмен', 'омск', 'томск', 'кемеров', 'новосибирск',
                         'пермь', 'екатеринбург', 'чебоксар', 'ставропол', 'астрахан',
                         'белгород', 'воронеж', 'липец', 'тула', 'калуг', 'рязан',
                         'тверь', 'псков', 'новгород', 'вологд', 'ижевск', 'киров',
                         'оренбург', 'уфа', 'саха', 'якут', 'бурят', 'тыва', 'алтай']
    if any(k in name_lower for k in regional_keywords) or \
       any(g in group_lower for g in ['local', 'regional', 'регион']):
        return 'Региональные'

    # 10. Федеральные (ИСПРАВЛЕНО: ищем вхождение, а не точное совпадение)
    federal_keywords = ['первый', 'россия 1', 'россия-1', 'нтв', 'стс', 'тнт', 
                        'рен тв', 'рентв', 'тв-3', 'тв3', 'пятница', 'звезда', 'спас', 
                        'тв центр', 'твц', 'отр', 'муз тв', 'муз-тв', 'матч тв', 'карусель',
                        'че', 'ю', 'суббота', 'солнце']
    
    # Защита: "Мир" только если это отдельное слово или точное название канала
    if 'мир' in name_lower and not any(x in name_lower for x in ['животных', 'природ', 'кино']):
        if 'мир' in _base_name(name_lower).split() or name_lower == 'мир':
            return 'Федеральные'

    if any(k in name_lower for k in federal_keywords):
        return 'Федеральные'

    # 11. Развлекательные
    fun_keywords = ['развлекательн', 'comedy', 'lifestyle', 'fashion', 'relax',
                    'entertainment', 'cooking', 'family', 'юмор', 'пельмени',
                    'наша russia', 'che!', 'сарафан', 'subbota', 'суббота',
                    'пятница', 'friday', 'ctc', 'стс', 'ю-тв', '2x2', 'мультиландия']
    if any(k in name_lower for k in fun_keywords) or \
       any(g in group_lower for g in ['entertainment', 'lifestyle', 'cooking',
                                       'family', 'general', 'развлек']):
        return 'Развлекательные'

    return 'Общие'


def load_iptv_org_epg_map():
    epg_map = {}
    url = "https://iptv-org.github.io/api/channels.json"
    log("[*] Загрузка базы tvg-id (iptv-org)...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
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
        log(f"[+] База tvg-id загружена. Записей: {len(epg_map)}")
    except Exception as e:
        log(f"[!] Ошибка загрузки базы tvg-id: {e}")
    return epg_map


def parse_m3u_from_url(url, source_index, global_logos_by_norm_name, epg_map):
    log(f"[*] Скачивание источника #{source_index + 1}: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    channels = []
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        log(f"[!] Ошибка при скачивании источника {url}: {e}")
        return channels

    current_group = "Общие"
    current_name = ""
    current_logo = ""
    current_tvg_id = ""

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("#EXTINF:"):
            group_match = re.search(r'group-title="([^"]+)"', line)
            current_group = group_match.group(1) if group_match else "Общие"

            logo_match = re.search(r'tvg-logo="([^"]*)"', line)
            current_logo = logo_match.group(1) if logo_match else ""

            tvg_match = re.search(r'tvg-id="([^"]*)"', line)
            current_tvg_id = tvg_match.group(1) if tvg_match else ""

            current_name = extract_display_name(line)
        elif line and not line.startswith("#"):
            if current_name:
                if not is_valid_url(line):
                    current_name, current_logo, current_tvg_id = "", "", ""
                    continue

                norm_name = normalize_name(current_name)
                logo = current_logo

                if source_index == 2 and not logo and norm_name in global_logos_by_norm_name:
                    logo = global_logos_by_norm_name[norm_name]

                if logo and norm_name and norm_name not in global_logos_by_norm_name:
                    global_logos_by_norm_name[norm_name] = logo

                tvg_id = current_tvg_id
                if not tvg_id:
                    tvg_id = epg_map.get(norm_name, "")

                custom_ua = "HlsWinkPlayer" if re.search(r'\+\s*\d+', current_name) else None
                final_group = smart_categorize(current_name, current_group)

                channels.append({
                    "name": current_name,
                    "group": final_group,
                    "logo": logo,
                    "tvg_id": tvg_id,
                    "url": line,
                    "user_agent": custom_ua,
                    "norm_name": norm_name,
                })
                current_name, current_logo, current_tvg_id = "", "", ""

    log(f"[+] Источник #{source_index + 1} обработан. Найдено: {len(channels)}")
    return channels


def deduplicate_channels(channels):
    by_url = {}
    for ch in channels:
        if ch["url"] not in by_url:
            by_url[ch["url"]] = ch
            continue
        existing = by_url[ch["url"]]
        if not existing.get("logo") and ch.get("logo"):
            existing["logo"] = ch["logo"]
        if not existing.get("tvg_id") and ch.get("tvg_id"):
            existing["tvg_id"] = ch["tvg_id"]

    by_key = {}
    for ch in by_url.values():
        key = (ch["norm_name"], ch["group"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = ch
            continue
        existing_score = (bool(existing.get("logo")), -existing.get("fail_count", 0))
        new_score = (bool(ch.get("logo")), -ch.get("fail_count", 0))
        if new_score > existing_score:
            by_key[key] = ch

    return list(by_key.values())


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
            log(f"[*] Загружен старый кэш. Каналов: {len(old_data_map)}")
        except Exception as e:
            log(f"[!] Не удалось прочитать старый channels.json: {e}")

    epg_map = load_iptv_org_epg_map()

    sources = [
        "https://iptv-org.github.io/iptv/countries/ru.m3u",
        "https://iptv-org.github.io/iptv/languages/rus.m3u",
        "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    ]

    all_channels = []
    global_logos_by_norm_name = {}

    for idx, src in enumerate(sources):
        parsed = parse_m3u_from_url(src, idx, global_logos_by_norm_name, epg_map)
        all_channels.extend(parsed)

    if not all_channels:
        raise SystemExit("[!] Все источники пусты/недоступны — прерываемся")

    unique_channels = deduplicate_channels(all_channels)

    # Переносим историю/fail_count/latency из старого кэша
    for ch in unique_channels:
        old = old_data_map.get(ch["url"], {})
        ch["fail_count"] = old.get("fail_count", 0)
        ch["latency"] = old.get("latency", 999.0)
        ch["history"] = old.get("history", [])

    log(f"[*] Уникальных каналов после дедупликации: {len(unique_channels)}")

    with open("channels.json", "w", encoding="utf-8") as f:
        json.dump(unique_channels, f, ensure_ascii=False, indent=2)

    log("[+] Парсинг успешно завершён, данные сохранены в channels.json")


if __name__ == "__main__":
    main()
