<h1 align="center">🎬 Pluto TV M3U Generator</h1>

![Visitors](https://komarev.com/ghpvc/?username=Belfagor2005&label=Repository%20Views&color=blueviolet)
[![Version](https://img.shields.io/badge/Version-1.0-blue.svg)]
[![License](https://img.shields.io/badge/License-MIT-green.svg)]
[![Donate](https://img.shields.io/badge/_-Donate-red.svg?logo=githubsponsors&labelColor=555555&style=for-the-badge)](https://ko-fi.com/lululla)


This repository contains an automated workflow that generates M3U playlists for Pluto TV channels and VOD (movies) for **all supported regions**.  
The playlists are updated every 6 hours and pushed to a **public repository** of your choice.

## 🔧 Features

- ✅ Generates M3U files for **live TV channels** and **on‑demand movies**.
- ✅ Localized metadata: channel names, categories, and descriptions in the language of each region (Italian, Spanish, French, German, etc.).
- ✅ Uses the **official Pluto TV API** with proper JWT tokens.
- ✅ Respects regional differences using IP geolocation (X-Forwarded-For headers).
- ✅ **Automatic updates** via GitHub Actions – no manual intervention needed.
- ✅ Files are sorted alphabetically (categories and channels/movies).
- ✅ Audio language can be forced to Italian for Italian streams (optional).

## 📦 What you need

- A **GitHub account**.
- Two repositories:
  1. **Private repository** (this one) – contains the script and the workflow.
  2. **Public repository** (e.g., `pluto-tv-m3u`) – where the generated `.m3u` files will be published.
- A **GitHub personal access token** with `repo` scope.

## 🚀 Setup

### 1. Create the repositories

- Create a **private** repository (e.g., `pluto-m3u-generator`) and clone it locally.
- Create a **public** repository (e.g., `pluto-tv-m3u`) – you can initialize it with a README.

### 2. Add the script

Copy the `generate_m3u.py` script from this repository into the root of your private repository.

### 3. Configure the workflow

The workflow file is located at `.github/workflows/update-m3u.yml`.  
Make sure it contains the following (replace `your-username` and `pluto-tv-m3u` with your actual public repository):

```yaml
name: Aggiorna liste Pluto TV

on:
  schedule:
    - cron: '0 */6 * * *'   # every 6 hours
  workflow_dispatch:          # manual trigger

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout codice
        uses: actions/checkout@v4

      - name: Configura Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Installa dipendenze
        run: pip install requests

      - name: Esegui generazione M3U
        run: python generate_m3u.py

      - name: Clona repository pubblico
        run: |
          git clone https://x-access-token:${{ secrets.GH_TOKEN }}@github.com/your-username/pluto-tv-m3u.git public-repo
          cp pluto-*.m3u public-repo/

      - name: Push su repository pubblico
        working-directory: public-repo
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add *.m3u
          git diff --quiet && git diff --staged --quiet || git commit -m "Aggiornamento automatico $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
          git push
```

### 4. Add the GitHub secret

In your **private repository**, go to **Settings → Secrets and variables → Actions** and add a new secret:

- **Name**: `GH_TOKEN`
- **Value**: your personal access token (with `repo` scope)

### 5. Customize the script (optional)

You can change the following variables at the top of `generate_m3u.py`:

```python
GENERATE_ALL_REGIONS = True      # Set to False to generate only specific regions
LIVE_GROUP_BY_CATEGORY = True    # Group live channels by category in the M3U
GENERATE_VOD = True              # Generate VOD playlists
VOD_MAX_ITEMS = 500              # Limit number of VOD entries per file (0 = no limit)
```

If you set `GENERATE_ALL_REGIONS = False`, you must also provide a list of country codes in `REGIONS_TO_GENERATE` (e.g., `["IT", "FR"]`).

### 6. Run the workflow

- Push the code to your private repository.
- Go to the **Actions** tab and run the workflow manually (or wait for the scheduled run).
- Check your public repository – you should now see files like `pluto-live-IT.m3u`, `pluto-vod-US.m3u`, etc.

## 📁 Output files

The script produces two types of files for each region:

- `pluto-live-XX.m3u` – Live TV channels, grouped by category, sorted alphabetically.
- `pluto-vod-XX.m3u` – On‑demand movies, grouped by category, sorted alphabetically.

Example:  
`pluto-live-IT.m3u` – Italian live channels (names, descriptions, categories in Italian).  
`pluto-vod-US.m3u` – VOD movies for the United States (English).

## 🎵 Audio language

For Italian streams, the script adds `&audioLanguage=it` to the stream URL.  
If the stream contains an Italian audio track, it will be played automatically if your player (e.g., VLC) is configured to prefer Italian.

To set the preferred language in VLC:  
**Tools → Preferences → Show settings: All → Audio → Preferred audio language** → enter `ita,it`.

## ⚠️ Important notes

- The script uses **X-Forwarded-For** headers to simulate the region of the user. This works on GitHub Actions because the IP address is not the actual one of the server.
- Token refresh and rate‑limit handling are built in.
- The public repository should **not** contain any secrets; only the generated M3U files.

## 📜 License

This script is derived from the [oe-alliance/PlutoTV](https://github.com/oe-alliance/PlutoTV) plugin and is licensed under the **GPL‑2.0‑or‑later** license.

## 🙏 Credits

- Original plugin authors: Team OpenSPA, Billy2011, jbleyel, IanSav, WXBet, and contributors.
- This generator was adapted and extended by [Belfagor2005](https://github.com/Belfagor2005).

---

**Enjoy your Pluto TV playlists!** 🎬
