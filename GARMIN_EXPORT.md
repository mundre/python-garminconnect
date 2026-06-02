# Garmin export & dashboard — setup guide

Personal ops guide for downloading Garmin Connect data and generating HTML health dashboards with [python-garminconnect](README.md).

---

## Quick start (one script)

After [one-time setup](#one-time-setup-new-computer):

```bash
./run_dashboard.sh weekly    # last Mon–Sun — run on Mondays
./run_dashboard.sh monthly   # previous calendar month — run on the 1st
```

Output is always a **single HTML file** under `your_data/dashboards/`:

| Mode | Example file |
|------|----------------|
| weekly | `your_data/dashboards/weekly_2026_W22.html` |
| monthly | `your_data/dashboards/monthly_2026_05.html` |

The script prints the full path when done. Attach that file to an email, or paste/import the HTML into your mail tool however you prefer.

Equivalent Python (same result):

```bash
source .venv/bin/activate
python3 garmin_dashboard.py --mode weekly --fetch
python3 garmin_dashboard.py --mode monthly --fetch
python3 garmin_dashboard.py --mode auto --fetch   # weekly on Mon, monthly on 1st
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

## Using the HTML in email

The dashboard is **self-contained static HTML** (no JavaScript, no CDN). Options:

1. **Attach the file** — recipients open `monthly_2026_05.html` in a browser.
2. **Drag into mail** — some clients embed or attach HTML correctly.
3. **Automate elsewhere** — point your own mail script at the path printed by `run_dashboard.sh`.

There is no built-in SMTP sender in this project; you control how the HTML is delivered.

---

## Paths & files

| Item | Location |
|------|----------|
| Python venv | `.venv/` |
| Garmin tokens | `~/.garminconnect/garmin_tokens.json` |
| Cached daily data | `your_data/YYYY_MM/daily_stats.json` |
| Training cache | `your_data/YYYY_MM/training_metrics.json` |
| Activities | `your_data/YYYY_MM/activities.json` |
| **Dashboard output** | `your_data/dashboards/weekly_YYYY_Www.html` or `monthly_YYYY_MM.html` |

---

## All scripts

| Script | Purpose |
|--------|---------|
| **`run_dashboard.sh`** | **Main entry:** `./run_dashboard.sh weekly\|monthly` |
| `garmin_dashboard.py` | Build dashboard (`--mode weekly\|monthly\|auto`, `--fetch`) |
| `example.py` | Login + sanity check |
| `download_last_month.py` | Full export (daily stats + GPX) |
| `download_last_month_lite.py` | Lite export |

---

## Dashboard features

Static HTML — works in any browser.

**Panels:** stat cards, steps, resting HR, active calories, sleep, endurance + HRV, recovery/stress trends, training status, activity fitness impact, activity tables, daily breakdown. Weekend shading on charts.

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
| Rate limits | Retry later; scripts sleep between API calls |

---

## Downloads log

### 2026-05 (May 2026) — full export on 2026-06-01

Folder: `your_data/2026_05/` — 14 activities, daily stats, GPX files.
