# ml_models.py

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score, KFold, GridSearchCV, RandomizedSearchCV
from sklearn.svm import SVR
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import logging
import joblib
import pandas as pd
import streamlit as st
from sklearn.feature_selection import SelectKBest, f_regression
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@st.cache_resource
def train_ml_model(
    df,
    target_column,
    model_type="ML (линейная регрессия)",
    poly_degree=2,
    n_estimators=100,
    features=None,
    param_search_method="Нет",
    auto_feature_selection=False
):
    """
    Обучает модель ML (линейная/полиномиальная регрессия/случайный лес/SVR).
    (XGBoost убран)
    """
    try:
        if "Месяц" not in df.columns or target_column not in df.columns:
            raise ValueError("Нет столбцов 'Месяц' и/или целевой переменной.")

        X = df[["Месяц"]].values if features is None else df[features].values
        y = df[target_column].values

        if auto_feature_selection and features is not None and len(features) > 1:
            selector = SelectKBest(score_func=f_regression, k=min(3, len(features)))
            X = selector.fit_transform(X, y)
            selected_features = [features[i] for i in selector.get_support(indices=True)]
            logging.info(f"Автоматический выбор признаков: {selected_features}")

        # Инициализируем модель (без XGBoost)
        if model_type == "ML (линейная регрессия)":
            model = LinearRegression()
        elif model_type == "ML (полиномиальная регрессия)":
            model = make_pipeline(PolynomialFeatures(poly_degree), LinearRegression())
        elif model_type == "ML (случайный лес)":
            model = RandomForestRegressor(random_state=42, n_estimators=n_estimators)
        elif model_type == "ML (SVR)":
            model = SVR()
        else:
            raise ValueError(f"Неподдерживаемый тип модели: {model_type}")

        # Параметрический поиск
        if param_search_method == "GridSearchCV":
            param_grid = get_param_grid(model_type)
            model = GridSearchCV(model, param_grid, cv=5, scoring='neg_mean_squared_error', verbose=0)
        elif param_search_method == "RandomizedSearchCV":
            param_dist = get_param_dist(model_type)
            model = RandomizedSearchCV(
                model, param_dist, n_iter=10, cv=5,
                scoring='neg_mean_squared_error', random_state=42, verbose=0
            )

        model.fit(X, y)
        cv = KFold(n_splits=5, shuffle=True, random_state=42)
        scores = cross_val_score(model, X, y, cv=cv, scoring="neg_mean_squared_error")
        rmse_scores = np.sqrt(-scores)
        logging.info(f"'{model_type}' обучена. Средняя RMSE: {rmse_scores.mean():.2f}")
        return model

    except Exception as e:
        logging.error(f"Ошибка при обучении ML-модели: {e}")
        raise


def get_param_grid(model_type):
    """
    Возвращает словарь сетки параметров для GridSearchCV (без XGBoost).
    """
    if model_type == "ML (случайный лес)":
        return {
            'n_estimators': [100, 200, 300, 400],
            'max_depth': [None, 5, 10, 15],
            'min_samples_split': [2, 5, 10],
            'min_samples_leaf': [1, 2, 4],
        }
    elif model_type == "ML (SVR)":
        return {
            'C': [0.1, 1, 10],
            'kernel': ['linear', 'rbf', 'poly'],
            'gamma': ['scale', 'auto']
        }
    return {}


def get_param_dist(model_type):
    """
    Возвращает словарь распределений параметров для RandomizedSearchCV (без XGBoost).
    """
    if model_type == "ML (случайный лес)":
        return {
            'n_estimators': np.arange(100, 500, 50),
            'max_depth': [None] + list(np.arange(5, 20, 5)),
            'min_samples_split': np.arange(2, 15, 2),
            'min_samples_leaf': np.arange(1, 10, 2),
        }
    elif model_type == "ML (SVR)":
        return {
            'C': np.logspace(-1, 2, 10),
            'kernel': ['linear', 'rbf', 'poly'],
            'gamma': ['scale', 'auto'] + list(np.logspace(-3, 0, 5))
        }
    return {}


