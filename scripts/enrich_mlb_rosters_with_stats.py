#!/usr/bin/env python
"""
Read a roster CSV and write an enriched CSV with season/basic and advanced stats
from MLB StatsAPI.

Example:
    python scripts/enrich_mlb_rosters_with_stats.py --season 2022
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


BASE_URL = "https://statsapi.mlb.com/api/v1"

HITTING_FIELDS = [
    "gamesPlayed",
    "plateAppearances",
    "atBats",
    "runs",
    "hits",
    "doubles",
    "triples",
    "homeRuns",
    "rbi",
    "baseOnBalls",
    "strikeOuts",
    "stolenBases",
    "avg",
    "obp",
    "slg",
    "ops",
    "babip",
    "woba",
    "wrcPlus",
]

PITCHING_FIELDS = [
    "gamesPlayed",
    "gamesStarted",
    "wins",
    "losses",
    "saves",
    "holds",
    "inningsPitched",
    "hits",
    "runs",
    "earnedRuns",
    "baseOnBalls",
    "strikeOuts",
    "homeRuns",
    "era",
    "whip",
    "babip",
    "fip",
    "strikeoutWalkRatio",
]

BATCH_SIZE = 25


def fetch_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params, doseq=True)
    url = f"{BASE_URL}{path}?{query}" if query else f"{BASE_URL}{path}"

    try:
        with urlopen(url, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error {exc.code} for {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc


def read_roster_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def first_stat_split(stats_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    for block in stats_blocks:
        splits = block.get("splits") or []
        if splits:
            stat = splits[0].get("stat")
            if isinstance(stat, dict):
                return stat
    return {}


def batched(values: list[str], batch_size: int) -> list[list[str]]:
    return [values[index:index + batch_size] for index in range(0, len(values), batch_size)]


def fetch_group_stats_map(
    player_ids: list[str],
    season: int,
    group: str,
    delay_seconds: float,
) -> dict[str, dict[str, Any]]:
    stats_map: dict[str, dict[str, Any]] = {}

    for batch in batched(player_ids, BATCH_SIZE):
        payload = fetch_json(
            "/people",
            {
                "personIds": ",".join(batch),
                "hydrate": f"stats(group=[{group}],type=[season,seasonAdvanced],season={season})",
            },
        )
        for person in payload.get("people", []):
            player_id = str(person.get("id") or "").strip()
            if not player_id:
                continue
            stats_map[player_id] = first_stat_split(person.get("stats") or [])

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return stats_map


def fetch_player_group_stats(player_id: str, season: int, group: str) -> dict[str, Any]:
    payload = fetch_json(
        f"/people/{player_id}/stats",
        {
            "stats": ["season", "seasonAdvanced"],
            "group": group,
            "season": season,
        },
    )
    return first_stat_split(payload.get("stats") or [])


def is_pitcher(row: dict[str, str]) -> bool:
    return (row.get("position_type") or "").strip().lower() == "pitcher"


def select_prefixed_fields(stat: dict[str, Any], fields: list[str], prefix: str) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for field in fields:
        selected[f"{prefix}{field}"] = stat.get(field)
    return selected


def enrich_rows(
    rows: list[dict[str, str]],
    season: int,
    delay_seconds: float,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []

    pitching_ids = sorted({
        (row.get("player_id") or "").strip()
        for row in rows
        if is_pitcher(row) and (row.get("player_id") or "").strip()
    })
    hitting_ids = sorted({
        (row.get("player_id") or "").strip()
        for row in rows
        if not is_pitcher(row) and (row.get("player_id") or "").strip()
    })

    print(f"Fetching hitting stats for {len(hitting_ids)} players")
    hitting_map = fetch_group_stats_map(hitting_ids, season, "hitting", delay_seconds)
    print(f"Fetching pitching stats for {len(pitching_ids)} players")
    pitching_map = fetch_group_stats_map(pitching_ids, season, "pitching", delay_seconds)

    total = len(rows)
    for index, row in enumerate(rows, start=1):
        player_id = (row.get("player_id") or "").strip()
        if not player_id:
            enriched.append(dict(row))
            continue

        group = "pitching" if is_pitcher(row) else "hitting"
        stat = pitching_map.get(player_id, {}) if group == "pitching" else hitting_map.get(player_id, {})
        merged = dict(row)
        merged["stats_group"] = group
        merged["stats_found"] = bool(stat)

        if group == "pitching":
            merged.update(select_prefixed_fields(stat, PITCHING_FIELDS, "pitching_"))
            merged.update({f"hitting_{field}": None for field in HITTING_FIELDS})
        else:
            merged.update(select_prefixed_fields(stat, HITTING_FIELDS, "hitting_"))
            merged.update({f"pitching_{field}": None for field in PITCHING_FIELDS})

        enriched.append(merged)

        if index % 50 == 0 or index == total:
            print(f"Processed {index}/{total} roster rows")

    return enriched


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("No rows to write.")

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an enriched MLB roster CSV with season stats from StatsAPI."
    )
    parser.add_argument("--season", type=int, default=2022, help="Target season year.")
    parser.add_argument(
        "--input-csv",
        type=Path,
        help="Roster CSV to read. Defaults to data/mlb_rosters_<season>.csv.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        help="Output CSV path. Defaults to data/mlb_rosters_<season>_enriched.csv.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.05,
        help="Optional delay between API calls to reduce request bursts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_csv = args.input_csv or Path("data") / f"mlb_rosters_{args.season}.csv"
    output_csv = args.output_csv or Path("data") / f"mlb_rosters_{args.season}_enriched.csv"

    if not input_csv.exists():
        raise SystemExit(f"Roster CSV not found: {input_csv}")

    rows = read_roster_csv(input_csv)
    enriched_rows = enrich_rows(rows, args.season, args.delay_seconds)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    write_csv(output_csv, enriched_rows)
    print(f"Wrote enriched CSV: {output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
