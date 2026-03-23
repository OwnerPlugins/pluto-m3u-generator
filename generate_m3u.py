#!/usr/bin/env python3
import os
import sys
import json
import time
import uuid
import requests
import xml.etree.ElementTree as ET
from collections import defaultdict
from base64 import urlsafe_b64decode
from urllib.parse import urljoin

# ------------------------------
# Costanti e configurazione
# ------------------------------
PLUTO_API_URL = "https://api.pluto.tv"
PLUTO_VOD_URL = f"{PLUTO_API_URL}/v3/vod/categories"
PLUTO_SEASON_URL = f"{PLUTO_API_URL}/v3/vod/series/%s/seasons"
REGIONS_XML_URL = "https://raw.githubusercontent.com/oe-alliance/PlutoTV/refs/heads/main/src/PlutoTV/plutotv.xml"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Se vuoi generare solo alcune regioni, modifica questa lista (usa i codici paese)
# Se vuoi generare per tutte le regioni trovate nel XML, imposta GENERATE_ALL_REGIONS = True
GENERATE_ALL_REGIONS = True
REGIONS_TO_GENERATE = ["US", "IT", "GB", "DE", "FR", "ES"]  # usato solo se GENERATE_ALL_REGIONS = False
GENERATE_VOD = True          # genera anche file VOD (film)
VOD_MAX_ITEMS = 500          # limite per evitare file troppo grandi (0 = nessun limite)
LIVE_GROUP_BY_CATEGORY = True # raggruppa i canali live per categoria nel file M3U

