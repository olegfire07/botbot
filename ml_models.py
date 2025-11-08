"""Machine learning helpers for the auction router speed model."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import RandomizedSearchCV, train_test_split

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBRegressor  # type: ignore
except Exception:  # pragma: no cover
    XGBRegressor = None

try:
    from lightgbm import LGBMRegressor  # type: ignore
except Exception:  # pragma: no cover
    LGBMRegressor = None

try:
    from catboost import CatBoostRegressor  # type: ignore
except Exception:  # pragma: no cover
    CatBoostRegressor = None

try:
    import shap  # type: ignore
except Exception:  # pragma: no cover
    shap = None

FEATURE_NAMES = [
    "bias",
    "log_price",
    "log_velocity",
    "log_inventory",
    "bucket_code",
    "seasonal_factor",
    "quarterly_factor",
    "weekly_factor",
    "price_to_median_ratio",
    "inventory_turnover",
    "log_sample_size",
    "stock_pressure",
    "velocity_pressure",
    "price_per_unit",
    "volatility",
]


@dataclass
class SpeedModelArtifact:
    models: Dict[str, Any] = field(default_factory=dict)
    feature_names: List[str] = field(default_factory=lambda: FEATURE_NAMES.copy())
    ensemble_weights: Dict[str, float] = field(default_factory=dict)
    training_summary: Dict[str, Dict[str, float]] = field(default_factory=dict)
    best_model_name: Optional[str] = None
    shap_background: Optional[np.ndarray] = None
    shap_model_name: Optional[str] = None
    shap_explainer: Any = None
    history_lookup: Dict[Tuple[str, str, str], Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "models": self.models,
            "feature_names": self.feature_names,
            "ensemble_weights": self.ensemble_weights,
            "training_summary": self.training_summary,
            "best_model_name": self.best_model_name,
            "shap_background": self.shap_background,
            "shap_model_name": self.shap_model_name,
            "shap_explainer": self.shap_explainer,
            "history_lookup": self.history_lookup,
        }


def _safe_value(val: float, default: float = 0.0) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    return float(val)


def _weekly_factor(dow: float) -> float:
    return np.sin(2 * np.pi * dow / 7.0)


def _quarterly_factor(quarter: float) -> float:
    return np.cos(2 * np.pi * quarter / 4.0)


def _seasonal_factor(month: float) -> float:
    return np.sin(2 * np.pi * month / 12.0)


def _build_feature_vector(
    price: float,
    velocity: float,
    inventory: float,
    bucket_code: float,
    month: float,
    dow: float,
    quarter: float,
    sample_size: float,
    price_to_median_ratio: float,
    inventory_turnover: float,
    volatility: float,
) -> np.ndarray:
    safe_price = max(price, 1e-6)
    safe_velocity = max(velocity, 1e-6)
    safe_inventory = max(inventory + 0.5, 1e-6)
    safe_sample = max(sample_size, 1.0)

    vector = np.array(
        [
            1.0,
            np.log1p(safe_price),
            np.log1p(safe_velocity),
            np.log1p(safe_inventory),
            float(bucket_code),
            _seasonal_factor(month),
            _quarterly_factor(quarter),
            _weekly_factor(dow),
            price_to_median_ratio,
            inventory_turnover,
            np.log1p(safe_sample),
            safe_inventory / safe_sample,
            safe_velocity * safe_inventory,
            safe_price / (safe_inventory + 0.5),
            np.log1p(max(volatility, 0.0)),
        ],
        dtype=float,
    )
    return vector


def _candidate_models() -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {
        "rf": {
            "estimator": RandomForestRegressor(random_state=42, n_jobs=-1),
            "param_distributions": {
                "n_estimators": [100, 200, 300],
                "max_depth": [4, 6, 8, None],
                "min_samples_split": [2, 4, 6, 8],
                "min_samples_leaf": [1, 2, 4],
            },
            "n_iter": 12,
        },
        "gbr": {
            "estimator": GradientBoostingRegressor(random_state=42),
            "param_distributions": {
                "n_estimators": [150, 250, 350],
                "learning_rate": [0.03, 0.05, 0.08, 0.1],
                "max_depth": [2, 3, 4],
                "subsample": [0.7, 0.85, 1.0],
            },
            "n_iter": 12,
        },
    }

    if XGBRegressor is not None:
        registry["xgb"] = {
            "estimator": XGBRegressor(
                objective="reg:squarederror",
                random_state=42,
                verbosity=0,
                tree_method="hist",
            ),
            "param_distributions": {
                "n_estimators": [200, 400, 600],
                "max_depth": [3, 4, 5],
                "learning_rate": [0.03, 0.05, 0.08],
                "subsample": [0.7, 0.85, 1.0],
                "colsample_bytree": [0.7, 0.85, 1.0],
            },
            "n_iter": 15,
        }

    if LGBMRegressor is not None:
        registry["lgbm"] = {
            "estimator": LGBMRegressor(random_state=42, verbose=-1),
            "param_distributions": {
                "n_estimators": [200, 400, 600],
                "learning_rate": [0.03, 0.05, 0.08],
                "num_leaves": [31, 63, 95],
                "subsample": [0.7, 0.85, 1.0],
                "colsample_bytree": [0.7, 0.85, 1.0],
            },
            "n_iter": 15,
        }

    if CatBoostRegressor is not None:
        registry["catboost"] = {
            "estimator": CatBoostRegressor(
                random_state=42,
                depth=6,
                verbose=False,
                loss_function="MAE",
            ),
            "param_distributions": {
                "learning_rate": [0.03, 0.05, 0.08],
                "depth": [4, 6, 8],
                "l2_leaf_reg": [1.0, 3.0, 5.0, 7.0],
                "bagging_temperature": [0.3, 0.7, 1.0],
            },
            "n_iter": 12,
        }

    return registry


def _train_single_model(
    name: str,
    config: Dict[str, Any],
    X_train: np.ndarray,
    y_train: np.ndarray,
) -> Tuple[Any, Dict[str, float]]:
    estimator = clone(config["estimator"])
    params = config.get("param_distributions")
    summary: Dict[str, float] = {}

    cv = min(4, len(y_train))
    if cv >= 2 and params:
        try:
            search = RandomizedSearchCV(
                estimator,
                params,
                n_iter=config.get("n_iter", 10),
                scoring="neg_mean_absolute_error",
                n_jobs=-1,
                cv=cv,
                random_state=42,
            )
            search.fit(X_train, y_train)
            estimator = search.best_estimator_
            summary["best_mae_cv"] = abs(search.best_score_)
            summary["best_params_count"] = float(len(search.best_params_))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Tuning failed for %s: %s", name, exc)
            estimator.fit(X_train, y_train)
    else:
        if cv < 2:
            logger.info("Not enough data for CV, training default %s", name)
        estimator.fit(X_train, y_train)

    return estimator, summary


def _prepare_training_frame(
    sales: pd.DataFrame,
    vel_bcb_key: Dict[Tuple[str, str, str], float],
    vel_bc_key: Dict[Tuple[str, str], float],
    stock_key: Dict[Tuple[str, str], float],
    price_bucket_map: Dict[str, int],
) -> Tuple[np.ndarray, np.ndarray, Dict[Tuple[str, str, str], Dict[str, float]]]:
    required_cols = {"days_real", "branch", "category", "price_bucket"}
    if not required_cols.issubset(sales.columns):
        logger.warning("Training skipped: missing columns %s", required_cols - set(sales.columns))
        return np.empty((0, len(FEATURE_NAMES))), np.array([]), {}

    train = sales.dropna(subset=["days_real", "branch", "category"]).copy()
    if train.empty:
        return np.empty((0, len(FEATURE_NAMES))), np.array([]), {}

    if "_date" in train.columns:
        train["_month"] = train["_date"].dt.month.fillna(6)
        train["_dow"] = train["_date"].dt.dayofweek.fillna(3)
        train["_quarter"] = train["_date"].dt.quarter.fillna(2)
        train["_date_ord"] = train["_date"].map(lambda x: x.toordinal() if pd.notna(x) else np.nan)
    else:
        train["_month"] = 6
        train["_dow"] = 3
        train["_quarter"] = 2
        train["_date_ord"] = np.nan

    grouped = (
        train.groupby(["branch", "category", "price_bucket"], dropna=False)
        .agg(
            median_days=("days_real", "median"),
            avg_price=("_sale_price", "mean"),
            median_price=("_sale_price", "median"),
            cnt=("days_real", "count"),
            month=("_month", "median"),
            dow=("_dow", "median"),
            quarter=("_quarter", "median"),
            volatility=("days_real", "std"),
            recent_ord=("_date_ord", "max"),
        )
        .reset_index()
    )

    feature_rows: List[np.ndarray] = []
    targets: List[float] = []
    history_lookup: Dict[Tuple[str, str, str], Dict[str, float]] = {}

    current_ord = pd.Timestamp.now().toordinal()

    for row in grouped.itertuples(index=False):
        if row.cnt < 3 or not np.isfinite(row.median_days):
            continue

        branch = row.branch
        category = row.category
        bucket_str = str(row.price_bucket)
        bucket_code = price_bucket_map.get(bucket_str, 0)

        velocity = vel_bcb_key.get((branch, category, bucket_str))
        if velocity is None:
            velocity = vel_bc_key.get((branch, category))
        if velocity is None or velocity <= 0:
            continue

        inventory = stock_key.get((branch, category), 0.0)
        price = _safe_value(row.avg_price, 0.0)
        median_price = _safe_value(row.median_price, price)
        sample_size = float(row.cnt)
        month = _safe_value(row.month, 6.0)
        dow = _safe_value(row.dow, 3.0)
        quarter = _safe_value(row.quarter, 2.0)
        volatility = _safe_value(row.volatility, 0.0)
        recent_ord = _safe_value(row.recent_ord, current_ord - 30)
        price_ratio = price / (median_price + 1e-6) if median_price > 0 else 1.0
        inventory_turnover = velocity / (inventory + 1.0) if inventory > 0 else velocity

        feature_vector = _build_feature_vector(
            price=price,
            velocity=velocity,
            inventory=inventory,
            bucket_code=bucket_code,
            month=month,
            dow=dow,
            quarter=quarter,
            sample_size=sample_size,
            price_to_median_ratio=price_ratio,
            inventory_turnover=inventory_turnover,
            volatility=volatility,
        )

        feature_rows.append(feature_vector)
        targets.append(float(row.median_days))

        recent_days = max(current_ord - recent_ord, 1.0)
        history_lookup[(branch, category, bucket_str)] = {
            "history_cnt": sample_size,
            "volatility": volatility,
            "recent_days": recent_days,
        }
        generic_key = (branch, category, "__all__")
        if (
            generic_key not in history_lookup
            or history_lookup[generic_key]["history_cnt"] < sample_size
        ):
            history_lookup[generic_key] = {
                "history_cnt": sample_size,
                "volatility": volatility,
                "recent_days": recent_days,
            }

    if not feature_rows:
        return np.empty((0, len(FEATURE_NAMES))), np.array([]), {}

    X = np.vstack(feature_rows)
    y = np.array(targets, dtype=float)
    return X, y, history_lookup


def fit_speed_model(
    sales: pd.DataFrame,
    vel_bcb_key: Dict[Tuple[str, str, str], float],
    vel_bc_key: Dict[Tuple[str, str], float],
    stock_key: Dict[Tuple[str, str], float],
    price_bucket_map: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    X, y, history_lookup = _prepare_training_frame(
        sales, vel_bcb_key, vel_bc_key, stock_key, price_bucket_map
    )

    if y.size < 5 or X.size == 0:
        logger.info("Not enough samples to train speed model (n=%s)", y.size)
        return None

    if y.size < 10:
        X_train, X_val, y_train, y_val = X, X, y, y
    else:
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

    artifact = SpeedModelArtifact()
    artifact.history_lookup = history_lookup

    candidate_models = _candidate_models()
    for name, config in candidate_models.items():
        try:
            estimator, tuning_info = _train_single_model(name, config, X_train, y_train)
        except Exception as exc:  # pragma: no cover
            logger.warning("Model %s failed during training: %s", name, exc)
            continue

        try:
            y_pred_train = estimator.predict(X_train)
        except Exception as exc:  # pragma: no cover
            logger.debug("Prediction failed on train for %s: %s", name, exc)
            continue

        metrics: Dict[str, float] = dict(tuning_info)
        metrics["mae_train"] = float(mean_absolute_error(y_train, y_pred_train))
        try:
            metrics["r2_train"] = float(r2_score(y_train, y_pred_train))
        except Exception:
            metrics["r2_train"] = float("nan")

        if X_val is X_train:
            metrics["mae_val"] = metrics["mae_train"]
            metrics["r2_val"] = metrics["r2_train"]
        else:
            try:
                y_pred_val = estimator.predict(X_val)
                metrics["mae_val"] = float(mean_absolute_error(y_val, y_pred_val))
                metrics["r2_val"] = float(r2_score(y_val, y_pred_val))
            except Exception as exc:  # pragma: no cover
                logger.debug("Validation prediction failed for %s: %s", name, exc)
                metrics["mae_val"] = metrics["mae_train"]
                metrics["r2_val"] = metrics["r2_train"]

        artifact.models[name] = estimator
        artifact.training_summary[name] = metrics

    if not artifact.models:
        logger.info("No models were successfully trained for speed estimation")
        return None

    weights: Dict[str, float] = {}
    for name, metrics in artifact.training_summary.items():
        mae = metrics.get("mae_val") or metrics.get("mae_train") or 1.0
        weight = 1.0 / (mae + 1e-6)
        weights[name] = weight

    weight_sum = sum(weights.values())
    if weight_sum == 0:
        artifact.ensemble_weights = {name: 1.0 / len(weights) for name in weights}
    else:
        artifact.ensemble_weights = {
            name: weight / weight_sum for name, weight in weights.items()
        }

    artifact.best_model_name = min(
        artifact.training_summary.keys(),
        key=lambda n: artifact.training_summary[n].get("mae_val", float("inf")),
    )

    if shap is not None and artifact.best_model_name and X_train.size > 0:
        sample_size = min(256, len(X_train))
        indices = np.random.choice(len(X_train), size=sample_size, replace=False)
        artifact.shap_background = X_train[indices]
        artifact.shap_model_name = artifact.best_model_name

    return artifact.to_dict()


def get_history_context(
    model: Optional[Dict[str, Any]],
    branch: Optional[str],
    category: Optional[str],
    bucket: Optional[str],
) -> Dict[str, float]:
    if not model:
        return {}
    lookup = model.get("history_lookup", {})
    if not lookup:
        return {}
    key_specific = (branch, category, str(bucket))
    generic_key = (branch, category, "__all__")
    context = lookup.get(key_specific) or lookup.get(generic_key) or {}
    return dict(context)


def _build_prediction_features(
    price: float,
    vel: float,
    inv: float,
    bucket_code: int,
    med_price: Optional[float],
    current_date: Optional[pd.Timestamp],
    context: Optional[Dict[str, Any]],
) -> Tuple[np.ndarray, Dict[str, float]]:
    context = context or {}
    timestamp = current_date or pd.Timestamp.now()
    month = context.get("month") or float(timestamp.month)
    dow = context.get("dow") or float(timestamp.dayofweek)
    quarter = context.get("quarter") or float(timestamp.quarter)
    sample_size = context.get("history_cnt", 1.0)
    volatility = context.get("volatility", 0.0)
    price_ratio = (
        price / ((med_price or 0.0) + 1e-6) if med_price and med_price > 0 else 1.0
    )
    inventory_turnover = vel / (inv + 1.0) if inv > 0 else vel

    vector = _build_feature_vector(
        price=price,
        velocity=vel,
        inventory=inv,
        bucket_code=float(bucket_code),
        month=month,
        dow=dow,
        quarter=quarter,
        sample_size=sample_size,
        price_to_median_ratio=price_ratio,
        inventory_turnover=inventory_turnover,
        volatility=volatility,
    )
    feature_meta = {
        "month": month,
        "dow": dow,
        "quarter": quarter,
        "sample_size": sample_size,
        "volatility": volatility,
        "price_ratio": price_ratio,
        "inventory_turnover": inventory_turnover,
    }
    return vector, feature_meta


def predict_speed(
    model: Optional[Dict[str, Any]],
    price: float,
    vel: float,
    inv: float,
    bucket_code: int,
    med_price: float = None,
    current_date: pd.Timestamp = None,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    if not model or "models" not in model:
        return None

    vector, meta = _build_prediction_features(
        price, vel, inv, bucket_code, med_price, current_date, context
    )
    if context is not None:
        context["feature_vector"] = vector
        context["feature_meta"] = meta

    predictions: List[Tuple[float, float]] = []
    models = model.get("models", {})
    weights = model.get("ensemble_weights", {})

    for name, estimator in models.items():
        try:
            pred = float(estimator.predict(vector.reshape(1, -1))[0])
            if not np.isfinite(pred) or pred <= 0:
                continue
        except Exception:
            continue
        weight = weights.get(name, 1.0)
        predictions.append((pred, weight))

    if not predictions:
        return None

    weight_sum = sum(w for _, w in predictions)
    if weight_sum <= 0:
        return float(np.mean([p for p, _ in predictions]))

    ensemble_pred = sum(p * w for p, w in predictions) / weight_sum
    return float(max(ensemble_pred, 0.5))


def explain_speed_prediction(
    model: Optional[Dict[str, Any]],
    feature_vector: np.ndarray,
    top_n: int = 5,
) -> List[Dict[str, float]]:
    if shap is None or not model:
        return []
    best_name = model.get("shap_model_name")
    if not best_name:
        return []
    estimator = model.get("models", {}).get(best_name)
    background = model.get("shap_background")
    if estimator is None or background is None or background.size == 0:
        return []

    if model.get("shap_explainer") is None:
        try:
            explainer = shap.Explainer(estimator, background)
            model["shap_explainer"] = explainer
        except Exception as exc:  # pragma: no cover
            logger.debug("Failed to initialise SHAP explainer: %s", exc)
            return []

    explainer = model["shap_explainer"]
    try:
        shap_values = explainer(feature_vector.reshape(1, -1))
    except Exception as exc:  # pragma: no cover
        logger.debug("Failed to compute SHAP values: %s", exc)
        return []

    contributions = np.asarray(shap_values.values)[0]
    feature_names = model.get("feature_names", FEATURE_NAMES)

    abs_contrib = np.abs(contributions)
    top_idx = np.argsort(abs_contrib)[::-1][:top_n]

    explanation = []
    for idx in top_idx:
        if idx >= len(feature_names):
            continue
        explanation.append(
            {
                "feature": feature_names[idx],
                "contribution": float(contributions[idx]),
            }
        )
    return explanation
