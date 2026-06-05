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

| Mode | Default (`email_friendly_only`) | Gmail PNG (`email_dashboard`) | Browser (`dashboard`) |
|------|----------------------------------|-------------------------------|------------------------|
| weekly | `weekly_2026_W22.html` | `weekly_2026_W22_email_dashboard.html` | `weekly_2026_W22_dashboard.html` |
| monthly | `monthly_2026_05.html` | `monthly_2026_05_email_dashboard.html` | `monthly_2026_05_dashboard.html` |

**Default (`--format email_friendly_only`):** Dark theme, table layout, **HTML bar charts** — no Cairo. Paste-friendly for most email clients.

**Gmail PNG (`--format email_dashboard`):** Same panels with **embedded PNG chart images** (needs `cairosvg` + Cairo). `--format email` is an alias.

**Browser (`--format dashboard`):** Full SVG dashboard with CSS grid — best in a browser.

```bash
./run_dashboard.sh weekly                                    # email-friendly (default)
./run_dashboard.sh weekly --format email_dashboard           # PNG for Gmail
./run_dashboard.sh weekly --format dashboard                 # browser SVG
python3 garmin_dashboard.py --mode monthly --fetch --open
```

Equivalent Python:

```bash
source .venv/bin/activate
python3 garmin_dashboard.py --mode weekly --fetch                         # default
python3 garmin_dashboard.py --mode monthly --fetch --format email_dashboard
python3 garmin_dashboard.py --mode monthly --fetch --format dashboard
python3 garmin_dashboard.py --mode auto --fetch
```

---

## One-time setup — macOS (complete)

Copy-paste these steps on a new Mac. Total time ~10 minutes.

### Step 1: Homebrew (skip if you already have it)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After install, follow the “Next steps” Homebrew prints (add `brew` to your PATH). Then:

```bash
brew --version
```

### Step 2: Install Python 3.12

```bash
brew install python@3.12 git
```

**Cairo is only needed for `--format email_dashboard`** (PNG charts). The default `email_friendly_only` and `dashboard` formats do not require it.

Verify Python:

```bash
python3.12 --version    # should show 3.12.x
```

### Step 3: Clone the project

```bash
cd ~/personal_github   # or wherever you keep projects
git clone https://github.com/mundre/python-garminconnect.git python-garminconnect-master
cd python-garminconnect-master
```

Or copy the folder from another Mac (do **not** copy `.venv` — recreate it).

### Step 4: Python virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[example]"
```

For Gmail PNG charts (`--format email_dashboard`), also install Cairo:

```bash
brew install cairo
python3 -c "import cairosvg; print('cairosvg ok')"
```

### Step 5: Garmin login (once)

```bash
source .venv/bin/activate
python3 example.py
```

- Enter Garmin email and password (and MFA code if prompted).
- Tokens saved to `~/.garminconnect/garmin_tokens.json`.

**Alternative:** copy tokens from your other Mac:

```bash
mkdir -p ~/.garminconnect
scp other-mac:~/.garminconnect/garmin_tokens.json ~/.garminconnect/
```

### Step 6: Enable and test the run script

```bash
chmod +x run_dashboard.sh
./run_dashboard.sh weekly
./run_dashboard.sh monthly
```

Check output:

```bash
ls -la your_data/dashboards/
open your_data/dashboards/weekly_*.html    # default email-friendly HTML
```

For browser SVG: `./run_dashboard.sh weekly --format dashboard`. For Gmail PNG charts: `--format email_dashboard` (requires Cairo).

### Step 7: Ongoing use

```bash
cd ~/personal_github/python-garminconnect-master
source .venv/bin/activate   # each new terminal session
./run_dashboard.sh weekly   # run on Mondays
./run_dashboard.sh monthly  # run on the 1st of the month
```

Gmail PNG version (optional, needs Cairo):

```bash
./run_dashboard.sh weekly --format email_dashboard
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

**macOS — only for `--format email_dashboard`:** install Cairo so SVG charts can be converted to PNG:

```bash
brew install cairo
```

**Linux (Debian/Ubuntu)** — for `--format email_dashboard`, install system libs first:

