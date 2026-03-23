#!/usr/bin/env python3
import requests
import json
import sys
import time
import uuid
from base64 import urlsafe_b64decode
from urllib.parse import urljoin


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


pluto_auth = PlutoAuth() 


def fetch_channels(region="US", ip_address=""):
    # Usa l'IP se fornito (per regioni diverse)
    pluto_auth = PlutoAuth()
    # Ottieni il token e costruisci headers
    headers = {
        "authorization": f"Bearer {pluto_auth.boot(ip_address).get('sessionToken', '')}",
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "origin": "https://pluto.tv",
        "referer": "https://pluto.tv/",
    }
    # Aggiungi X-Forwarded-For se necessario per forzare una regione
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


def generate_m3u(channels, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for ch in channels:
            # Salta canali promozionali se desideri (opzionale)
            # if ch.get("isPromoted"):
            #     continue
            name = ch.get("name", "Unknown")
            channel_id = ch.get("id")
            # Prendi il logo (se presente)
            logo = ch.get("logo", {}).get("path", "") or ch.get("image", "")
            # Costruisci l'URL dello stream
            stream_url = plutoAuth.build_stream_url(channel_id, ip_address="")  # Puoi passare IP regionale

            # Scrive la riga EXTINF con i meta dati
            f.write(f'#EXTINF:-1 tvg-id="{channel_id}" tvg-name="{name}" tvg-logo="{logo}",{name}\n')
            f.write(f"{stream_url}\n")


if __name__ == "__main__":
    # Puoi scegliere una regione; qui usa US senza IP forzato
    channels = fetch_channels()
    print(f"Trovati {len(channels)} canali.")
    generate_m3u(channels, "pluto.m3u")
    print("File pluto.m3u generato.")