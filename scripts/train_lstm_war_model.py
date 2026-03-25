import argparse
import json
import pickle
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset


DEFAULT_SEED = 42


@dataclass(frozen=True)
class DatasetConfig:
    csv_path: str
    feature_cols: tuple[str, ...]
    target_col: str = "WAR"


DATASET_CONFIGS = {
    "pitching": DatasetConfig(
        csv_path="data/pitching.csv",
        feature_cols=("HR/9", "K%", "BB", "IP", "FIP", "GS", "G", "Age", "Age2", "WAR"),
    ),
    "batting": DatasetConfig(
        csv_path="data/batting.csv",
        feature_cols=("G", "PA", "HR", "ISO", "BB%", "K%", "wOBA", "wRC+", "SB", "BABIP", "Age", "Age2", "WAR"),
    ),
}


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train LSTM WAR models on batting and/or pitching data.")
    parser.add_argument(
        "--dataset",
        choices=sorted(DATASET_CONFIGS.keys()),
        default=None,
        help="If omitted, the script trains both pitching and batting models in sequence.",
    )
    parser.add_argument("--seq-len", type=int, default=3)
    parser.add_argument("--pred-len", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda", "auto"),
        default="cpu",
        help="Default is cpu for predictable local runs. Use cuda explicitly if you want GPU training.",
    )
    parser.add_argument(
        "--holdout-last-input-season",
        type=int,
        default=2022,
        help="Use windows whose final input season matches this value as the test split.",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Defaults to model_artifacts/lstm_<dataset>.",
    )
    return parser.parse_args()


def to_numeric(df: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")


def load_dataframe(base_dir: Path, dataset_name: str) -> tuple[pd.DataFrame, DatasetConfig]:
    config = DATASET_CONFIGS[dataset_name]
    csv_path = base_dir / config.csv_path
    if not csv_path.exists():
        raise FileNotFoundError(f"Could not find dataset CSV: {csv_path}")

    df = pd.read_csv(csv_path)
    required_columns = {"Season", "PlayerId", "NameASCII", config.target_col, *config.feature_cols}
    missing_columns = [column for column in required_columns if column not in df.columns and column != "Age2"]
    if missing_columns:
        raise ValueError(f"Missing required columns for {dataset_name}: {missing_columns}")

    to_numeric(df, sorted({"Season", "Age", config.target_col, *config.feature_cols}))
    if "Age2" in config.feature_cols:
        if "Age" not in df.columns:
            raise ValueError("Age column is required to derive Age2.")
        df["Age2"] = df["Age"] ** 2

    df["player_name_key"] = df["PlayerId"].astype(str)
    df = df.sort_values(["player_name_key", "Season"]).dropna(
        subset=["player_name_key", "Season", config.target_col, *config.feature_cols]
    )
    return df, config


def build_sequences(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    seq_len: int,
    pred_len: int,
) -> dict[str, np.ndarray]:
    x_list: list[np.ndarray] = []
    y_list: list[np.ndarray] = []
    player_ids: list[str] = []
    player_names: list[str] = []
    input_last_seasons: list[int] = []
    target_start_seasons: list[int] = []

    for player_id, group in df.groupby("player_name_key", sort=False):
        group = group.sort_values("Season")
        if len(group) < seq_len + pred_len:
            continue

        feature_values = group[feature_cols].to_numpy(dtype=np.float32)
        target_values = group[target_col].to_numpy(dtype=np.float32)
        seasons = group["Season"].to_numpy(dtype=np.int32)
        name_ascii = group["NameASCII"].iloc[-1]

        for start_idx in range(len(group) - seq_len - pred_len + 1):
            end_idx = start_idx + seq_len
            target_end_idx = end_idx + pred_len

            x_list.append(feature_values[start_idx:end_idx])
            y_list.append(target_values[end_idx:target_end_idx])
            player_ids.append(player_id)
            player_names.append(name_ascii)
            input_last_seasons.append(int(seasons[end_idx - 1]))
            target_start_seasons.append(int(seasons[end_idx]))

    if not x_list:
        raise ValueError("No training windows were generated from the dataset.")

    return {
        "X": np.array(x_list, dtype=np.float32),
        "y": np.array(y_list, dtype=np.float32),
        "player_ids": np.array(player_ids),
        "player_names": np.array(player_names),
        "input_last_seasons": np.array(input_last_seasons),
        "target_start_seasons": np.array(target_start_seasons),
    }


class BaseballDataset(Dataset):
    def __init__(self, X: np.ndarray, y: np.ndarray) -> None:
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.X)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.X[idx], self.y[idx]


class LSTMRegressor(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int) -> None:
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.lstm(x)
        return self.fc(hidden[-1])


