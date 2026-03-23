#!/usr/bin/env python3
import requests
import json
import time
import uuid
from base64 import urlsafe_b64decode
from collections import defaultdict


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
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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

    def build_stream_url(self, channel_id, ip_address=""):
        token = self.boot(ip_address).get("sessionToken", "")
        return f"{self.STITCHER_BASE}/v2/stitch/hls/channel/{channel_id}/master.m3u8?jwt={token}&masterJWTPassthrough=true"

    def build_vod_stream_url(self, vod_url, ip_address=""):
        token = self.boot(ip_address).get("sessionToken", "")
        # Semplice: se l'URL è già un URL stitched, lo usiamo così.
        # Per sicurezza, possiamo fare come nel plugin.
        return f"{vod_url}?jwt={token}&masterJWTPassthrough=true"


pluto_auth = PlutoAuth()


def fetch_channels(ip_address=""):
    headers = {
        "authorization": f"Bearer {pluto_auth.boot(ip_address).get('sessionToken', '')}",
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "origin": "https://pluto.tv",
        "referer": "https://pluto.tv/",
    }
    if ip_address:
        headers["X-Forwarded-For"] = ip_address

    url = "https://api.pluto.tv/v2/channels"
    params = {
        "deviceType": "web",
        "deviceMake": "chrome",
        "deviceModel": "web",
        "deviceVersion": "122.0.0",
        "appName": "web",
        "appVersion": "8.0.0",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_vod_categories(ip_address=""):
    headers = {
        "authorization": f"Bearer {pluto_auth.boot(ip_address).get('sessionToken', '')}",
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "origin": "https://pluto.tv",
        "referer": "https://pluto.tv/",
    }
    if ip_address:
        headers["X-Forwarded-For"] = ip_address

    url = "https://api.pluto.tv/v3/vod/categories"
    params = {
        "includeItems": "true",
        "deviceType": "web",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def generate_m3u(channels, vod_categories=None, output_file="pluto.m3u"):
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        
        # Sezione Live TV
        f.write("\n#EXTINF:-1 group-title=\"Live TV\",--- Live TV ---\n")  # separatore
        # Raggruppa canali per categoria
        groups = defaultdict(list)
        for ch in channels:
            channel_id = ch.get("_id") or ch.get("id")
            if not channel_id:
                continue
            name = ch.get("name", "Unknown")
            logo = ch.get("logo", {}).get("path", "") or ch.get("image", "")
            category = ch.get("category", "Uncategorized")
            stream_url = pluto_auth.build_stream_url(channel_id, ip_address="")
            groups[category].append((name, stream_url, logo, channel_id))
        
        # Ordina le categorie alfabeticamente
        for category in sorted(groups.keys()):
            f.write(f'\n#EXTINF:-1 group-title="{category}",--- {category} ---\n')
            # Ordina i canali per nome
            for name, stream_url, logo, channel_id in sorted(groups[category], key=lambda x: x[0]):
                f.write(f'#EXTINF:-1 tvg-id="{channel_id}" tvg-name="{name}" tvg-logo="{logo}" group-title="{category}",{name}\n')
                f.write(f"{stream_url}\n")
        
        # Sezione VOD (se richiesto)
        if vod_categories and vod_categories.get("totalCategories", 0) > 0:
            f.write("\n#EXTINF:-1 group-title=\"VOD\",--- VOD ---\n")
            for category in vod_categories.get("categories", []):
                cat_name = category.get("name", "Uncategorized")
                items = category.get("items", [])
                if not items:
                    continue
                f.write(f'\n#EXTINF:-1 group-title="VOD - {cat_name}",--- {cat_name} ---\n')
                for item in items:
                    name = item.get("name", "Unknown")
                    # Prendi l'URL dello stream (stitched)
                    urls = item.get("stitched", {}).get("urls", [])
                    if not urls:
                        continue
                    stream_url = urls[0].get("url", "")
                    if not stream_url:
                        continue
                    # Aggiungi il token JWT (opzionale, potrebbe già esserci)
                    stream_url = pluto_auth.build_vod_stream_url(stream_url, ip_address="")
                    logo = ""
                    covers = item.get("covers", [])
                    if covers:
                        logo = covers[0].get("url", "")
                    f.write(f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="VOD - {cat_name}",{name}\n')
                    f.write(f"{stream_url}\n")


if __name__ == "__main__":
    print("Fetching channels...")
    channels = fetch_channels()
    print(f"Found {len(channels)} channels.")
    
    # Opzionale: fetch VOD (attenzione: potrebbe essere pesante)
    include_vod = True  # metti False se vuoi solo live
    vod_categories = None
    if include_vod:
        print("Fetching VOD categories...")
        vod_categories = fetch_vod_categories()
        total = vod_categories.get("totalCategories", 0)
        print(f"Found {total} VOD categories.")
    
    generate_m3u(channels, vod_categories, "pluto.m3u")
    print("File pluto.m3u generated.")
