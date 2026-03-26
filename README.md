# Baseball Team Manager

A Django app for managing baseball team roster decisions and MLB player analysis. The manager can add players, keep active players, and kick out (release) players. Includes a net worth calculation module and MLB player search with performance prediction and market value simulation.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py load_sample_players   # Load sample MLB data
python manage.py runserver
```

Visit http://127.0.0.1:8000/

## Fetch MLB Rosters

Download 2022 MLB rosters from StatsAPI and save them to `data/` as CSV/JSON:

```bash
python scripts/fetch_mlb_rosters.py --season 2022 --format both
```

Load the saved roster snapshot into the configured Django database:

```bash
python manage.py migrate
python manage.py load_mlb_rosters --season 2022 --replace-season
```

On Heroku, the same import can be run against Heroku Postgres with:

```bash
heroku run python manage.py migrate
heroku run python manage.py load_mlb_rosters --season 2022 --replace-season --from-api
```

## LSTM Training

Train the WAR forecasting baseline on the season CSVs in `data/`:

```bash
python scripts/train_lstm_war_model.py
python scripts/train_lstm_war_model.py --dataset pitching
python scripts/train_lstm_war_model.py --dataset batting
```

Running without `--dataset` trains both models and writes artifacts to `model_artifacts/lstm_pitching/` and `model_artifacts/lstm_batting/`.
The script defaults to CPU. Pass `--device cuda` only if you want GPU training.

## Features

### Roster (팀 매니저)
- **Roster management** — Add, view, edit, and release players
- **Status filtering** — Filter by active, pending, or released
- **Contract & net worth** — Set total value, guaranteed ratio (0–1), and years. Net worth = total × ratio × years
- **Admin** — Django admin at /admin/ for quick data entry

### MLB Analysis (MLB 분석)
- **Player search** — Search MLB players by name, team, position
- **Player detail** — Future performance prediction, market value, season stats
- **Performance trend chart** — Chart.js visualization of year-over-year stats
- **Similar players** — Comparable player recommendations
- **Simulation** — Adjust stats (AVG, HR, OPS) and see predicted value update in real time

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the architecture diagram and data flow.