def scale_features(X_train: np.ndarray, X_test: np.ndarray) -> tuple[np.ndarray, np.ndarray, StandardScaler]:
    scaler = StandardScaler()
    n_train, train_steps, feature_count = X_train.shape
    n_test = X_test.shape[0]

    X_train_flat = X_train.reshape(-1, feature_count)
    X_test_flat = X_test.reshape(-1, feature_count)

    scaler.fit(X_train_flat)
    X_train_scaled = scaler.transform(X_train_flat).reshape(n_train, train_steps, feature_count)
    X_test_scaled = scaler.transform(X_test_flat).reshape(n_test, train_steps, feature_count)
    return X_train_scaled, X_test_scaled, scaler


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> float:
    model.train()
    total_loss = 0.0
    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device)

        optimizer.zero_grad()
        predictions = model(X_batch)
        loss = criterion(predictions, y_batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total_loss += loss.item()

    return total_loss / max(len(loader), 1)


def predict(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[np.ndarray, np.ndarray]:
    preds: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for X_batch, y_batch in loader:
            batch_preds = model(X_batch.to(device))
            preds.append(batch_preds.cpu().numpy())
            targets.append(y_batch.numpy())

    return np.concatenate(preds, axis=0), np.concatenate(targets, axis=0)


def regression_metrics(targets: np.ndarray, preds: np.ndarray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(targets.reshape(-1), preds.reshape(-1))),
        "rmse": float(np.sqrt(mean_squared_error(targets.reshape(-1), preds.reshape(-1)))),
        "r2": float(r2_score(targets.reshape(-1), preds.reshape(-1))),
    }


def horizon_metrics(targets: np.ndarray, preds: np.ndarray, start_year: int) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for horizon_idx in range(targets.shape[1]):
        year = start_year + horizon_idx
        metrics[str(year)] = {
            "mae": float(mean_absolute_error(targets[:, horizon_idx], preds[:, horizon_idx])),
            "rmse": float(np.sqrt(mean_squared_error(targets[:, horizon_idx], preds[:, horizon_idx]))),
            "r2": float(r2_score(targets[:, horizon_idx], preds[:, horizon_idx])),
        }
    return metrics


def save_artifacts(
    output_dir: Path,
    model: nn.Module,
    scaler: StandardScaler,
    args: argparse.Namespace,
    metrics: dict[str, object],
    predictions_df: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    torch.save(
        {
            "state_dict": model.state_dict(),
            "dataset": args.dataset,
            "seq_len": args.seq_len,
            "pred_len": args.pred_len,
            "hidden_dim": args.hidden_dim,
        },
        output_dir / "model.pt",
    )

    with (output_dir / "scaler.pkl").open("wb") as handle:
        pickle.dump(scaler, handle)

    with (output_dir / "metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    predictions_df.to_csv(output_dir / "predictions.csv", index=False)


def train_dataset(args: argparse.Namespace, dataset_name: str) -> dict[str, object]:
    set_seed(args.seed)

    base_dir = Path(args.base_dir).resolve()
    if args.output_dir:
        base_output_dir = Path(args.output_dir).resolve()
        output_dir = base_output_dir if args.dataset else base_output_dir / dataset_name
    else:
        output_dir = base_dir / "model_artifacts" / f"lstm_{dataset_name}"

    df, config = load_dataframe(base_dir, dataset_name)
    sequences = build_sequences(
        df=df,
        feature_cols=list(config.feature_cols),
        target_col=config.target_col,
        seq_len=args.seq_len,
        pred_len=args.pred_len,
    )

    train_idx = sequences["input_last_seasons"] < args.holdout_last_input_season
    test_idx = (
        (sequences["input_last_seasons"] == args.holdout_last_input_season)
        & (sequences["target_start_seasons"] == args.holdout_last_input_season + 1)
    )

    if not train_idx.any():
        raise ValueError("Training split is empty. Adjust --holdout-last-input-season or sequence lengths.")
    if not test_idx.any():
        raise ValueError("Test split is empty. Adjust --holdout-last-input-season or sequence lengths.")

    X_train = sequences["X"][train_idx]
    y_train = sequences["y"][train_idx]
    X_test = sequences["X"][test_idx]
    y_test = sequences["y"][test_idx]

    X_train, X_test, scaler = scale_features(X_train, X_test)

    train_loader = DataLoader(BaseballDataset(X_train, y_train), batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(BaseballDataset(X_test, y_test), batch_size=args.batch_size, shuffle=False)

    if args.device == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    elif args.device == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA was requested but is not available.")
        device_name = "cuda"
    else:
        device_name = "cpu"

    device = torch.device(device_name)
    model = LSTMRegressor(
        input_dim=X_train.shape[2],
        hidden_dim=args.hidden_dim,
        output_dim=args.pred_len,
    ).to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)

    for epoch in range(args.epochs):
        loss = run_epoch(model, train_loader, criterion, optimizer, device)
        print(f"Epoch {epoch + 1}/{args.epochs} - loss: {loss:.4f}")

    train_preds, train_targets = predict(model, train_loader, device)
    test_preds, test_targets = predict(model, test_loader, device)

    test_start_year = int(sequences["target_start_seasons"][test_idx][0])
    metrics = {
        "dataset": dataset_name,
        "train": regression_metrics(train_targets, train_preds),
        "test": regression_metrics(test_targets, test_preds),
        "test_by_year": horizon_metrics(test_targets, test_preds, test_start_year),
    }

    prediction_columns: dict[str, np.ndarray] = {
        "player_id": sequences["player_ids"][test_idx],
        "player_name_key": sequences["player_names"][test_idx],
    }
    for offset in range(args.pred_len):
        target_year = test_start_year + offset
        prediction_columns[f"pred_{target_year}"] = test_preds[:, offset]
        prediction_columns[f"real_{target_year}"] = test_targets[:, offset]
        prediction_columns[f"error_{target_year}"] = test_preds[:, offset] - test_targets[:, offset]

    predictions_df = pd.DataFrame(prediction_columns)
    save_artifacts(output_dir, model, scaler, args, metrics, predictions_df)

    print(json.dumps(metrics, indent=2))
    print(f"Saved artifacts to {output_dir}")
    return metrics


def main() -> None:
    args = parse_args()
    dataset_names = [args.dataset] if args.dataset else list(DATASET_CONFIGS.keys())

    all_metrics: dict[str, object] = {}
    for dataset_name in dataset_names:
        print(f"\n===== Training {dataset_name} model =====")
        all_metrics[dataset_name] = train_dataset(args, dataset_name)

    if len(dataset_names) > 1:
        print("\n===== Combined Summary =====")
        print(json.dumps(all_metrics, indent=2))


if __name__ == "__main__":
    main()
