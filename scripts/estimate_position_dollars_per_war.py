#!/usr/bin/env python
"""
Estimate $/WAR by position from the consolidated free-agent workbook and a
player-season WAR file.

This script:
- loads the consolidated free-agent data from
  data/MLB-Free Agency 1991-2026_consolidated.xlsx
- loads a WAR table (one row per player-season)
- constructs WAR_at_signing features (previous 3 seasons by default)
- fits a Swartz-style linear model with optional 2-way/3-way interaction specs:

    AAV_real = β₀ + β₁·WAR_at_signing + f(Age) + γ_Year + δ_Position
               + Σ_p θ_p·(WAR_at_signing × 1[Position=p]) + ε

  The default keeps the original baseline formula. Use --interaction-spec two_way
  or --interaction-spec three_way to test richer linear interaction terms, and
  --compare-interactions to export baseline vs 2-way vs 3-way experiment metrics.

- exports:
  - data/position_dollars_per_war.csv  (Position, dollars_per_war, n_obs, etc.)
  - data/position_dollars_per_war.md   (short markdown summary)

WAR input format (CSV by default):
- Player: player name matching the consolidated sheet
- Year: season year (int)
- WAR: wins above replacement for that season (float)

Usage examples (from project root):
    python scripts/estimate_position_dollars_per_war.py
    python scripts/estimate_position_dollars_per_war.py --interaction-spec three_way --compare-interactions
    python scripts/estimate_position_dollars_per_war.py \\
        --fa-path data/MLB-Free Agency 1991-2026_consolidated.xlsx \\
        --war-path data/war/player_year_war.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from patsy import dmatrices


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FA_PATH = PROJECT_ROOT / "data" / "MLB-Free Agency 1991-2026_consolidated.xlsx"
DEFAULT_WAR_PATH = PROJECT_ROOT / "data" / "war" / "player_year_war.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "position_dollars_per_war.csv"
OUTPUT_MD = PROJECT_ROOT / "data" / "position_dollars_per_war.md"
OUTPUT_MODEL_JSON = PROJECT_ROOT / "data" / "position_dollars_per_war_model.json"
OUTPUT_COMPARISON_CSV = PROJECT_ROOT / "data" / "aav_linear_interaction_experiment.csv"
OUTPUT_COMPARISON_JSON = PROJECT_ROOT / "data" / "aav_linear_interaction_experiment.json"

LINEAR_MODEL_FORMULAS = {
    "baseline": (
        "AAV_real ~ WAR_prev3 + Age_c + Age_c2 + C(Year) + C(Position)"
        " + WAR_prev3:C(Position)"
    ),
    "two_way": (
        "AAV_real ~ WAR_prev3 + Age_c + Age_c2 + C(Year) + C(Position)"
        " + WAR_prev3:C(Position)"
        " + WAR_prev3:Age_c"
        " + WAR_prev3:Year_c"
        " + Age_c:C(Position)"
    ),
    "three_way": (
        "AAV_real ~ WAR_prev3 + Age_c + Age_c2 + C(Year) + C(Position)"
        " + WAR_prev3:C(Position)"
        " + WAR_prev3:Age_c"
        " + WAR_prev3:Year_c"
        " + Age_c:C(Position)"
        " + WAR_prev3:Age_c:C(Position)"
        " + WAR_prev3:Year_c:C(Position)"
    ),
}


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
    df["Age"] = df["Age"].astype(float)
    df["Age_c"] = df["Age"] - df["Age"].mean()
    df["Age_c2"] = df["Age_c"] ** 2
    df["Year_c"] = df["Year"].astype(float) - df["Year"].astype(float).mean()
    df["AAV_real"] = df["AAV"].astype(float)

    # Keep only essential columns for modeling.
    keep_cols = [
        "Year",
        "Player",
        "Position",
        "Age",
        "Age_c",
        "Age_c2",
        "Year_c",
        "AAV_real",
        "WAR_prev3",
    ]
    model_df = df[keep_cols].copy()
    model_df = model_df.dropna(subset=["AAV_real", "WAR_prev3", "Age"])
    return model_df


def _formula_for_spec(interaction_spec: str) -> str:
    try:
        return LINEAR_MODEL_FORMULAS[interaction_spec]
    except KeyError as exc:
        valid = ", ".join(sorted(LINEAR_MODEL_FORMULAS))
        raise ValueError(f"Unknown interaction spec {interaction_spec!r}; choose one of: {valid}") from exc


def fit_linear_model(model_df: pd.DataFrame, interaction_spec: str = "baseline"):
    """Fit the Swartz-style linear model with position interactions.

    baseline:
        AAV_real ~ WAR_prev3 + Age_c + Age_c^2 + C(Year) + C(Position)
                   + WAR_prev3:C(Position)

    two_way:
        baseline plus WAR_prev3:Age_c, WAR_prev3:Year_c, Age_c:C(Position)

    three_way:
        two_way plus WAR_prev3:Age_c:C(Position), WAR_prev3:Year_c:C(Position)
    """
    # Ensure types are sensible for patsy/statsmodels.
    model_df = model_df.copy()
    model_df["Year"] = model_df["Year"].astype(int)
    model_df["Position"] = model_df["Position"].astype(str)

    formula = _formula_for_spec(interaction_spec)
    model = smf.ols(formula=formula, data=model_df).fit()
    return model


def _regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    residuals = y_true - y_pred
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    return {
        "rmse": float(np.sqrt(np.mean(residuals**2))),
        "mae": float(np.mean(np.abs(residuals))),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
    }


def _fold_indices(n_obs: int, n_splits: int, seed: int) -> list[np.ndarray]:
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2.")
    if n_obs < n_splits:
        raise ValueError(f"Cannot create {n_splits} folds from {n_obs} observations.")
    indices = np.arange(n_obs)
    rng = np.random.default_rng(seed)
    rng.shuffle(indices)
    return [fold for fold in np.array_split(indices, n_splits) if len(fold) > 0]


def evaluate_interaction_specs(
    model_df: pd.DataFrame,
    *,
    n_splits: int = 5,
    seed: int = 42,
) -> pd.DataFrame:
    """Compare baseline, 2-way, and 3-way OLS formulas on the same data.

    The CV design matrix is built once per formula so every fold uses the same
    dummy/interaction columns. This avoids failures when a category appears in a
    validation fold but not in that fold's training rows.
    """
    records = []
    folds = _fold_indices(len(model_df), n_splits=n_splits, seed=seed)
    all_indices = np.arange(len(model_df))

    for spec, formula in LINEAR_MODEL_FORMULAS.items():
        full_model = fit_linear_model(model_df, interaction_spec=spec)
        y, x = dmatrices(formula, data=model_df, return_type="dataframe")
        y_array = np.asarray(y).reshape(-1)
        x_array = np.asarray(x)

        fold_metrics = []
        for test_idx in folds:
            train_idx = np.setdiff1d(all_indices, test_idx, assume_unique=False)
            fold_model = sm.OLS(y_array[train_idx], x_array[train_idx]).fit()
            y_pred = fold_model.predict(x_array[test_idx])
            fold_metrics.append(_regression_metrics(y_array[test_idx], y_pred))

        mean_metrics = {
            key: float(np.mean([metrics[key] for metrics in fold_metrics]))
            for key in ("rmse", "mae", "r2")
        }
        records.append(
            {
                "interaction_spec": spec,
                "n_obs": int(len(y_array)),
                "n_params": int(x.shape[1]),
                "cv_folds": int(n_splits),
                "cv_rmse": mean_metrics["rmse"],
                "cv_mae": mean_metrics["mae"],
                "cv_r2": mean_metrics["r2"],
                "in_sample_adj_r2": float(full_model.rsquared_adj),
                "aic": float(full_model.aic),
                "bic": float(full_model.bic),
                "formula": formula,
            }
        )

    return pd.DataFrame.from_records(records)


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
    interaction_spec: str = "baseline",
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
    lines.append(f"- Linear interaction spec: `{interaction_spec}`")
    lines.append("- $/WAR slope context: centered average age and centered average contract year")
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
        "interaction_spec": interaction_spec,
        "formula": _formula_for_spec(interaction_spec),
        "war_slope_context": "Age_c=0 and Year_c=0, i.e. sample-average age and contract year.",
        "age_center": float(model_df["Age"].mean()) if not model_df.empty else None,
        "year_center": float(model_df["Year"].mean()) if not model_df.empty else None,
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


def write_interaction_comparison(
    comparison_df: pd.DataFrame,
    *,
    csv_path: Path = OUTPUT_COMPARISON_CSV,
    json_path: Path = OUTPUT_COMPARISON_JSON,
) -> None:
    """Persist OLS interaction-spec experiment metrics."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_df.to_csv(csv_path, index=False)
    payload = {
        "metric_direction": {
            "cv_rmse": "lower_is_better",
            "cv_mae": "lower_is_better",
            "cv_r2": "higher_is_better",
            "in_sample_adj_r2": "higher_is_better",
            "aic": "lower_is_better",
            "bic": "lower_is_better",
        },
        "rows": comparison_df.to_dict(orient="records"),
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
    parser.add_argument(
        "--interaction-spec",
        choices=sorted(LINEAR_MODEL_FORMULAS),
        default="baseline",
        help="Linear formula interaction depth to fit for the exported $/WAR table.",
    )
    parser.add_argument(
        "--compare-interactions",
        action="store_true",
        help="Export baseline vs 2-way vs 3-way OLS interaction experiment metrics.",
    )
    parser.add_argument(
        "--cv-folds",
        type=int,
        default=5,
        help="Number of folds for --compare-interactions.",
    )
    parser.add_argument(
        "--cv-seed",
        type=int,
        default=42,
        help="Random seed for --compare-interactions fold assignment.",
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

    model = fit_linear_model(model_df, interaction_spec=args.interaction_spec)
    table_df = extract_position_dollars_per_war(model, model_df)
    write_outputs(table_df, model, model_df, interaction_spec=args.interaction_spec)

    print(f"Wrote: {OUTPUT_CSV}")
    print(f"Wrote: {OUTPUT_MD}")
    print(f"Wrote: {OUTPUT_MODEL_JSON}")

    if args.compare_interactions:
        comparison_df = evaluate_interaction_specs(
            model_df,
            n_splits=args.cv_folds,
            seed=args.cv_seed,
        )
        write_interaction_comparison(comparison_df)
        print(f"Wrote: {OUTPUT_COMPARISON_CSV}")
        print(f"Wrote: {OUTPUT_COMPARISON_JSON}")


if __name__ == "__main__":
    main()