```bash
sudo apt update
sudo apt install -y \
  libcairo2-dev libpango1.0-dev libgdk-pixbuf-2.0-dev libffi-dev pkg-config \
  libx11-dev libxrender-dev libxext-dev libxcb-render0-dev libxcb-shm0-dev \
  libjpeg-dev libpng-dev
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

- [ ] macOS: `brew install python@3.12 git` (+ `cairo` only if using `email_dashboard`)
- [ ] Clone: `git clone https://github.com/mundre/python-garminconnect.git`
- [ ] `python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[example]"`
- [ ] (Optional) Verify PNG charts: `python3 -c "import cairosvg; print('ok')"`
- [ ] Run `python3 example.py` (or copy `~/.garminconnect/garmin_tokens.json`)
- [ ] `chmod +x run_dashboard.sh`
- [ ] Test: `./run_dashboard.sh weekly` and `./run_dashboard.sh monthly`
- [ ] Confirm HTML in `your_data/dashboards/`
- [ ] (Optional) Copy `your_data/` from old machine for history

---

## Using the HTML in Gmail

**Default (`email_friendly_only`)** — `./run_dashboard.sh weekly` — table layout with HTML bar charts. No Cairo. Works in most email clients when pasted.

**Gmail PNG (`email_dashboard`)** — best chart fidelity in Gmail:

```bash
./run_dashboard.sh weekly --format email_dashboard
```

Output: `weekly_*_email_dashboard.html` with embedded PNG images (needs Cairo).

**Browser (`dashboard`)** — open `weekly_*_dashboard.html` in a browser for full SVG charts. Not for email paste.

---

## Paths & files

| Item | Location |
|------|----------|
| Python venv | `.venv/` |
| Garmin tokens | `~/.garminconnect/garmin_tokens.json` |
| Cached daily data | `your_data/YYYY_MM/daily_stats.json` |
| Training cache | `your_data/YYYY_MM/training_metrics.json` |
| Activities | `your_data/YYYY_MM/activities.json` |
| **Dashboard output (default)** | `your_data/dashboards/monthly_YYYY_MM.html` |
| **Dashboard output (Gmail PNG)** | `your_data/dashboards/monthly_YYYY_MM_email_dashboard.html` |
| **Dashboard output (browser)** | `your_data/dashboards/monthly_YYYY_MM_dashboard.html` |

---

## All scripts

| Script | Purpose |
|--------|---------|
| **`run_dashboard.sh`** | **Main entry:** `./run_dashboard.sh weekly\|monthly` |
| `garmin_dashboard.py` | Build dashboard (`--format email_friendly_only\|email_dashboard\|dashboard`) |
| `garmin_email_friendly_html.py` | Default email-friendly renderer (HTML bars, no Cairo) |
| `garmin_email_html.py` | PNG email renderer (`--format email_dashboard`) |
| `run_dashboard_cron.sh` | Cron wrapper for Conda/Cairo (`--format email_dashboard`) |
| `example.py` | Login + sanity check |
| `download_last_month.py` | Full export (daily stats + GPX) |
| `download_last_month_lite.py` | Lite export |

---

## Dashboard features

Static HTML — no JavaScript.

**Default (`email_friendly_only`):** dark theme, table layout, HTML bar charts. No Cairo.

**Gmail (`email_dashboard`):** same panels; charts as embedded PNG images.

**Browser (`dashboard`):** full SVG dashboard with CSS grid.

---

## Optional: full data export

```bash
source .venv/bin/activate
python3 download_last_month.py
```

Output: `your_data/YYYY_MM/` with GPX files (~1 min).

---

## Cron / OpenClaw

**Default (SVG dashboard, no Cairo):**

```bash
export HOME=/Users/youruser
export GARMINTOKENS=$HOME/.garminconnect
/bin/bash /Users/youruser/path/to/python-garminconnect-master/run_dashboard.sh weekly
```

**Gmail PNG (`email_dashboard`):** use `run_dashboard_cron.sh` when Cairo is installed via Conda:

```bash
export HOME=/Users/youruser
/bin/bash /Users/youruser/path/to/python-garminconnect-master/run_dashboard_cron.sh weekly --format email_dashboard
```

Optional overrides: `CONDA_BASE`, `CONDA_ENV_NAME` (default `garmin`), `GARMINTOKENS`.

---

## Downloads log

### 2026-05 (May 2026) — full export on 2026-06-01

Folder: `your_data/2026_05/` — 14 activities, daily stats, GPX files.
