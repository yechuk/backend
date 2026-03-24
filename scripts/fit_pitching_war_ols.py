from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "pitching.csv"


def main() -> None:
    df = pd.read_csv(DATA_PATH).copy()
    df["Age2"] = df["Age"] ** 2

    formula = 'WAR ~ Q("HR/9") + Q("K%") + BB + IP + FIP + GS + G + Age + Age2'
    model = smf.ols(formula=formula, data=df).fit()

    print(f"Formula: {formula}")
    print(f"Rows used: {int(model.nobs)}")
    print(model.summary())


if __name__ == "__main__":
    main()
