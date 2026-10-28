import json
import urllib.request
import gzip
import xml.etree.ElementTree as ET
import sys
import io
import re
import difflib
import http.client
import time

def log(msg):
    print(msg)
    sys.stdout.flush()

TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu',
    'я': 'ya'
}

def translit(text):
    return "".join(TRANSLIT_MAP.get(c, c) for c in text)

def clean_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'[\+\-]\s*\d+', '', name)
    garbage_words = r'\b(hd|sd|4k|fhd|hq|1080p|720p|1080i|576i|576p|480p|480i|russia|ukraine|belarus|international|europe|asia|cis|tv|channel|телеканал|канал)\b'
    name = re.sub(garbage_words, '', name)
    name = re.sub(r'[^а-яa-z0-9]', '', name)
    return name

def download_gz_data(url):
    """Скачивает файл с 3 попытками и проверяет целостность GZIP"""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    for attempt in range(3):
        log(f"[*] Попытка скачивания EPG #{attempt+1}...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=120) as response:
                data = b""
                while True:
                    chunk = response.read(1024 * 64)
                    if not chunk:
                        break
                    data += chunk
            
            # Проверка целостности (распаковываем первые 10 КБ)
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
                f.read(1024 * 10)
                
            return data
            
        except http.client.IncompleteRead as e:
            log(f"[!] Оборвано соединение. Повтор...")
            time.sleep(3)
        except Exception as e:
            log(f"[!] Ошибка (возможно, битый файл): {e}. Повтор...")
            time.sleep(3)
            
    log("[!] Не удалось скачать валидный EPG после 3 попыток.")
    return None

def main():
    log("[*] Запуск усиленной фильтрации EPG...")
    
    try:
        with open("channels.json", "r", encoding="utf-8") as f:
            channels = json.load(f)
    except FileNotFoundError:
        log("[!] channels.json не найден")
        return

    base_to_actual = {}
    name_to_tvgid = {}
    
    for c in channels:
        tvg_id = c.get("tvg_id")
        if tvg_id:
            base_id = tvg_id.split('@')[0]
            base_to_actual[base_id] = tvg_id
            
            for name_field in [c.get("norm_name"), c.get("name")]:
                if name_field:
                    clean = clean_name(name_field)
                    if clean:
                        name_to_tvgid[clean] = tvg_id
                        name_to_tvgid[translit(clean)] = tvg_id

    valid_tvgids = set(base_to_actual.values())
    if not valid_tvgids:
        log("[!] Нет tvg-id для фильтрации")
        return

    log(f"[*] В базе {len(valid_tvgids)} каналов. Загружаем альтернативные имена из API...")

    try:
        api_url = "https://iptv-org.github.io/api/channels.json"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            api_data = json.loads(response.read().decode('utf-8'))
            for item in api_data:
                ch_id = item.get("id")
                if not ch_id or ch_id not in base_to_actual:
                    continue
                actual_id = base_to_actual[ch_id]
                names = [item.get("name")] + item.get("alt_names", [])
                for n in names:
                    if n:
                        clean = clean_name(n)
                        if clean:
                            name_to_tvgid[clean] = actual_id
                            name_to_tvgid[translit(clean)] = actual_id
    except Exception as e:
        log(f"[!] Ошибка загрузки API: {e}")

    log(f"[*] Всего имен для поиска: {len(name_to_tvgid)}")
    
    url = "https://www.teleguide.info/download/new3/xmltv.xml.gz"
    gz_data = download_gz_data(url)
    
    if not gz_data:
        log("[!] Пропускаем генерацию EPG, так как файл не скачан.")
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
        
        if old_id in valid_tvgids:
            matched_new_id = old_id
            exact_matches += 1
        else:
            display_names = [dn.text for dn in channel.findall("display-name") if dn.text]
            
            for dn in display_names:
                norm_dn = clean_name(dn)
                translit_dn = translit(norm_dn)
                
                if norm_dn in name_to_tvgid:
                    matched_new_id = name_to_tvgid[norm_dn]
                    exact_matches += 1
                    break
                if translit_dn in name_to_tvgid:
                    matched_new_id = name_to_tvgid[translit_dn]
                    exact_matches += 1
                    break
                
                if not matched_new_id and len(norm_dn) > 4:
                    matches = difflib.get_close_matches(norm_dn, all_norm_names, n=1, cutoff=0.70)
                    if matches:
                        matched_new_id = name_to_tvgid[matches[0]]
                        fuzzy_matches += 1
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

    log("==========================================")
    log(f"ТОП-60 НЕСОПОСТАВЛЕННЫХ КАНАЛОВ ИЗ EPG ({len(unmatched_epg_names)} всего):")
    for name in sorted(list(set(unmatched_epg_names)))[:60]:
        log(f"  - {name}")
    log("==========================================")

    log("[*] Сохранение epg_lite.xml.gz...")
    xml_bytes = ET.tostring(new_root, encoding="utf-8")
    
    with gzip.open("epg_lite.xml.gz", "wb") as f:
        f.write(xml_bytes)

    log("[+] EPG успешно отфильтрован!")

if __name__ == "__main__":
    main()
