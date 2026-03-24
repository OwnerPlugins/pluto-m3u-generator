#!/usr/bin/env python3
import os
import sys
import json
import time
import uuid
import re
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

GENERATE_ALL_REGIONS = True
GENERATE_VOD = True
VOD_MAX_ITEMS = 500
LIVE_GROUP_BY_CATEGORY = True


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

    def build_stream_url(self, channel_id, ip_address=""):
        token = self.boot(ip_address).get("sessionToken", "")
        return f"{self.STITCHER_BASE}/v2/stitch/hls/channel/{channel_id}/master.m3u8?jwt={token}&masterJWTPassthrough=true"

    def build_vod_stream_url(self, vod_url, ip_address=""):
        token = self.boot(ip_address).get("sessionToken", "")
        path = vod_url.split("?")[0]
        path = re.sub(r"^https?://[^/]+", "", path)
        if path.startswith("/stitch/"):
            path = "/v2" + path
        return f"{self.STITCHER_BASE}{path}?jwt={token}&masterJWTPassthrough=true"


pluto_auth = PlutoAuth()

# ------------------------------
# Caricamento regioni
# ------------------------------
def fetch_regions():
    try:
        resp = requests.get(REGIONS_XML_URL, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        regions = {}
        for region in root.findall("region"):
            country = region.get("country")
            name = region.get("name")
            ip = region.get("ip")
            tids = region.get("tids")
            if country and ip and tids:
                regions[country] = (name, ip, tids)
        print(f"[Regions] Caricate {len(regions)} regioni.")
        return regions
    except Exception as e:
        print(f"[Regions] Errore: {e}")
        return {}


# ------------------------------
# Recupero dati con regione
# ------------------------------
def fetch_live_channels(ip_address="", region_code=""):
    headers = pluto_auth._api_headers(ip_address)
    headers["Accept-Language"] = "it-IT,it;q=0.9,en;q=0.8"  # preferisci italiano
    url = f"{PLUTO_API_URL}/v2/channels"
    params = {
        "deviceType": "web",
        "deviceMake": "chrome",
        "deviceModel": "web",
        "deviceVersion": "122.0.0",
        "appName": "web",
        "appVersion": "8.0.0"
    }
    if region_code:
        params["region"] = region_code
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        channels = resp.json()
        print(f"[Live] Trovati {len(channels)} canali per {region_code}.")
        return channels
    except Exception as e:
        print(f"[Live] Errore: {e}")
        return []


def fetch_vod_categories(ip_address="", region_code=""):
    headers = pluto_auth._api_headers(ip_address)
    headers["Accept-Language"] = "it-IT,it;q=0.9,en;q=0.8"
    params = {
        "includeItems": "true",
        "deviceType": "web",
    }
    if region_code:
        params["region"] = region_code
    try:
        resp = requests.get(PLUTO_VOD_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"[VOD] Trovate {len(data.get('categories', []))} categorie per {region_code}.")
        return data
    except Exception as e:
        print(f"[VOD] Errore: {e}")
        return {}


# ------------------------------
# Generazione M3U
# ------------------------------
def generate_live_m3u(channels, output_file, ip_address="", group_by_category=True):
    if not channels:
        print(f"[Live] Nessun canale, salto {output_file}")
        return

    if group_by_category:
        by_category = defaultdict(list)
        for ch in channels:
            cat = ch.get("category", "Other")
            by_category[cat].append(ch)
        sorted_cats = sorted(by_category.items())
    else:
        sorted_cats = [("All", channels)]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for cat, ch_list in sorted_cats:
            for ch in sorted(ch_list, key=lambda x: x.get("name", "").lower()):
                name = ch.get("name", "Unknown")
                channel_id = ch.get("_id")
                if not channel_id:
                    continue
                stream_url = pluto_auth.build_stream_url(channel_id, ip_address)
                logo = ch.get("logo", {}).get("path", "") or ch.get("image", "")
                f.write(f'#EXTINF:-1 group-title="{cat}" tvg-id="{channel_id}" tvg-name="{name}" tvg-logo="{logo}",{name}\n')
                f.write(f"{stream_url}\n")
    print(f"[Live] File generato: {output_file}")


def generate_vod_m3u(vod_data, output_file, ip_address="", max_items=0):
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
            movies = [item for item in items if item.get("type") == "movie"]
            if not movies:
                continue
            f.write(f'#EXTGRP:{cat_name}\n')
            for movie in movies:
                name = movie.get("name", "Unknown")
                orig_url = movie.get("stitched", {}).get("urls", [{}])[0].get("url")
                if not orig_url:
                    continue
                stream_url = pluto_auth.build_vod_stream_url(orig_url, ip_address)
                f.write(f'#EXTINF:-1 tvg-name="{name}",{name}\n')
                f.write(f"{stream_url}\n")
                total_written += 1
                if max_items > 0 and total_written >= max_items:
                    print(f"[VOD] Limite di {max_items} voci raggiunto.")
                    return
    print(f"[VOD] File generato: {output_file} ({total_written} voci)")


# ------------------------------
# Main
# ------------------------------
def main():
    regions = fetch_regions()
    if not regions:
        print("Nessuna regione disponibile, esco.")
        sys.exit(1)

    region_codes = list(regions.keys()) if GENERATE_ALL_REGIONS else [c for c in REGIONS_TO_GENERATE if c in regions]
    for code in region_codes:
        name, ip, tids = regions[code]
        print(f"\n--- Regione: {code} ({name}) ---")

        # Live
        channels = fetch_live_channels(ip, region_code=code)
        if channels:
            live_file = f"pluto-live-{code}.m3u"
            generate_live_m3u(channels, live_file, ip_address=ip, group_by_category=LIVE_GROUP_BY_CATEGORY)

        # VOD
        if GENERATE_VOD:
            vod_data = fetch_vod_categories(ip, region_code=code)
            if vod_data:
                vod_file = f"pluto-vod-{code}.m3u"
                generate_vod_m3u(vod_data, vod_file, ip_address=ip, max_items=VOD_MAX_ITEMS)

    print("\nElaborazione completata.")


if __name__ == "__main__":
    main()