# ------------------------------
# Classe PlutoAuth (dal plugin originale)
# ------------------------------
class PlutoAuth:
    BOOT_URL = "https://boot.pluto.tv/v4/start"
    STITCHER_BASE = "https://cfd-v4-service-channel-stitcher-use1-1.prd.pluto.tv"

    def __init__(self):
        self.session = requests.Session()
        self.client_id = str(uuid.uuid4())
        self.cache = {}

    @staticmethod
    def _token_expiry(token):
        try:
            payload = token.split(".")[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            return json.loads(urlsafe_b64decode(payload).decode())["exp"]
        except Exception:
            return 0

    def boot(self, ip_address=""):
        cache_key = ip_address or "default"
        cached = self.cache.get(cache_key)
        if cached and time.time() < cached["exp"] - 60:
            return cached["response"]
        headers = {
            "authority": "boot.pluto.tv",
            "accept": "*/*",
            "origin": "https://pluto.tv",
            "referer": "https://pluto.tv/",
            "user-agent": USER_AGENT,
        }
        params = {
            "appName": "web",
            "appVersion": "8.0.0-111b2b9dc00bd0bea9030b30662159ed9e7c8bc6",
            "deviceVersion": "122.0.0",
            "deviceModel": "web",
            "deviceMake": "chrome",
            "deviceType": "web",
            "clientID": self.client_id,
            "clientModelNumber": "1.0.0",
            "serverSideAds": "false",
            "drmCapabilities": "widevine:L3",
            "blockingMode": "",
        }
        if ip_address:
            headers["X-Forwarded-For"] = ip_address
        try:
            resp = self.session.get(self.BOOT_URL, headers=headers, params=params, timeout=10).json()
            token = resp.get("sessionToken", "")
            exp = self._token_expiry(token)
            self.cache[cache_key] = {"response": resp, "exp": exp}
            print(f"[PlutoAuth] New token for {cache_key}, expires {exp}")
            return resp
        except Exception as e:
            print(f"[PlutoAuth] boot error: {e}")
            return {}

    def _api_headers(self, ip_address=""):
        token = self.boot(ip_address).get("sessionToken", "")
        return {
            "authorization": f"Bearer {token}",
            "accept": "application/json",
            "origin": "https://pluto.tv",
            "referer": "https://pluto.tv/",
            "user-agent": USER_AGENT,
        }

# Istanza globale
pluto_auth = PlutoAuth()

# ------------------------------
# Caricamento regioni dal file XML
# ------------------------------
def fetch_regions():
    """Scarica il file XML delle regioni e restituisce un dict: {country_code: (name, ip, tids)}"""
    try:
        resp = requests.get(REGIONS_XML_URL, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        regions = {}
        for region in root.findall("region"):
            country = region.get("country")
            name = region.get("name") or country  # in realtà il nome è nel tag <name>? Nel XML originale c'è attributo "country"
            ip = region.get("ip")
            tids = region.get("tids")
            if country and ip and tids:
                regions[country] = (name, ip, tids)
        print(f"[Regions] Caricate {len(regions)} regioni dal file XML.")
        return regions
    except Exception as e:
        print(f"[Regions] Errore nel caricamento del file XML: {e}")
        # Fallback con alcune regioni note
        return {
            "US": ("United States", "8.8.8.8", "0"),
            "IT": ("Italy", "80.241.215.160", "0"),
            "GB": ("United Kingdom", "80.241.215.160", "0"),
            "DE": ("Germany", "80.241.215.160", "0"),
            "FR": ("France", "80.241.215.160", "0"),
            "ES": ("Spain", "80.241.215.160", "0"),
        }

# ------------------------------
# Funzioni per recuperare i dati
# ------------------------------
def fetch_live_channels(ip_address=""):
    """Recupera la lista dei canali live per la regione specificata"""
    headers = pluto_auth._api_headers(ip_address)
    # Usa l'endpoint v2/channels
    url = f"{PLUTO_API_URL}/v2/channels"
    params = {
        "deviceType": "web",
        "deviceMake": "chrome",
        "deviceModel": "web",
        "deviceVersion": "122.0.0",
        "appName": "web",
        "appVersion": "8.0.0",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        channels = resp.json()
        print(f"[Live] Trovati {len(channels)} canali.")
        return channels
    except Exception as e:
        print(f"[Live] Errore: {e}")
        return []

def fetch_vod_categories(ip_address=""):
    """Recupera le categorie VOD con i relativi film/serie"""
    headers = pluto_auth._api_headers(ip_address)
    params = {"includeItems": "true", "deviceType": "web"}
    try:
        resp = requests.get(PLUTO_VOD_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"[VOD] Trovate {len(data.get('categories', []))} categorie.")
        return data
    except Exception as e:
        print(f"[VOD] Errore: {e}")
        return {}

# ------------------------------
# Generazione file M3U
# ------------------------------
def generate_live_m3u(channels, output_file, group_by_category=True):
    """
    Genera un file M3U con i canali live.
    Se group_by_category è True, usa #EXTGRP per raggruppare per categoria.
    """
    if not channels:
        print(f"[Live] Nessun canale, salto {output_file}")
        return

    # Ordina i canali: prima per categoria, poi per nome
    if group_by_category:
        by_category = defaultdict(list)
        for ch in channels:
            cat = ch.get("category", "Other")
            by_category[cat].append(ch)
        # Ordina le categorie e i canali all'interno
        sorted_cats = sorted(by_category.items())
    else:
        sorted_cats = [("All", channels)]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for cat, ch_list in sorted_cats:
            if group_by_category:
                f.write(f'#EXTGRP:{cat}\n')
            # Ordina i canali per nome
            for ch in sorted(ch_list, key=lambda x: x.get("name", "").lower()):
                name = ch.get("name", "Unknown")
                channel_id = ch.get("_id")
                if not channel_id:
                    continue
                # Estrai l'URL dallo stitched
                stitched = ch.get("stitched", {})
                urls = stitched.get("urls", [])
                if not urls:
                    continue
                stream_url = urls[0].get("url")
                if not stream_url:
                    continue
                logo = ch.get("logo", {}).get("path", "") or ch.get("image", "")
                f.write(f'#EXTINF:-1 tvg-id="{channel_id}" tvg-name="{name}" tvg-logo="{logo}",{name}\n')
                f.write(f"{stream_url}\n")
    print(f"[Live] File M3U generato: {output_file}")

def generate_vod_m3u(vod_data, output_file, max_items=0):
    """
    Genera un file M3U con i contenuti VOD (solo film, per ora).
    I film vengono raggruppati per categoria.
    Se max_items > 0, limita il numero totale di voci.
    """
    categories = vod_data.get("categories", [])
    if not categories:
        print(f"[VOD] Nessuna categoria, salto {output_file}")
        return

    total_written = 0
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for cat in categories:
            cat_name = cat.get("name", "Unknown")
            items = cat.get("items", [])
            # Filtra solo i film (type == "movie")
            movies = [item for item in items if item.get("type") == "movie"]
            if not movies:
                continue
            f.write(f'#EXTGRP:{cat_name}\n')
            for movie in movies:
                name = movie.get("name", "Unknown")
                # Prendi l'URL dello stream
                stitched = movie.get("stitched", {})
                urls = stitched.get("urls", [])
                if not urls:
                    continue
                stream_url = urls[0].get("url")
                if not stream_url:
                    continue
                f.write(f'#EXTINF:-1 tvg-name="{name}",{name}\n')
                f.write(f"{stream_url}\n")
                total_written += 1
                if max_items > 0 and total_written >= max_items:
                    print(f"[VOD] Limite di {max_items} voci raggiunto, interrompo.")
                    return
    print(f"[VOD] File M3U generato: {output_file} ({total_written} voci)")

# ------------------------------
# Funzione principale
# ------------------------------
def main():
    # 1. Ottieni le regioni
    regions = fetch_regions()
    if not regions:
        print("Nessuna regione disponibile, esco.")
        sys.exit(1)

    # Seleziona le regioni da processare
    if GENERATE_ALL_REGIONS:
        region_codes = list(regions.keys())
    else:
        region_codes = [code for code in REGIONS_TO_GENERATE if code in regions]

    if not region_codes:
        print("Nessuna regione selezionata, esco.")
        sys.exit(1)

    print(f"Processerò le seguenti regioni: {region_codes}")

    # 2. Per ogni regione, genera i file
    for code in region_codes:
        name, ip, tids = regions[code]
        print(f"\n--- Regione: {code} ({name}) ---")

        # Live
        channels = fetch_live_channels(ip)
        if channels:
            live_file = f"pluto-live-{code}.m3u"
            generate_live_m3u(channels, live_file, group_by_category=LIVE_GROUP_BY_CATEGORY)

        # VOD (opzionale)
        if GENERATE_VOD:
            vod_data = fetch_vod_categories(ip)
            if vod_data:
                vod_file = f"pluto-vod-{code}.m3u"
                generate_vod_m3u(vod_data, vod_file, max_items=VOD_MAX_ITEMS)

    print("\nElaborazione completata.")

if __name__ == "__main__":
    main()