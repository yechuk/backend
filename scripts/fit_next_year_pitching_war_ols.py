from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "pitching.csv"


def main() -> None:
    df = pd.read_csv(DATA_PATH).copy()
    df["Season"] = pd.to_numeric(df["Season"])
    df["Age2"] = df["Age"] ** 2

    df = df.sort_values(["PlayerId", "Season"]).copy()
    df["next_season"] = df.groupby("PlayerId")["Season"].shift(-1)
    df["next_year_WAR"] = df.groupby("PlayerId")["WAR"].shift(-1)

    model_df = df[df["next_season"] == df["Season"] + 1].copy()

    formula = 'next_year_WAR ~ Q("HR/9") + Q("K%") + BB + IP + FIP + GS + G + Age + Age2'
    model = smf.ols(formula=formula, data=model_df).fit()

    print(f"Formula: {formula}")
    print(f"Original rows: {len(df)}")
    print(f"Consecutive-season rows used: {int(model.nobs)}")
    print(model.summary())


if __name__ == "__main__":
    main()
