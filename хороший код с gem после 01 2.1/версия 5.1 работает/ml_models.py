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
import xgboost as xgb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@st.cache_resource
def train_ml_model(df, target_column, model_type="ML (линейная регрессия)", poly_degree=2, n_estimators=100, features=None, param_search_method="Нет"):
    """
    Обучает модель ML (линейная/полиномиальная регрессия или случайный лес).
    """
    try:
        if "Месяц" not in df.columns or target_column not in df.columns:
            raise ValueError("Нет столбцов 'Месяц' и целевой переменной.")
        
        if features is None:
            X = df[["Месяц"]].values
        else:
           X = df[features].values

        y = df[target_column].values

        if model_type == "ML (линейная регрессия)":
            model = LinearRegression()
        elif model_type == "ML (полиномиальная регрессия)":
            model = make_pipeline(PolynomialFeatures(poly_degree), LinearRegression())
        elif model_type == "ML (случайный лес)":
            model = RandomForestRegressor(random_state=42, n_estimators=n_estimators)
        elif model_type == "ML (SVR)":
            model = SVR()
        elif model_type == "ML (XGBoost)":
            model = xgb.XGBRegressor(random_state=42)
        else:
            raise ValueError(f"Неподдерживаемый тип модели: {model_type}")
        
        if param_search_method == "GridSearchCV":
          param_grid = get_param_grid(model_type)
          model = GridSearchCV(model, param_grid, cv=5, scoring='neg_mean_squared_error', verbose=0)
        elif param_search_method == "RandomizedSearchCV":
            param_dist = get_param_dist(model_type)
            model = RandomizedSearchCV(model, param_dist, n_iter=10, cv=5, scoring='neg_mean_squared_error', random_state=42, verbose=0)

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

def get_param_grid(model_type):
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
    elif model_type == "ML (XGBoost)":
         return {
            'n_estimators': [100, 200, 300],
            'max_depth': [3, 5, 7],
            'learning_rate': [0.01, 0.1, 0.2],
             'subsample': [0.7, 0.8, 0.9]
         }
    return {}

def get_param_dist(model_type):
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
     elif model_type == "ML (XGBoost)":
        return {
            'n_estimators': np.arange(100, 500, 50),
            'max_depth': np.arange(3, 10, 2),
            'learning_rate': np.logspace(-3, -1, 5),
            'subsample': np.arange(0.6, 1, 0.1),
         }
     return {}


def predict_with_model(model, future_months):
    """Делает прогноз с помощью обученной модели."""
    try:
        X_future = np.array(future_months).reshape(-1, 1)
        return model.predict(X_future)
    except Exception as e:
        logging.error(f"Ошибка при прогнозировании: {e}")
        raise

@st.cache_resource
def load_ml_model(df, target_column, model_type="ML (линейная регрессия)", poly_degree=2, n_estimators=100, features=None, param_search_method="Нет"):
    """
    Загружает или обучает (если нет готовой) ML-модель.
    """
    try:
        logging.info(f"Загрузка/обучение модели: '{model_type}'.")
        if df is not None:
            return train_ml_model(df, target_column, model_type, poly_degree, n_estimators, features, param_search_method)
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

def calculate_metrics(y_true, y_pred):
    """Вычисляет и возвращает метрики качества модели."""
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    mae = mean_absolute_error(y_true, y_pred)
    return rmse, r2, mae