# Baseball Team Manager

A Django app for managing baseball team roster decisions and MLB player analysis. The manager can add players, keep active players, and kick out (release) players. Includes a net worth calculation module and MLB player search with performance prediction and market value simulation.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py load_sample_players   # Load sample MLB data
python manage.py runserver
```

If you want to run model-training scripts locally, install the ML extras too:

```bash
pip install -r requirements-ml.txt
```

Visit http://127.0.0.1:8000/

If you want to run the training/data-science scripts locally, install the heavier ML dependencies separately:

```bash
pip install -r requirements-ml.txt
```

## Fetch MLB Rosters

Download 2022 MLB rosters from StatsAPI and save them to `data/` as CSV/JSON:

```bash
python scripts/fetch_mlb_rosters.py --season 2022 --format both
```

Create a separate enriched roster CSV with season/basic and advanced stats from StatsAPI:

```bash
python scripts/enrich_mlb_rosters_with_stats.py --season 2022
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

Load the local historical player stat CSVs into the same database that powers `/api/teams/`:

```bash
python manage.py load_team_api_stats --replace --batting-file data/batters_2018_2022.csv --pitching-file data/pitchers_2018_2022.csv
heroku run python manage.py load_team_api_stats --replace --batting-file data/batters_2018_2022.csv --pitching-file data/pitchers_2018_2022.csv
```

Load both similar-player datasets into the API tables:

```bash
python manage.py load_api_similar_players --replace
heroku run -a <app-name> -- python manage.py load_api_similar_players --replace
```

## Similar Player Methods

The player detail APIs expose the TabNet-based similar-player list.

- `tabnet_similar_players`
  Uses `data/batters_recommendations.csv` and `data/pitchers_recommendations.csv`.
  This list was built with deep-learning-based representation learning and metric learning.

### TabNet-Based Similarity Pipeline

The legacy approach relied on simple statistical comparison and accumulated record matching.
The newer approach learns a similarity space with deep representation learning.

Overall pipeline:

`data preprocessing -> player profile generation -> TabNet encoding -> metric learning -> embeddings -> similarity computation -> FA recommendation`

### Data Preprocessing

- Raw data is built from season-level records from 2018 to 2022.
- Records are merged by `player_id`.
- Seasonal performance is aggregated with a weighted average, giving more weight to recent seasons.
- Numeric features are normalized with standard scaling.
- Categorical features such as `Throws` and `Position` are encoded.
- Missing values are imputed with the median, and remaining `NaN` values are filled with `0`.

### Feature Set

Batter features:

- `WAR`, `AVG`, `OPS`, `HR`, `RBI`, `wRC+`, `wOBA`, `BABIP`, `ISO`, `BB%`, `K%`, `Exit_Velocity`, `Launch_Angle`, `Age`, `Debut Year`, `Height`, `Weight`, `Position`, `Bats`, `Throws`

Pitcher features:

- `WAR`, `ERA`, `FIP`, `WHIP`, `K/9`, `BB/9`, `IP`, `SO`, `xERA`, `xFIP`, `LOB%`, `BABIP`, `HR/9`, `velocity`, `Age`, `Debut Year`, `Height`, `Weight`, `Position`, `Bats`, `Throws`

### TabNet Representation Learning

TabNet is a deep model specialized for tabular data.
It learns representations with attention-based feature selection that can choose important features per sample.

- Reference paper: [TabNet: Attentive Interpretable Tabular Learning](https://arxiv.org/pdf/1908.07442)
- Input flow: `input -> feature selection mask -> transformation -> repeated steps -> final representation`
- `TabNetPretrainer` is used to pretrain feature relationships in player data.
- The pretrained TabNet weights are then used to initialize the feature encoder.
- Metric learning is applied on top of the encoder output to learn a player embedding space.

In practice, the pretraining stage helps the model understand feature structure, and the later metric-learning stage shapes distances so that similar players are close in the embedding space.

### Metric Learning

Metric learning is used to optimize similarity relationships between players in the learned embedding space.

- Concept reference: [Metric Learning overview](https://ysk1m.tistory.com/9)
- Training objective: Triplet Loss
- Training tuple:
  - Anchor: reference player
  - Positive: similar player
  - Negative: dissimilar player

Positive samples are chosen using similar position, similar age range, and similar performance.
Negative samples do not satisfy those conditions.

The loss is:

`loss = max(0, d(A, P) - d(A, N) + margin)`

This makes Anchor and Positive closer, while pushing Anchor and Negative farther apart.
After training, cosine similarity is computed on the learned embeddings for recommendation.

### Recommendation Rules

- Similarity is computed with cosine similarity:
  - `similarity = cos(embedding_A, embedding_B)`
- Candidate pool is restricted to FA players.
- Recommendations are filtered to the same position and a similar age range.
- Final output is Top-3 similar FA players for each player.

### Explainability

The TabNet feature mask is used for explainability.

- TabNet mask -> important features -> Top-3 features -> compare actual values

This makes it possible to explain why a recommendation was made by showing which features the model considered most important and how similar those values were in practice.

### Evaluation

The evaluation methodology for the TabNet-based recommendation pipeline is not finalized yet and should be defined separately.

## LSTM Training

Train the WAR forecasting baseline on the season CSVs in `data/`:

```bash
python scripts/train_lstm_war_model.py
python scripts/train_lstm_war_model.py --dataset pitching
python scripts/train_lstm_war_model.py --dataset batting
```

Running without `--dataset` trains both models and writes artifacts to `model_artifacts/lstm_pitching/` and `model_artifacts/lstm_batting/`.
The script defaults to CPU. Pass `--device cuda` only if you want GPU training.

## Heroku Postgres Deployment

The API paths stay the same on Heroku, for example `/api/teams/` and `/api/rosters/`.
Only the host changes unless you point your existing domain to the Heroku app.

This project now uses:

- local development: SQLite by default
- Heroku/runtime with `DATABASE_URL` set: PostgreSQL

Typical deployment flow:

```bash
heroku addons:create heroku-postgresql:essential-0 -a <app-name>
heroku config:set DJANGO_SECRET_KEY="<secret>" DEBUG=False ALLOWED_HOSTS="<your-domain>,<app-name>.herokuapp.com" -a <app-name>
git push heroku main
```

The `release` phase runs `python manage.py migrate`, so schema changes are applied automatically on deploy.

## Migrating Existing SQLite Data

If you want to keep existing local data, export from SQLite and import into Heroku Postgres:

```bash
python manage.py dumpdata --exclude auth.permission --exclude contenttypes > data.json
heroku run python manage.py loaddata data.json -a <app-name>
```

For API seed data managed from files, you can also reload directly in Heroku:

```bash
heroku run python manage.py load_team_api_stats --replace -a <app-name>
heroku run python manage.py load_roster_photos --replace -a <app-name>
```
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
