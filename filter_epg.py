import json
import urllib.request
import gzip
import xml.etree.ElementTree as ET
import sys
import io
import re
import difflib

def log(msg):
    print(msg)
    sys.stdout.flush()

def clean_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'\b(hd|sd|4k|fhd|hq|1080p|720p|1080i|576i|576p|480p|480i|russia|ukraine|belarus|international|europe|asia|cis)\b', '', name)
    name = re.sub(r'[^а-яa-z0-9]', '', name)
    return name

def main():
    log("[*] Запуск фильтрации EPG (исправленная версия)...")
    
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels = json.load(f)
    except FileNotFoundError:
        log("[!] channels.json не найден")
        return

    # Строим карту: базовый ID (без @SD) -> полный ID (с @SD)
    base_to_actual = {}
    name_to_tvgid = {} # Нормализованное имя -> полный ID
    
    for c in channels:
        tvg_id = c.get("tvg_id")
        if tvg_id:
            base_id = tvg_id.split('@')[0]
            base_to_actual[base_id] = tvg_id
            
            norm = c.get("norm_name")
            if norm:
                name_to_tvgid[clean_name(norm)] = tvg_id

    valid_tvgids = set(base_to_actual.values())
    if not valid_tvgids:
        log("[!] Нет tvg-id для фильтрации")
        return

    log(f"[*] В базе {len(valid_tvgids)} каналов. Загружаем альтернативные имена...")

    try:
        api_url = "https://iptv-org.github.io/api/channels.json"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            api_data = json.loads(response.read().decode('utf-8'))
            
            added = 0
            for item in api_data:
                ch_id = item.get("id")
                if not ch_id or ch_id not in base_to_actual:
                    continue
                
                actual_id = base_to_actual[ch_id]
                names = [item.get("name")] + item.get("alt_names", [])
                for n in names:
                    if n:
                        norm = clean_name(n)
                        if norm and norm not in name_to_tvgid:
                            name_to_tvgid[norm] = actual_id
                            added += 1
        log(f"[+] Загружено {added} новых альтернативных имен из API.")
    except Exception as e:
        log(f"[!] Ошибка загрузки API: {e}")

    log(f"[*] Всего имен для поиска: {len(name_to_tvgid)}")
    log("[*] Скачиваем EPG от teleguide.info...")
    
    url = "https://www.teleguide.info/download/new3/xmltv.xml.gz"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as response:
            gz_data = response.read()
    except Exception as e:
        log(f"[!] Ошибка скачивания EPG: {e}")
        return

    log("[*] Анализ XML и поиск совпадений...")
    
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(gz_data)) as f:
            tree = ET.parse(f)
            root = tree.getroot()
    except Exception as e:
        log(f"[!] Ошибка парсинга XML: {e}")
        return

    new_root = ET.Element("tv")
    id_mapping = {}
    exact_matches = 0
    fuzzy_matches = 0
    unmatched_epg_names = []
    
    all_norm_names = list(name_to_tvgid.keys())

    for channel in root.findall("channel"):
        old_id = channel.get("id")
        if not old_id:
            continue
            
        matched_new_id = None
        
        # 1. Прямое совпадение ID (редкость)
        if old_id in valid_tvgids:
            matched_new_id = old_id
            exact_matches += 1
        else:
            display_names = [dn.text for dn in channel.findall("display-name") if dn.text]
            matched_name = None
            
            for dn in display_names:
                norm_dn = clean_name(dn)
                
                # 2. Точное совпадение имени
                if norm_dn in name_to_tvgid:
                    matched_new_id = name_to_tvgid[norm_dn]
                    exact_matches += 1
                    matched_name = dn
                    break
                
                # 3. Нечеткое совпадение
                if not matched_new_id and len(norm_dn) > 3:
                    matches = difflib.get_close_matches(norm_dn, all_norm_names, n=1, cutoff=0.85)
                    if matches:
                        matched_new_id = name_to_tvgid[matches[0]]
                        fuzzy_matches += 1
                        matched_name = dn
                        break
            
            if not matched_new_id and display_names:
                unmatched_epg_names.append(display_names[0])
        
        if matched_new_id:
            id_mapping[old_id] = matched_new_id
            channel.set("id", matched_new_id)
            new_root.append(channel)

    programme_count = 0
    for programme in root.findall("programme"):
        old_channel_id = programme.get("channel")
        if old_channel_id in id_mapping:
            new_channel_id = id_mapping[old_channel_id]
            programme.set("channel", new_channel_id)
            new_root.append(programme)
            programme_count += 1

    log(f"[*] Точных совпадений: {exact_matches}")
    log(f"[*] Нечетких совпадений: {fuzzy_matches}")
    log(f"[*] ВСЕГО Сопоставлено каналов: {len(id_mapping)}")
    log(f"[*] Найдено передач: {programme_count}")

    log("[*] Сохранение epg_lite.xml.gz...")
    xml_bytes = ET.tostring(new_root, encoding="utf-8")
    
    with gzip.open("epg_lite.xml.gz", "wb") as f:
        f.write(xml_bytes)

    log("[+] EPG успешно отфильтрован!")

if __name__ == "__main__":
    main()
