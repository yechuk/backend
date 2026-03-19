#!/usr/bin/env python
"""
Estimate $/WAR by position from the consolidated free-agent workbook and a
player-season WAR file.

This script:
- loads the consolidated free-agent data from
  data/MLB-Free Agency 1991-2026_consolidated.xlsx
- loads a WAR table (one row per player-season)
- constructs WAR_at_signing features (previous 3 seasons by default)
- fits a Swartz-style linear model with position interactions:

    AAV_real = β₀ + β₁·WAR_at_signing + f(Age) + γ_Year + δ_Position
               + Σ_p θ_p·(WAR_at_signing × 1[Position=p]) + ε

- exports:
  - data/position_dollars_per_war.csv  (Position, dollars_per_war, n_obs, etc.)
  - data/position_dollars_per_war.md   (short markdown summary)

WAR input format (CSV by default):
- Player: player name matching the consolidated sheet
- Year: season year (int)
- WAR: wins above replacement for that season (float)

Usage examples (from project root):
    python scripts/estimate_position_dollars_per_war.py
    python scripts/estimate_position_dollars_per_war.py \\
        --fa-path data/MLB-Free Agency 1991-2026_consolidated.xlsx \\
        --war-path data/war/player_year_war.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FA_PATH = PROJECT_ROOT / "data" / "MLB-Free Agency 1991-2026_consolidated.xlsx"
DEFAULT_WAR_PATH = PROJECT_ROOT / "data" / "war" / "player_year_war.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "position_dollars_per_war.csv"
OUTPUT_MD = PROJECT_ROOT / "data" / "position_dollars_per_war.md"
OUTPUT_MODEL_JSON = PROJECT_ROOT / "data" / "position_dollars_per_war_model.json"


def _load_free_agents(path: Path) -> pd.DataFrame:
    """Load and lightly clean the consolidated free-agent workbook."""
    df = pd.read_excel(path, sheet_name="free_agents_1991_2026")
    # Keep only signed MLB free agents with non-missing AAV and Position.
    df = df[df["Status"] == "signed"].copy()
    df = df.dropna(subset=["Player", "Position", "Year", "AAV"])
    # Normalize position strings (strip whitespace).
    df["Position"] = df["Position"].astype(str).str.strip()
    df["Year"] = df["Year"].astype(int)
    # Age may have NaNs; keep as float.
    return df


def _load_war(path: Path) -> pd.DataFrame:
    """Load player-season WAR table.

    Expected columns: Player, Year, WAR
    """
    df = pd.read_csv(path)
    required = {"Player", "Year", "WAR"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"WAR file {path} is missing required columns: {sorted(missing)}")
    df = df[list(required)].copy()
    df["Player"] = df["Player"].astype(str).str.strip()
    df["Year"] = df["Year"].astype(int)
    df["WAR"] = df["WAR"].astype(float)
    return df


def _compute_war_window(
    fa_df: pd.DataFrame,
    war_df: pd.DataFrame,
    years_back: int,
    label: str,
) -> pd.Series:
    """Compute WAR_at_signing as sum of WAR in [Year-years_back, Year-1].

    This loops by player; the dataset is small enough that this is acceptable
    and keeps the logic simple.
    """
    # Index WAR by (Player, Year) for quick lookup.
    war_by_player = {
        player: sub_df.set_index("Year")["WAR"]
        for player, sub_df in war_df.groupby("Player")
    }

    def _sum_window(row: pd.Series) -> float:
        player = str(row["Player"]).strip()
        year = int(row["Year"])
        series = war_by_player.get(player)
        if series is None:
            return np.nan
        start = year - years_back
        end = year - 1
        window = series.loc[start:end] if start <= end else series.iloc[0:0]
        return float(window.sum()) if not window.empty else 0.0

    values = fa_df.apply(_sum_window, axis=1)
    values.name = label
    return values


def build_model_dataset(
    fa_df: pd.DataFrame,
    war_df: pd.DataFrame,
) -> pd.DataFrame:
    """Create modeling dataset with WAR_at_signing and basic covariates."""
    df = fa_df.copy()

    # Compute previous-3-years WAR window as headline feature.
    df["WAR_prev3"] = _compute_war_window(df, war_df, years_back=3, label="WAR_prev3")

    # Drop rows without WAR information if desired; for now, keep zeros as 0 and NaNs as missing.
    # We will drop rows with missing WAR_prev3 before fitting.
    df["Age2"] = df["Age"].astype(float) ** 2
    df["AAV_real"] = df["AAV"].astype(float)

    # Keep only essential columns for modeling.
    keep_cols = [
        "Year",
        "Player",
        "Position",
        "Age",
        "Age2",
        "AAV_real",
        "WAR_prev3",
    ]
    model_df = df[keep_cols].copy()
    model_df = model_df.dropna(subset=["AAV_real", "WAR_prev3", "Age"])
    return model_df


def fit_linear_model(model_df: pd.DataFrame):
    """Fit the Swartz-style linear model with position interactions.

    AAV_real ~ WAR_prev3 + Age + Age^2 + C(Year) + C(Position) + WAR_prev3:C(Position)
    """
    # Ensure types are sensible for patsy/statsmodels.
    model_df = model_df.copy()
    model_df["Year"] = model_df["Year"].astype(int)
    model_df["Position"] = model_df["Position"].astype(str)

    formula = (
        "AAV_real ~ WAR_prev3 + Age + Age2 + C(Year) + C(Position)"
        " + WAR_prev3:C(Position)"
    )
    model = smf.ols(formula=formula, data=model_df).fit()
    return model


def extract_position_dollars_per_war(model, model_df: pd.DataFrame) -> pd.DataFrame:
    """Compute implied $/WAR by position from the fitted linear model.

    For each position p:
        $/WAR(p) = β_WAR_prev3 + θ_p

    where:
      - β_WAR_prev3 is the coefficient on WAR_prev3
      - θ_p is the coefficient on the interaction WAR_prev3:C(Position)[p]
        (0 for the reference position).
    """
    params = model.params
    base_coef = params.get("WAR_prev3", np.nan)

    positions = sorted(model_df["Position"].unique())
    records = []

    # Determine reference position as used by statsmodels (lexicographically first).
    # For that position, the interaction term is omitted, so θ_p = 0.
    reference_position = None
    # Find any interaction term to infer naming pattern.
    for name in params.index:
        if name.startswith("WAR_prev3:C(Position)[T."):
            # Name like 'WAR_prev3:C(Position)[T.CF]'
            # statsmodels uses the first category as reference; others appear as T.<cat>.
            break

    # statsmodels chooses the reference category as the *first* category seen.
    # For safety, we can get it from model.data.orig_exog design info if needed,
    # but here we infer it as any position not appearing in the interaction terms.
    interaction_positions = {
        name.split("[T.", 1)[1].rstrip("]")
        for name in params.index
        if name.startswith("WAR_prev3:C(Position)[T.")
    }
    for pos in positions:
        if pos not in interaction_positions:
            reference_position = pos
            break

    for pos in positions:
        if pos == reference_position:
            theta = 0.0
        else:
            key = f"WAR_prev3:C(Position)[T.{pos}]"
            theta = params.get(key, 0.0)
        dollars_per_war = base_coef + theta
        n_obs = int((model_df["Position"] == pos).sum())
        records.append(
            {
                "Position": pos,
                "dollars_per_WAR": float(dollars_per_war),
                "base_WAR_coef": float(base_coef),
                "interaction_theta": float(theta),
                "n_signings": n_obs,
                "is_reference": pos == reference_position,
            }
        )

    return pd.DataFrame.from_records(records)


def write_outputs(
    table_df: pd.DataFrame,
    model,
    model_df: pd.DataFrame,
    *,
    csv_path: Path = OUTPUT_CSV,
    md_path: Path = OUTPUT_MD,
    json_path: Path = OUTPUT_MODEL_JSON,
) -> None:
    """Persist results: CSV, markdown summary, and a small JSON with metadata."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    table_df.to_csv(csv_path, index=False)

    # Simple markdown summary.
    lines = []
    lines.append("# Position $/WAR summary\n")
    lines.append("")
    lines.append(f"- Observations used: {len(model_df)}")
    years = sorted(model_df["Year"].unique())
    lines.append(f"- Year range: {years[0]}–{years[-1]}")
    lines.append("")
    lines.append("| Position | $/WAR | n signings | reference? |")
    lines.append("|----------|-------|------------|------------|")
    for row in table_df.sort_values("Position").itertuples(index=False):
        lines.append(
            f"| {row.Position} | {row.dollars_per_WAR:,.0f} | "
            f"{row.n_signings} | {'yes' if row.is_reference else 'no'} |"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    # Small JSON blob for Django or other consumers.
    payload = {
        "base_WAR_coef": table_df["base_WAR_coef"].iloc[0]
        if not table_df.empty
        else None,
        "positions": {
            row.Position: {
                "dollars_per_WAR": row.dollars_per_WAR,
                "interaction_theta": row.interaction_theta,
                "n_signings": row.n_signings,
                "is_reference": bool(row.is_reference),
            }
            for row in table_df.itertuples(index=False)
        },
        "n_obs": len(model_df),
        "year_min": int(years[0]) if years else None,
        "year_max": int(years[-1]) if years else None,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate $/WAR by position using a Swartz-style linear model."
    )
    parser.add_argument(
        "--fa-path",
        type=Path,
        default=DEFAULT_FA_PATH,
        help="Path to consolidated free-agent workbook.",
    )
    parser.add_argument(
        "--war-path",
        type=Path,
        default=DEFAULT_WAR_PATH,
        help="Path to player-season WAR CSV file.",
    )
    parser.add_argument(
        "--min-war-prev3",
        type=float,
        default=None,
        help="Optional minimum WAR_prev3 for inclusion (e.g., 0.0 or 1.0).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fa_df = _load_free_agents(args.fa_path)
    war_df = _load_war(args.war_path)

    model_df = build_model_dataset(fa_df, war_df)
    if args.min_war_prev3 is not None:
        model_df = model_df[model_df["WAR_prev3"] >= args.min_war_prev3].copy()

    if model_df.empty:
        raise SystemExit("No observations left after filtering; cannot fit model.")

    model = fit_linear_model(model_df)
    table_df = extract_position_dollars_per_war(model, model_df)
    write_outputs(table_df, model, model_df)

    print(f"Wrote: {OUTPUT_CSV}")
    print(f"Wrote: {OUTPUT_MD}")
    print(f"Wrote: {OUTPUT_MODEL_JSON}")


if __name__ == "__main__":
    main()