def predict_with_model(
    model,
    df,
    future_months,
    features=None,
    auto_feature_selection=False
):
    """
    Делает прогноз с помощью обученной модели. Возвращает (predictions, intervals).
    """
    try:
        if features is None:
            X_future = np.array(future_months).reshape(-1, 1)
        else:
            last_data = df[features].iloc[-1].to_dict()
            future_df = pd.DataFrame({'Месяц': future_months})
            for feature in features:
                if feature != 'Месяц':
                    future_df[feature] = last_data[feature]

            if auto_feature_selection and features is not None and len(features) > 1:
                if "Доходы" not in df.columns:
                    raise ValueError("В DataFrame нет столбца 'Доходы' для вычисления фич.")
                X = df[features].values
                selector = SelectKBest(score_func=f_regression, k=min(3, len(features)))
                selector.fit(X, df["Доходы"].values)
                selected_features = [features[i] for i in selector.get_support(indices=True)]
                X_future = future_df[selected_features].values
            else:
                X_future = future_df[features].values

            if hasattr(model, "predict_interval"):
                predictions, intervals = model.predict_interval(X_future, alpha=0.05)
                return predictions, intervals

            if isinstance(model, type(make_pipeline(PolynomialFeatures(), LinearRegression()))):
                if not isinstance(model[0], PolynomialFeatures):
                    return model.predict(X_future), None
                predictions = model.predict(X_future)
                return predictions, None

        return model.predict(X_future), None

    except Exception as e:
        logging.error(f"Ошибка при прогнозировании: {e}")
        raise


@st.cache_resource
def load_ml_model(
    df,
    target_column,
    model_type="ML (линейная регрессия)",
    poly_degree=2,
    n_estimators=100,
    features=None,
    param_search_method="Нет",
    auto_feature_selection=False,
    uploaded_model_file=None
):
    """
    Загружает или обучает (если нет готовой) ML-модель (без XGBoost).
    """
    try:
        logging_info_message = ("Загрузка модели из загруженного файла."
                                if uploaded_model_file
                                else f"Загрузка/обучение модели: '{model_type}'.")
        logging.info(logging_info_message)

        model_filename = (
            f"ml_model_{model_type}_{poly_degree}_{n_estimators}_"
            f"{'_'.join(features or [])}_{param_search_method}_{auto_feature_selection}.pkl"
        )

        if uploaded_model_file is not None:
            return joblib.load(uploaded_model_file)

        if df is not None:
            if os.path.exists(model_filename):
                logging.info(f"Загрузка модели из файла: {model_filename}")
                model = joblib.load(model_filename)
            else:
                logging.info(f"Обучение новой модели: {model_filename}")
                model = train_ml_model(
                    df,
                    target_column,
                    model_type,
                    poly_degree,
                    n_estimators,
                    features,
                    param_search_method,
                    auto_feature_selection
                )
                save_ml_model(model, model_filename)
            return model
        else:
            logging.warning("Нет данных для обучения ML-модели.")
            return None

    except Exception as e:
        logging.error(f"Ошибка при загрузке/обучении: {e}")
        return None


def save_ml_model(model, filepath="ml_model.pkl"):
    """
    Сохраняет обученную модель на диск.
    """
    try:
        joblib.dump(model, filepath)
        logging.info(f"Модель сохранена в {filepath}.")
    except Exception as e:
        logging.error(f"Ошибка сохранения модели: {e}")


def prepare_ml_data(df, target_column):
    """
    Добавляет признаки Lag_1, Lag_2, Rolling_Mean_3 и Rolling_Mean_5 в DataFrame df.
    """
    try:
        df = df.copy()
        avg = df[target_column].mean() if target_column in df.columns else 0
        df["Lag_1"] = df[target_column].shift(1).fillna(avg)
        df["Lag_2"] = df[target_column].shift(2).fillna(avg)
        df["Rolling_Mean_3"] = df[target_column].rolling(3, min_periods=1).mean()
        df["Rolling_Mean_5"] = df[target_column].rolling(5, min_periods=1).mean()
        logging.info("Данные для ML подготовлены.")
        return df
    except Exception as e:
        logging.error(f"Ошибка при подготовке данных для ML: {e}")
        return df


def calculate_metrics(y_true, y_pred):
    """
    Вычисляет и возвращает метрики качества модели: (RMSE, R2, MAE).
    """
    try:
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        r2 = r2_score(y_true, y_pred)
        mae = mean_absolute_error(y_true, y_pred)
        return rmse, r2, mae
    except Exception as e:
        logging.error(f"Ошибка при расчете метрик: {e}")
        return None, None, None