#!/usr/bin/env python
"""
Download MLB team rosters for a given season from the public StatsAPI.

By default this script fetches all active MLB teams for the target season,
downloads each team roster, and writes:

- data/mlb_rosters_<season>.json
- data/mlb_rosters_<season>.csv

Example:
    python scripts/fetch_mlb_rosters.py --season 2022 --format both
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


BASE_URL = "https://statsapi.mlb.com/api/v1"


def fetch_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params)
    url = f"{BASE_URL}{path}?{query}"

    try:
        with urlopen(url, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error {exc.code} for {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc


def fetch_teams(season: int) -> list[dict[str, Any]]:
    payload = fetch_json("/teams", {"sportId": 1, "season": season})
    teams = payload.get("teams", [])
    return [team for team in teams if team.get("active")]


def fetch_team_roster(team_id: int, season: int) -> list[dict[str, Any]]:
    payload = fetch_json(f"/teams/{team_id}/roster", {"season": season})
    return payload.get("roster", [])


def flatten_roster_row(
    season: int,
    team: dict[str, Any],
    roster_entry: dict[str, Any],
) -> dict[str, Any]:
    person = roster_entry.get("person", {})
    position = roster_entry.get("position", {})
    status = roster_entry.get("status", {})

    return {
        "season": season,
        "team_id": team.get("id"),
        "team_name": team.get("name"),
        "team_abbreviation": team.get("abbreviation"),
        "league_name": (team.get("league") or {}).get("name"),
        "division_name": (team.get("division") or {}).get("name"),
        "player_id": person.get("id"),
        "player_name": person.get("fullName"),
        "player_link": person.get("link"),
        "jersey_number": roster_entry.get("jerseyNumber"),
        "position_code": position.get("code"),
        "position_name": position.get("name"),
        "position_type": position.get("type"),
        "position_abbreviation": position.get("abbreviation"),
        "status_code": status.get("code"),
        "status_description": status.get("description"),
    }


def build_outputs(season: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    teams = fetch_teams(season)

    json_rows: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []

    for team in teams:
        roster = fetch_team_roster(team["id"], season)
        json_rows.append(
            {
                "season": season,
                "team": {
                    "id": team.get("id"),
                    "name": team.get("name"),
                    "abbreviation": team.get("abbreviation"),
                    "league": (team.get("league") or {}).get("name"),
                    "division": (team.get("division") or {}).get("name"),
                },
                "roster": roster,
            }
        )

        for roster_entry in roster:
            csv_rows.append(flatten_roster_row(season, team, roster_entry))

    return json_rows, csv_rows


def write_json(path: Path, payload: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "season",
        "team_id",
        "team_name",
        "team_abbreviation",
        "league_name",
        "division_name",
        "player_id",
        "player_name",
        "player_link",
        "jersey_number",
        "position_code",
        "position_name",
        "position_type",
        "position_abbreviation",
        "status_code",
        "status_description",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download MLB team rosters from StatsAPI and save them to disk."
    )
    parser.add_argument("--season", type=int, default=2022, help="Target season year.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Directory where output files will be written.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "csv", "both"),
        default="both",
        help="Output format to write.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    json_rows, csv_rows = build_outputs(args.season)

    json_path = args.output_dir / f"mlb_rosters_{args.season}.json"
    csv_path = args.output_dir / f"mlb_rosters_{args.season}.csv"

    if args.format in {"json", "both"}:
        write_json(json_path, json_rows)
        print(f"Wrote JSON: {json_path}")

    if args.format in {"csv", "both"}:
        write_csv(csv_path, csv_rows)
        print(f"Wrote CSV: {csv_path}")

    print(f"Fetched {len(json_rows)} teams and {len(csv_rows)} roster entries for {args.season}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
