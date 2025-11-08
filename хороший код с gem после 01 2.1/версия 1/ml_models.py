# ml_models.py

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score, KFold
import logging
import joblib
import pandas as pd
import streamlit as st

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@st.cache_resource
def train_ml_model(df, target_column, model_type="Линейная регрессия", poly_degree=2, n_estimators=100, features=None):
    """
    Обучает модель ML (линейная/полиномиальная регрессия или случайный лес).
    """
    try:
        if "Месяц" not in df.columns or target_column not in df.columns:
            raise ValueError("Нет столбцов 'Месяц' и целевой переменной.")

        if features is None:
             X = df[["Месяц"]].values
        else:
            X = df[features].values # Use the selected features

        y = df[target_column].values

        if model_type == "ML (линейная регрессия)":
            model = LinearRegression()
        elif model_type == "ML (полиномиальная регрессия)":
            model = make_pipeline(PolynomialFeatures(poly_degree), LinearRegression())
        elif model_type == "ML (случайный лес)":
            model = RandomForestRegressor(random_state=42, n_estimators=n_estimators) # Set n_estimators
        else:
            raise ValueError(f"Неподдерживаемый тип модели: {model_type}")

        model.fit(X, y)
        cv = KFold(n_splits=5, shuffle=True, random_state=42)
        scores = cross_val_score(model, X, y, cv=cv, scoring="neg_mean_squared_error")
        rmse_scores = np.sqrt(-scores)
        logging.info(
            f"'{model_type}' обучена. Средняя RMSE: {rmse_scores.mean():.2f}"
        )
        return model
    except Exception as e:
        logging.error(f"Ошибка при обучении ML-модели: {e}")
        raise

def predict_with_model(model, future_months):
    """Делает прогноз с помощью обученной модели."""
    try:
        X_future = np.array(future_months).reshape(-1, 1)
        return model.predict(X_future)
    except Exception as e:
        logging.error(f"Ошибка при прогнозировании: {e}")
        raise

@st.cache_resource
def load_ml_model(df, target_column, model_type="Линейная регрессия", poly_degree=2, n_estimators=100, features=None):
    """
    Загружает или обучает (если нет готовой) ML-модель.
    """
    try:
        logging.info(f"Загрузка/обучение модели: '{model_type}'.")
        if df is not None:
            return train_ml_model(df, target_column, model_type, poly_degree, n_estimators, features)
        else:
            logging.warning("Нет данных для обучения ML-модели.")
            return None
    except Exception as e:
        logging.error(f"Ошибка при загрузке/обучении: {e}")
        return None

def save_ml_model(model, filepath="ml_model.pkl"):
    """Сохраняет обученную модель на диск."""
    try:
        joblib.dump(model, filepath)
        logging.info(f"Модель сохранена в {filepath}.")
    except Exception as e:
        logging.error(f"Ошибка сохранения модели: {e}")

def prepare_ml_data(df, target_column):
    """
    Добавляет признаки Lag_1, Lag_2, Rolling_Mean_3 и Rolling_Mean_5.
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