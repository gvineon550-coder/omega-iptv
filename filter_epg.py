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
    # Убираем скобки и их содержимое
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'\(.*?\)', '', name)
    # Убираем качество и мусорные слова
    name = re.sub(r'\b(hd|sd|4k|fhd|hq|1080p|720p|1080i|576i|576p|480p|480i|russia|ukraine|belarus|international|europe|asia|cis)\b', '', name)
    # Убираем пунктуацию и оставляем только буквы/цифры
    name = re.sub(r'[^а-яa-z0-9]', '', name)
    return name

def main():
    log("[*] Запуск АВТОМАТИЧЕСКОЙ фильтрации с нечетким поиском...")
    
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels = json.load(f)
    except FileNotFoundError:
        log("[!] channels.json не найден")
        return

    valid_tvgids = {c.get("tvg_id") for c in channels if c.get("tvg_id")}
    if not valid_tvgids:
        log("[!] Нет tvg-id для фильтрации")
        return

    log(f"[*] В базе {len(valid_tvgids)} каналов. Загружаем альтернативные имена...")

    name_to_tvgid = {}
    try:
        api_url = "https://iptv-org.github.io/api/channels.json"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            api_data = json.loads(response.read().decode('utf-8'))
            for item in api_data:
                ch_id = item.get("id")
                if not ch_id or ch_id not in valid_tvgids:
                    continue
                names = [item.get("name")] + item.get("alt_names", [])
                for n in names:
                    if n:
                        norm = clean_name(n)
                        if norm and norm not in name_to_tvgid:
                            name_to_tvgid[norm] = ch_id
        log(f"[+] Загружено {len(name_to_tvgid)} имен.")
    except Exception as e:
        log(f"[!] Ошибка загрузки API: {e}")
        for c in channels:
            if c.get("norm_name") and c.get("tvg_id"):
                name_to_tvgid[clean_name(c["norm_name"])] = c["tvg_id"]

    log("[*] Скачиваем EPG от teleguide.info...")
    url = "https://www.teleguide.info/download/new3/xmltv.xml.gz"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as response:
            gz_data = response.read()
    except Exception as e:
        log(f"[!] Ошибка скачивания EPG: {e}")
        return

    log("[*] Анализ XML и поиск совпадений (включая нечеткие)...")
    
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
    
    # Список всех нормализованных имен из API для нечеткого поиска
    all_norm_names = list(name_to_tvgid.keys())

    for channel in root.findall("channel"):
        old_id = channel.get("id")
        if not old_id:
            continue
            
        matched_new_id = None
        
        if old_id in valid_tvgids:
            matched_new_id = old_id
            exact_matches += 1
        else:
            display_names = [dn.text for dn in channel.findall("display-name") if dn.text]
            for dn in display_names:
                norm_dn = clean_name(dn)
                
                # 1. Точное совпадение
                if norm_dn in name_to_tvgid:
                    potential_id = name_to_tvgid[norm_dn]
                    if potential_id in valid_tvgids:
                        matched_new_id = potential_id
                        exact_matches += 1
                        break
                
                # 2. Нечеткое совпадение (если точного нет)
                if not matched_new_id and len(norm_dn) > 3:
                    # Ищем самое похожее имя (порог схожести 0.85)
                    matches = difflib.get_close_matches(norm_dn, all_norm_names, n=1, cutoff=0.85)
                    if matches:
                        potential_id = name_to_tvgid[matches[0]]
                        if potential_id in valid_tvgids:
                            matched_new_id = potential_id
                            fuzzy_matches += 1
                            break
        
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
    log(f"[*] Нечетких совпадений (Fuzzy): {fuzzy_matches}")
    log(f"[*] ВСЕГО Сопоставлено каналов: {len(id_mapping)}")
    log(f"[*] Найдено передач: {programme_count}")

    log("[*] Сохранение epg_lite.xml.gz...")
    xml_bytes = ET.tostring(new_root, encoding="utf-8")
    
    with gzip.open("epg_lite.xml.gz", "wb") as f:
        f.write(xml_bytes)

    log("[+] EPG успешно отфильтрован!")

if __name__ == "__main__":
    main()
