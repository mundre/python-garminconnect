# Garmin export & dashboard — setup guide

Personal ops guide for downloading Garmin Connect data and generating HTML health dashboards with [python-garminconnect](README.md).

---

## Quick start (one script)

After [one-time setup](#one-time-setup-new-computer):

```bash
./run_dashboard.sh weekly    # last Mon–Sun — run on Mondays
./run_dashboard.sh monthly   # previous calendar month — run on the 1st
```

Output is a **single HTML file** under `your_data/dashboards/`:

| Mode | Email format (default) | Browser format |
|------|------------------------|----------------|
| weekly | `weekly_2026_W22.html` | `weekly_2026_W22_dashboard.html` |
| monthly | `monthly_2026_05.html` | `monthly_2026_05_dashboard.html` |

**Default (`--format email`):** Same dark Grafana-style dashboard as the browser version — charts are rendered as **embedded PNG images** (Gmail-safe). Tables and stat cards use inline styles on a dark theme.

**Browser (`--format dashboard`):** Live SVG charts for local viewing.

```bash
./run_dashboard.sh monthly                              # email format (default)
./run_dashboard.sh weekly --format dashboard          # browser SVG charts
python3 garmin_dashboard.py --mode monthly --format dashboard --open   # browser preview
```

Equivalent Python:

```bash
source .venv/bin/activate
python3 garmin_dashboard.py --mode weekly --fetch              # email (default)
python3 garmin_dashboard.py --mode monthly --fetch --format dashboard
python3 garmin_dashboard.py --mode auto --fetch
```

---

## One-time setup (new computer)

### 1. Prerequisites

- **Python 3.12+** (macOS: `brew install python@3.12`)
- **Git** (clone this repo or copy the project folder)
- A **Garmin Connect** account

### 2. Clone / copy project

```bash
git clone <your-repo-url> python-garminconnect-master
cd python-garminconnect-master
```

Or copy the folder from another computer (include scripts; you can skip `.venv` and recreate it).

### 3. Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[example]"
```

**macOS — chart images for email format:** install Cairo once so SVG charts can be converted to PNG:

```bash
brew install cairo
```

Then reinstall: `pip install -e ".[example]"` (includes `cairosvg`).

### 4. Garmin login (once)

```bash
source .venv/bin/activate
python3 example.py
```

- Enter Garmin email/password (and MFA if prompted).
- Tokens saved to **`~/.garminconnect/garmin_tokens.json`**.
- Re-run if login expires.

Optional: copy tokens from another machine:

```bash
mkdir -p ~/.garminconnect
scp other-host:~/.garminconnect/garmin_tokens.json ~/.garminconnect/
```

### 5. Make the run script executable

```bash
chmod +x run_dashboard.sh
```

### 6. Test

```bash
./run_dashboard.sh weekly
./run_dashboard.sh monthly
```

Confirm HTML files appear in `your_data/dashboards/`.

---

## Replication checklist

- [ ] Install Python 3.12+
- [ ] Clone/copy project directory
- [ ] `python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[example]"`
- [ ] Run `python3 example.py` (or copy `~/.garminconnect/garmin_tokens.json`)
- [ ] `chmod +x run_dashboard.sh`
- [ ] Test: `./run_dashboard.sh weekly` and `./run_dashboard.sh monthly`
- [ ] Confirm HTML in `your_data/dashboards/`
- [ ] (Optional) Copy `your_data/` from old machine for history

---

## Using the HTML in Gmail

The default **email format** matches the browser dashboard visually:

- Dark theme (`#0b0c0e` background, same colors as dashboard)
- Charts exported as **inline PNG images** (same SVG charts as `--format dashboard`)
- Tables and stat cards with inline styles (no CSS grid/flex/variables)

**Gmail note:** embedded images use `data:image/png;base64,...`. Most clients display these; if Gmail strips them when pasting, attach the `.html` file or send via an HTML-capable mail tool.

For interactive SVG charts locally: `./run_dashboard.sh weekly --format dashboard`

---

## Paths & files

| Item | Location |
|------|----------|
| Python venv | `.venv/` |
| Garmin tokens | `~/.garminconnect/garmin_tokens.json` |
| Cached daily data | `your_data/YYYY_MM/daily_stats.json` |
| Training cache | `your_data/YYYY_MM/training_metrics.json` |
| Activities | `your_data/YYYY_MM/activities.json` |
| **Dashboard output (email)** | `your_data/dashboards/monthly_YYYY_MM.html` |
| **Dashboard output (browser)** | `your_data/dashboards/monthly_YYYY_MM_dashboard.html` |

---

## All scripts

| Script | Purpose |
|--------|---------|
| **`run_dashboard.sh`** | **Main entry:** `./run_dashboard.sh weekly\|monthly` |
| `garmin_dashboard.py` | Build dashboard (`--format email\|dashboard`, `--mode`, `--fetch`) |
| `garmin_email_html.py` | Email-format HTML renderer (used internally) |
| `example.py` | Login + sanity check |
| `download_last_month.py` | Full export (daily stats + GPX) |
| `download_last_month_lite.py` | Lite export |

---

## Dashboard features

Static HTML — no JavaScript.

**Email format:** same panels as dashboard; charts as embedded PNG images on dark theme.

**Dashboard format:** same metrics with live SVG charts.

---

## Optional: full data export

```bash
source .venv/bin/activate
python3 download_last_month.py
```

Output: `your_data/YYYY_MM/` with GPX files (~1 min).

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Login fails | Run `python3 example.py` again; check MFA |
| Empty dashboard | Run with `--fetch`; check tokens |
| Charts missing in email HTML | macOS: `brew install cairo` then `pip install cairosvg` |
| Rate limits | Retry later; scripts sleep between API calls |

---

## Downloads log

### 2026-05 (May 2026) — full export on 2026-06-01

Folder: `your_data/2026_05/` — 14 activities, daily stats, GPX files.
