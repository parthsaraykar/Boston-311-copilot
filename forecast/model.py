"""Monthly demand forecast per department: seasonal-naive baseline vs ETS, chosen by backtest WAPE.

Run: python -m forecast.model   -> contracts/forecast.json, forecast/residuals.json
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

ROOT = Path(__file__).resolve().parents[1]
MONTHLY = ROOT / "data" / "processed" / "monthly.parquet"
CONTRACTS = ROOT / "contracts"
PLAN_YEAR = 2025


def load_series() -> dict[str, pd.Series]:
    m = pd.read_parquet(MONTHLY)
    m["month"] = pd.to_datetime(m["month"])
    out = {}
    for dept, g in m.groupby("dept"):
        s = g.set_index("month")["requests"].astype(float).asfreq("MS")
        out[dept] = s
    return out


def wape(actual, pred) -> float:
    actual, pred = np.asarray(actual, float), np.asarray(pred, float)
    return float(np.abs(actual - pred).sum() / actual.sum())


def seasonal_naive(train: pd.Series, h: int = 12) -> np.ndarray:
    return train.iloc[-12:].to_numpy()[:h]


def ets(train: pd.Series, h: int = 12) -> np.ndarray:
    """Holt-Winters with seasonal factors. With only 12-24 months of history we damp the trend
    and fall back to SARIMA(0,0,0)(0,1,0)+drift style if ETS can't fit."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if len(train) >= 24:
            best = None
            for seasonal in ("add", "mul"):
                try:
                    fit = ExponentialSmoothing(train, trend="add", damped_trend=True, seasonal=seasonal,
                                               seasonal_periods=12, initialization_method="estimated").fit()
                    if best is None or fit.aic < best.aic:
                        best = fit
                except Exception:
                    continue
            if best is not None:
                return np.maximum(best.forecast(h).to_numpy(), 0)
        # one year of history: seasonal shape from last year, level from the last quarter vs a year earlier
        try:
            fit = SARIMAX(train, order=(0, 0, 0), seasonal_order=(0, 1, 0, 12), trend="n").fit(disp=False)
            return np.maximum(fit.forecast(h).to_numpy(), 0)
        except Exception:
            return seasonal_naive(train, h)


def ets_level_adjusted(train: pd.Series, h: int = 12) -> np.ndarray:
    """Seasonal naive scaled by the year-over-year level change of the last 6 months (bounded)."""
    last = train.iloc[-12:].to_numpy()
    if len(train) >= 24:
        ratio = train.iloc[-6:].sum() / train.iloc[-18:-12].sum()
        ratio = float(np.clip(ratio, 0.8, 1.25))
    else:
        ratio = 1.0
    return last[:h] * ratio


MODELS = {"seasonal_naive": seasonal_naive, "ets": ets, "seasonal_naive_trend": ets_level_adjusted}


def backtest(s: pd.Series, train_end: str, test_year: int) -> dict:
    train = s[:train_end]
    test = s[str(test_year)]
    res = {}
    for name, fn in MODELS.items():
        pred = fn(train, len(test))
        res[name] = {"wape": wape(test, pred), "pred": pred.tolist(), "actual": test.tolist()}
    return res


def run() -> dict:
    series = load_series()
    rows, residuals, backtests = [], {}, {}
    for dept, s in series.items():
        # backtest A: train 2023 -> 2024. backtest B: train 2023-24 -> 2025 (the plan year; actuals exist)
        bt_a = backtest(s, "2023-12", 2024)
        bt_b = backtest(s, "2024-12", 2025)
        # choose the model on backtest A only, so the 2025 score is a true holdout
        challengers = {k: v for k, v in bt_a.items() if k != "seasonal_naive"}
        best_challenger = min(challengers, key=lambda k: challengers[k]["wape"])
        chosen = best_challenger if bt_a[best_challenger]["wape"] < bt_a["seasonal_naive"]["wape"] else "seasonal_naive"

        train = s[:"2024-12"]
        mean = MODELS[chosen](train, 12)
        # forecast band from the chosen model's backtest-A errors (relative), at least +-5%
        rel_err = (np.array(bt_a[chosen]["actual"]) - np.array(bt_a[chosen]["pred"])) / np.array(bt_a[chosen]["pred"])
        residuals[dept] = rel_err.tolist()
        lo_q, hi_q = np.quantile(rel_err, [0.1, 0.9])
        lo_q, hi_q = min(lo_q, -0.05), max(hi_q, 0.05)
        backtests[dept] = {
            "chosen": chosen,
            "train_2023_test_2024": {k: round(v["wape"], 4) for k, v in bt_a.items()},
            "train_2023_24_test_2025": {k: round(v["wape"], 4) for k, v in bt_b.items()},
            "series_2025": {"actual": bt_b[chosen]["actual"], "pred": bt_b[chosen]["pred"],
                            "naive": bt_b["seasonal_naive"]["pred"]},
            "series_2024": {"actual": bt_a[chosen]["actual"], "pred": bt_a[chosen]["pred"],
                            "naive": bt_a["seasonal_naive"]["pred"]},
        }
        for i in range(12):
            rows.append({
                "dept": dept, "month": f"{PLAN_YEAR}-{i + 1:02d}",
                "mean": round(float(mean[i]), 1),
                "p10": round(float(mean[i] * (1 + lo_q)), 1),
                "p90": round(float(mean[i] * (1 + hi_q)), 1),
                "model": chosen,
                "backtest_wape": round(bt_b[chosen]["wape"], 4),
                "actual": float(s[f"{PLAN_YEAR}-{i + 1:02d}"].iloc[0]) if f"{PLAN_YEAR}-{i + 1:02d}" in s else None,
            })
    history = [
        {"dept": d, "month": ts.strftime("%Y-%m"), "requests": float(v)}
        for d, s in series.items() for ts, v in s.items()
    ]
    out = {"plan_year": PLAN_YEAR, "forecast": rows, "backtests": backtests, "history": history}
    CONTRACTS.mkdir(exist_ok=True)
    (CONTRACTS / "forecast.json").write_text(json.dumps(out, indent=1))
    (ROOT / "forecast" / "residuals.json").write_text(json.dumps(residuals, indent=1))
    return out


def load_forecast() -> pd.DataFrame:
    return pd.DataFrame(json.loads((CONTRACTS / "forecast.json").read_text())["forecast"])


if __name__ == "__main__":
    out = run()
    for d, b in out["backtests"].items():
        a, c = b["train_2023_test_2024"], b["train_2023_24_test_2025"]
        print(f"{d:22s} chosen={b['chosen']:22s} 2024 WAPE {a}  |  2025 WAPE {c}")
