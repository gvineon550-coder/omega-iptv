import json
import urllib.request
import gzip
import xml.etree.ElementTree as ET
import sys
import io
import re

def log(msg):
    print(msg)
    sys.stdout.flush()

def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r'\b(hd|sd|4k|fhd|hq|1080p|720p|576i|1080|720)\b', '', name)
    name = re.sub(r'[^а-яa-z0-9]', '', name)
    return name

def main():
    log("[*] Запуск умной фильтрации EPG...")
    
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels = json.load(f)
    except FileNotFoundError:
        log("[!] channels.json не найден")
        return

    name_to_tvgid = {}
    valid_tvgids = set()
    for c in channels:
        tvg_id = c.get("tvg_id")
        norm_name = c.get("norm_name")
        if tvg_id:
            valid_tvgids.add(tvg_id)
            if norm_name:
                name_to_tvgid[norm_name] = tvg_id

    if not valid_tvgids:
        log("[!] Нет tvg-id для фильтрации")
        return

    log(f"[*] В базе {len(valid_tvgids)} каналов. Скачиваем полный EPG (RU)...")

    url = "http://epgshare01.online/epgshare01/epg_ripper_RU1.xml.gz"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            gz_data = response.read()
    except Exception as e:
        log(f"[!] Ошибка скачивания EPG: {e}")
        return

    log("[*] Умное сопоставление ID и фильтрация...")
    
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(gz_data)) as f:
            tree = ET.parse(f)
            root = tree.getroot()
    except Exception as e:
        log(f"[!] Ошибка парсинга XML: {e}")
        return

    new_root = ET.Element("tv")
    id_mapping = {}
    
    for channel in root.findall("channel"):
        old_id = channel.get("id")
        if not old_id:
            continue
            
        matched_new_id = None
        
        if old_id in valid_tvgids:
            matched_new_id = old_id
        else:
            display_names = [dn.text for dn in channel.findall("display-name") if dn.text]
            for dn in display_names:
                norm_dn = normalize_name(dn)
                if norm_dn in name_to_tvgid:
                    matched_new_id = name_to_tvgid[norm_dn]
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

    log(f"[*] Сопоставлено каналов: {len(id_mapping)}. Найдено передач: {programme_count}")

    log("[*] Сохранение epg_lite.xml.gz...")
    xml_bytes = ET.tostring(new_root, encoding="utf-8")
    
    with gzip.open("epg_lite.xml.gz", "wb") as f:
        f.write(xml_bytes)

    log("[+] EPG успешно отфильтрован, ID подменены на нужные!")

if __name__ == "__main__":
    main()
