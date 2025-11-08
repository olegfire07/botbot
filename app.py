import base64
import datetime
import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import dash
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, ctx, dash_table, dcc, html
from dash.exceptions import PreventUpdate
from dash.dependencies import Input, Output, State
from dateutil import parser
from flask_caching import Cache
from prophet import Prophet
from scipy.stats import zscore
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score, train_test_split

# ------------------------------------------------------------------------------
# КОНСТАНТЫ
# ------------------------------------------------------------------------------

STATS_COLUMN_NAMES = {
    'index': 'Столбец',
    'count': 'Количество',
    'mean': 'Среднее',
    'std': 'Станд. отклонение',
    'min': 'Минимум',
    '25%': '25-й перцентиль',
    '50%': 'Медиана',
    '75%': '75-й перцентиль',
    'max': 'Максимум'
}

CHART_TYPES = [
    {'label': 'Точечный (Scatter)', 'value': 'scatter'},
    {'label': 'Гистограмма (Histogram)', 'value': 'histogram'},
    {'label': 'Линейный (Line)', 'value': 'line'},
    {'label': 'Столбчатая (Bar)', 'value': 'bar'},
    {'label': 'Размах (Box)', 'value': 'box'},
    {'label': 'Тепловая карта (Heatmap)', 'value': 'heatmap'},
    {'label': 'Круговая (Pie)', 'value': 'pie'},
    {'label': 'Скрипичная диаграмма (Violin)', 'value': 'violin'},
    {'label': 'Площадная (Area)', 'value': 'area'},
    {'label': 'Пузырьковый (Bubble)', 'value': 'bubble'},
]

DATE_FORMATS = [
    {'label': 'День.Месяц.Год (dd.mm.yyyy)', 'value': '%d.%m.%Y'},
    {'label': 'Год-Месяц-День (yyyy-mm-dd)', 'value': '%Y-%m-%d'},
    {'label': 'Месяц/День/Год (mm/dd/yyyy)', 'value': '%m/%d/%Y'},
    {'label': 'ISO 8601', 'value': 'ISO8601'},
]

TEXT_HANDLING_OPTIONS = [
    {'label': 'Оставить как текст', 'value': 'keep_text'},
    {'label': 'Сделать категорией', 'value': 'as_category'},
    {'label': 'Игнорировать', 'value': 'ignore'},
]

DECIMAL_SEPARATORS = [
    {'label': 'Точка (.)', 'value': '.'},
    {'label': 'Запятая (,)', 'value': ','},
    {'label': 'Пробел ( )', 'value': ' '},
]

AGGREGATION_FUNCTIONS = [
    {'label': 'Сумма (sum)', 'value': 'sum'},
    {'label': 'Среднее (mean)', 'value': 'mean'},
    {'label': 'Количество (count)', 'value': 'count'},
    {'label': 'Максимум (max)', 'value': 'max'},
    {'label': 'Минимум (min)', 'value': 'min'},
]

FILTER_OPERATORS = [
    {'label': 'Равно', 'value': '=='},
    {'label': 'Не равно', 'value': '!='},
    {'label': 'Больше', 'value': '>'},
    {'label': 'Меньше', 'value': '<'},
    {'label': 'Больше или равно', 'value': '>='},
    {'label': 'Меньше или равно', 'value': '<='},
    {'label': 'Содержит', 'value': 'contains'},
    {'label': 'Не содержит', 'value': 'not_contains'},
    {'label': 'Не пустое', 'value': 'not_empty'},
    {'label': 'Пустое', 'value': 'empty'},
]

FORECAST_FREQUENCIES = [
    {'label': 'Дни (D)', 'value': 'D'},
    {'label': 'Недели (W)', 'value': 'W'},
    {'label': 'Месяцы (MS)', 'value': 'MS'},
]

# ------------------------------------------------------------------------------
# ЛОГИРОВАНИЕ
# ------------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# ТЕМА BOOTSTRAP И ПАРАМЕТРЫ ПРИЛОЖЕНИЯ
# ------------------------------------------------------------------------------

external_stylesheets = [
    dbc.themes.LITERA,
    "https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.10.5/font/bootstrap-icons.min.css"
]
app = dash.Dash(
    __name__,
    external_stylesheets=external_stylesheets,
    suppress_callback_exceptions=True,
    prevent_initial_callbacks='initial_duplicate'
)
app.title = "Улучшенный Анализ Excel от Олега"
server = app.server

# ------------------------------------------------------------------------------
# КЭШ
# ------------------------------------------------------------------------------

cache = Cache(app.server, config={
    'CACHE_TYPE': 'SimpleCache',  # Для production лучше использовать что-то вроде Redis
    'CACHE_DEFAULT_TIMEOUT': 300  # Время кэширования в секундах
})

# ------------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (УТИЛИТЫ)
# ------------------------------------------------------------------------------

def _read_excel_data(decoded_content: bytes, filename: str) -> Dict[str, pd.DataFrame]:
    """Читаем Excel файл."""
    try:
        if 'xls' in filename:
            return pd.read_excel(io.BytesIO(decoded_content), sheet_name=None, header=None)
        elif 'xlsx' in filename:
            return pd.read_excel(io.BytesIO(decoded_content), sheet_name=None, header=None)
        else:
            raise ValueError(f'Неподдерживаемый формат файла: {filename}')
    except Exception as e:
        logger.exception(f"Ошибка при чтении файла {filename}")
        raise ValueError(f'Ошибка при чтении файла {filename}: {e}')

def _convert_types(df_sheet: pd.DataFrame, date_format: str, text_handling: str = 'keep_text', decimal_separator: str = '.', number_handling: bool = True) -> pd.DataFrame:
     for col in df_sheet.columns:
        if col not in df_sheet.select_dtypes(include=['datetime']).columns:
            df_sheet[col] = df_sheet[col].fillna('').astype(str)
            if pd.api.types.is_string_dtype(df_sheet[col]):
                df_sheet[col] = df_sheet[col].str.strip()
                df_sheet[col] = df_sheet[col].str.replace('\xa0', ' ', regex=False)

            try:
                 df_sheet[col] = pd.to_datetime(
                    df_sheet[col],
                    errors='raise',
                    format=date_format,
                    dayfirst=True
                 )
                 continue
            except Exception:
                 logger.debug(f"Столбец '{col}': не является датой")

            if number_handling:
                try:
                    if decimal_separator != '.' and pd.api.types.is_string_dtype(df_sheet[col]):
                         df_sheet[col] = df_sheet[col].str.replace(decimal_separator, '.', regex=False)
                    df_sheet[col] = pd.to_numeric(df_sheet[col], errors='raise')
                    continue
                except Exception as e:
                    logger.debug(f"Столбец '{col}': не является числом {e}")
            if text_handling == 'as_category':
                unique_count = df_sheet[col].nunique()
                total_count = df_sheet[col].count()
                if total_count > 0 and unique_count / total_count < 0.3:
                   try:
                        df_sheet[col] = df_sheet[col].astype('category')
                        continue
                   except Exception as e:
                       logger.debug(
                           f"Столбец '{col}' не удалось привести к category. Ошибка: {e}"
                       )
                else:
                    logger.debug(
                        f"Столбец '{col}' не является категориальным, пропускаем."
                    )
            elif text_handling == 'ignore':
                 logger.debug(f"Столбец '{col}' пропущен по настройкам.")
     return df_sheet

def _process_sheet(df_sheet: pd.DataFrame, sheet: str, header_row: Optional[int], use_first_row_header: bool, date_format: str, text_handling: str, decimal_separator: str, number_handling: bool) -> List[dict]:
    if df_sheet.empty:
        logger.warning(f"Лист '{sheet}' пуст, пропускаем.")
        return []
    logger.debug(f"Исходный DataFrame для листа '{sheet}':\n{df_sheet.head()}")
    if header_row is not None and isinstance(header_row, int) and 0 <= header_row < len(df_sheet):
        df_sheet.columns = df_sheet.iloc[header_row].astype(str)
        df_sheet = df_sheet.iloc[header_row+1:]
    elif use_first_row_header:
        if all(df_sheet.iloc[0].apply(lambda x: isinstance(x, str))):
            df_sheet.columns = df_sheet.iloc[0].astype(str)
            df_sheet = df_sheet.iloc[1:]
        else:
            default_headers = df_sheet.iloc[0].fillna('').astype(str)
            df_sheet.columns = [
                f"Column_{i}" if header == "" else header
                for i, header in enumerate(default_headers)
            ]
            if not all(df_sheet.iloc[0].isna()):
                df_sheet = df_sheet.iloc[1:]
    else:
        default_headers = df_sheet.iloc[0].fillna('').astype(str)
        df_sheet.columns = [
            f"Column_{i}" if header == "" else header
            for i, header in enumerate(default_headers)
        ]
        if not all(df_sheet.iloc[0].isna()):
            df_sheet = df_sheet[1:]

    df_sheet = _convert_types(df_sheet, date_format, text_handling, decimal_separator, number_handling)

    df_sheet.columns = (
        df_sheet.columns.astype(str)
        .str.replace(r'[^A-Za-zА-Яа-я0-9_]+', '_', regex=True)
        .str.strip()
    )

    col_counts = df_sheet.columns.value_counts()
    for c_dup in col_counts[col_counts > 1].index:
        duplicates_idx = [i for i, c in enumerate(df_sheet.columns) if c == c_dup]
        for idx_i, dup_idx in enumerate(duplicates_idx):
            if idx_i > 0:
                df_sheet.columns.values[dup_idx] = f"{c_dup}_{idx_i}"

    df_sheet = df_sheet.infer_objects(copy=False)
    return df_sheet.to_dict('records')

def parse_contents(
    contents: str,
    filename: str,
    header_row: Optional[int] = None,
    use_first_row_header: bool = True,
    date_format: str = '%d.%m.%Y',
    text_handling: str = 'keep_text',
    decimal_separator: str = '.',
    number_handling: bool = True
) -> Dict[str, Any]:
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        df = _read_excel_data(decoded, filename)
    except Exception as e:
        return {'error': f'Ошибка при обработке файла {filename}: {e}'}

    df_serialized: Dict[str, List[dict]] = {}
    for sheet, data in df.items():
        try:
            df_serialized[str(sheet)] = _process_sheet(pd.DataFrame(data), str(sheet), header_row, use_first_row_header, date_format, text_handling, decimal_separator, number_handling)
        except Exception as e:
            logger.exception(f"Ошибка при обработке листа '{sheet}'")
            return {'error': f'Ошибка при обработке листа {sheet}: {e}'}
    return df_serialized

def create_data_table(df: pd.DataFrame) -> Tuple[List[Dict[str, str]], List[dict]]:
    """Создает данные для dash_table.DataTable."""
    if df is None or df.empty:
        return [], []
    columns = [
        {"name": str(col) if col else " ", "id": str(col) if col else " "}
        for col in df.columns
    ]
    data = df.to_dict('records')
    return columns, data

@cache.memoize()
def combine_data(stored_data: Dict[str, List[dict]], sheet_names: Union[List[str], str]) -> Optional[pd.DataFrame]:
    """Объединяет данные из нескольких листов Excel."""
    if not stored_data or not sheet_names:
        return None

    if isinstance(sheet_names, str):
        sheet_names = [sheet_names]

    df_list = [
        pd.DataFrame(stored_data[sheet])
        for sheet in sheet_names
        if sheet in stored_data
    ]
    if not df_list:
        return None

    combined_df = pd.concat(df_list, ignore_index=True)

    # Попытка преобразования столбцов с датами, которые могли быть считаны как object
    date_cols = combined_df.select_dtypes(include=['object']).columns
    for col in date_cols:
        try:
            # Используем dayfirst=True для явного указания формата дат
            combined_df[col] = combined_df[col].apply(parser.parse, dayfirst=True)
        except:
            pass  # Если не удалось преобразовать, оставляем как есть

    logger.info(
        f"Объединенный DataFrame: {combined_df.shape[0]} строк, {combined_df.shape[1]} столбцов."
    )
    return combined_df

def apply_all_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Применяет основные фильтры (X, Y, доп. фильтр, диапазон дат)."""
    if df is None or df.empty:
        return df

    x_col = filters.get('x_col')
    x_start_date = filters.get('x_start_date')
    x_end_date = filters.get('x_end_date')
    y_col = filters.get('y_col')
    y_min = filters.get('y_min')
    y_max = filters.get('y_max')
    adv_col = filters.get('adv_col')
    adv_val = filters.get('adv_val')

    if x_col and x_col in df.columns:
        if pd.api.types.is_numeric_dtype(df[x_col]):
            if filters.get('x_min') is not None:
                df = df[df[x_col] >= filters.get('x_min')]
            if filters.get('x_max') is not None:
                df = df[df[x_col] <= filters.get('x_max')]
        elif pd.api.types.is_datetime64_any_dtype(df[x_col]):
            if x_start_date:
                df = df[df[x_col] >= pd.to_datetime(x_start_date)]
            if x_end_date:
                df = df[df[x_col] <= pd.to_datetime(x_end_date)]

    if y_col and y_col in df.columns and pd.api.types.is_numeric_dtype(df[y_col]):
        if y_min is not None:
            df = df[df[y_col] >= y_min]
        if y_max is not None:
            df = df[df[y_col] <= y_max]

    if adv_col and adv_col in df.columns and adv_val is not None and pd.api.types.is_numeric_dtype(df[adv_col]):
        df = df[df[adv_col] > adv_val]

    logger.info(
        f"После фильтров: {df.shape[0]} строк, {df.shape[1]} столбцов."
    )
    return df


def apply_dynamic_filters(df: pd.DataFrame, filters: List[Dict[str, Any]]) -> pd.DataFrame:
    """Применяет динамические фильтры."""
    if df is None or df.empty or not filters:
        return df
    for f in filters:
        col = f.get('column')
        op = f.get('operator')
        val = f.get('value')
        if not col or col not in df.columns or op is None or val is None:
            continue

        try:
            if op == '==':
                if pd.api.types.is_numeric_dtype(df[col]):
                     df = df[df[col] == float(val)]
                else:
                    df = df[df[col] == val]
            elif op == '!=':
                if pd.api.types.is_numeric_dtype(df[col]):
                     df = df[df[col] != float(val)]
                else:
                    df = df[df[col] != val]
            elif op == '>':
                df = df[df[col] > float(val)]
            elif op == '<':
                df = df[df[col] < float(val)]
            elif op == '>=':
                df = df[df[col] >= float(val)]
            elif op == '<=':
                df = df[df[col] <= float(val)]
            elif op == 'contains':
                df = df[df[col].astype(str).str.contains(val, na=False, case=False)]
            elif op == 'not_contains':
                df = df[~df[col].astype(str).str.contains(val, na=False, case=False)]
            elif op == "not_empty":
                df = df[df[col].notna()]
            elif op == "empty":
                df = df[df[col].isna()]
        except Exception as e:
            logger.warning(f"Ошибка фильтрации столбца {col}: {e}")
    logger.info(f"После динамических фильтров: {df.shape[0]} строк, {df.shape[1]} столбцов.")
    return df

def create_dynamic_filter_component(filter_data: Dict[str, Any], index: int, col_options: List[Dict[str, str]]) -> html.Div:
    """Создает компонент динамического фильтра."""
    return html.Div([
        dcc.Dropdown(
            options=col_options,
            value=filter_data.get('column'),
            placeholder="Выберите столбец",
            style={'width': '40%', 'display': 'inline-block', 'marginRight': '5px'},
            id={'type': 'filter-column-dropdown', 'index': index}
        ),
        dcc.Dropdown(
            options=FILTER_OPERATORS,
            value=filter_data.get('operator'),
            placeholder="Выберите оператор",
            style={'width': '30%', 'display': 'inline-block', 'marginRight': '5px'},
            id={'type': 'filter-operator-dropdown', 'index': index}
        ),
        dbc.Input(
            value=filter_data.get('value'),
            placeholder="Значение",
            type='text',
            style={'width': '25%', 'display': 'inline-block'},
            id={'type': 'filter-value-input', 'index': index}
        ),
        dbc.Button('Удалить', id={'type': 'delete-filter-btn', 'index': index}, className='btn btn-danger btn-sm', style={'marginLeft': '5px'})
    ], className='mb-2 filter-item', id=f'dynamic-filter-{index}')

# ------------------------------------------------------------------------------
# ФУНКЦИИ ДЛЯ АНАЛИТИКИ
# ------------------------------------------------------------------------------

def perform_statistical_analysis(df: pd.DataFrame) -> html.Div:
    """Выполняет статистический анализ данных."""
    if df is None or df.empty:
        return dbc.Alert("Нет данных для статистического анализа.", color="danger")
    try:
        stats = df.describe(include='all').T.reset_index()
        stats.rename(columns=STATS_COLUMN_NAMES, inplace=True)
        stats_table = dash_table.DataTable(
            columns=[{"name": str(i), "id": str(i)} for i in stats.columns],
            data=stats.to_dict('records'),
            style_table={'overflowX': 'auto'},
            style_header={
                'backgroundColor': 'lightgrey',
                'fontWeight': 'bold',
                'textAlign': 'left'
            },
            style_cell={
                'whiteSpace': 'normal',
                'textAlign': 'left',
                'minWidth': '100px'
            },
            page_size=20,
            style_as_list_view=True
        )
        return html.Div([
            html.H4("Основная статистика", className="text-primary mt-3"),
            stats_table
        ])
    except Exception as e:
        logger.exception(f"Ошибка статистического анализа")
        return dbc.Alert(f"Ошибка статистического анализа: {e}", color="danger")

def _perform_regression_with_cv(df: pd.DataFrame, x_col: str, y_col: str) -> html.Div:
    """Выполняет линейную регрессию с кросс-валидацией."""
    df_reg = df[[x_col, y_col]].dropna()
    X = df_reg[[x_col]]
    y = df_reg[y_col]
    model = LinearRegression()
    cv_scores = cross_val_score(model, X, y, cv=5, scoring='r2')  # 5-кратная кросс-валидация
    cv_mean_r2 = np.mean(cv_scores)

    # Обучение на всем наборе данных для получения коэффициентов
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    slope = model.coef_[0]
    intercept = model.intercept_

    return html.Div([
        html.H4("Линейная Регрессия (с кросс-валидацией)", className="text-secondary"),
        html.P(f"Средний R² (cv=5): {cv_mean_r2:.4f}"),  # Средний R² по кросс-валидации
        html.P(f"Перехват (Intercept): {intercept:.4f}"),
        html.P(f"Коэффициент (Slope): {slope:.4f}"),
        html.P(f"MSE на тесте: {mse:.4f}"),
        html.P(f"R² на тесте: {r2:.4f}")
    ])

def _perform_simple_linear_regression(df: pd.DataFrame, x_col: str, y_col: str, test_size: float) -> html.Div:
    """Выполняет простую линейную регрессию."""
    df_ = df[[x_col, y_col]].dropna()
    X = df_[[x_col]]
    y = df_[y_col]
    if test_size <= 0 or test_size >= 1:
        return dbc.Alert("Значение test_size должно быть между 0 и 1.", color="danger")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)  # Исправлено: используем y_pred
    return html.Div([
        html.H4("Результаты (простая лин. регрессия)", className="text-info"),
        html.P(f"MSE: {mse:.2f}"),
        html.P(f"R²: {r2:.2f}")
    ])

def _perform_rf_regression(df: pd.DataFrame, x_col: str, y_col: str, test_size: float) -> html.Div:
    """Выполняет регрессию Random Forest."""
    df_ = df[[x_col, y_col]].dropna()
    X = df_[[x_col]]
    y = df_[y_col]

    if test_size <= 0 or test_size >= 1:
      return dbc.Alert("Значение test_size должно быть между 0 и 1.", color="danger")

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    return html.Div([
        html.H4("Результаты Random Forest", className="text-info"),
        html.P(f"MSE: {mse:.2f}"),
        html.P(f"R²: {r2:.2f}")
    ])

def _perform_pca_analysis(numeric_df: pd.DataFrame, n_components: int) -> html.Div:
    """Выполняет анализ главных компонент (PCA)."""
    scaler = StandardScaler()
    numeric_scaled = scaler.fit_transform(numeric_df)
    pca = PCA(n_components=n_components)
    pcs = pca.fit_transform(numeric_scaled)
    explained_variance = pca.explained_variance_ratio_

    # График объясненной дисперсии
    pc_cols = [f'ПК{i+1}' for i in range(n_components)]
    df_pca = pd.DataFrame(data=pcs, columns=pc_cols)

    fig_variance = px.bar(
        x=pc_cols, y=explained_variance,
        labels={'x': 'Компоненты', 'y': 'Доля дисперсии'},
        title="Объяснённая дисперсия (PCA)",
        color_discrete_sequence=['#636EFA']
    )

    # Scatter plot для первых двух компонент
    fig_scatter = (
        px.scatter(
            df_pca,
            x='ПК1',
            y='ПК2',
            title="PCA: ПК1 vs ПК2",
            labels={'ПК1': 'ПК1', 'ПК2': 'ПК2'},
            color_discrete_sequence=['#EF553B'],
        )
        if n_components >= 2
        else go.Figure().update_layout(title="Недостаточно компонентов для 2D-графика")
    )

    return html.Div([
        html.H4("Анализ главных компонентов (PCA)", className="text-warning"),
        dcc.Graph(figure=fig_variance),
        dcc.Graph(figure=fig_scatter)
    ])

def _perform_kmeans_clustering(num_clusters: int, numeric_df: pd.DataFrame, selected_columns: List[str]) -> html.Div:
    """Выполняет кластеризацию K-Means."""
    if num_clusters < 2:
        return dbc.Alert("Число кластеров должно быть >= 2.", color="danger")
    if numeric_df.shape[0] < num_clusters:
        return dbc.Alert("Количество кластеров не может превышать число строк после фильтрации.", color="danger")

    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(numeric_df)
    df_clustered = numeric_df.copy()
    df_clustered["Кластер"] = clusters.astype(str)

    # Визуализация (только если выбрано 2 столбца)
    fig = px.scatter(
        df_clustered,
        x=selected_columns[0],
        y=selected_columns[1],
        color="Кластер",
        title=f"K-Means: {num_clusters} кластеров"
    )

    return html.Div([
        html.H4(f"Результаты K-Means (Кластеров: {num_clusters})", className="text-secondary"),
        dcc.Graph(figure=fig)
    ])

def perform_outlier_detection(df: pd.DataFrame, threshold: float = 3.0) -> html.Div:
    """
    Поиск выбросов в числовых столбцах при помощи z-score.
    """
    if df is None or df.empty:
        return dbc.Alert("Нет данных для анализа выбросов.", color="danger")

    numeric_cols = df.select_dtypes(include=['number'])
    if numeric_cols.shape[1] == 0:
        return dbc.Alert("Нет числовых столбцов для анализа выбросов.", color="danger")

    zscores = numeric_cols.apply(zscore)
    outlier_mask = (zscores.abs() > threshold).any(axis=1)
    outliers_df = df[outlier_mask]

    count_outliers = outliers_df.shape[0]
    total_rows = df.shape[0]

    if count_outliers == 0:
      return dbc.Alert("Выбросов не обнаружено с заданным порогом.", color="success")

    columns, data = create_data_table(outliers_df)

    return html.Div([
        html.H4("Результаты Поиска Выбросов", className="text-danger"),
        html.P(f"Всего строк: {total_rows}. Выбросов по Z-score > {threshold}: {count_outliers}"),
        dash_table.DataTable(
            columns=columns,
            data=data,
            style_table={'overflowX': 'auto', 'maxHeight': '400px', 'overflowY': 'scroll'},
            style_header={
                'backgroundColor': 'lightgrey',
                'fontWeight': 'bold',
                'textAlign': 'left'
            },
            style_cell={
                'minWidth': '100px', 'width': '150px', 'maxWidth': '300px',
                'whiteSpace': 'normal'
            },
            filter_action='native',
            sort_action='native',
            sort_mode='multi',
            page_size=10
        )
    ])

def perform_forecast(
    df: pd.DataFrame,
    date_col: str,
    y_col: str,
    forecast_period: int,
    freq: str,
    date_format_user: str
) -> html.Div:
    """Выполняет прогнозирование временного ряда с помощью Prophet."""
    if df is None or not date_col or not y_col or not pd.api.types.is_numeric_dtype(df[y_col]):
        return dbc.Alert("Для прогноза укажите корректные столбцы (Дата, Y) и числовой тип данных для Y.", color="danger")
    if not date_col in df.columns:
        return dbc.Alert(f"Столбец '{date_col}' не найден в данных.", color="danger")
    if not y_col in df.columns:
        return dbc.Alert(f"Столбец '{y_col}' не найден в данных.", color="danger")


    try:
        logger.info(f"Начинаем прогноз Prophet для столбца дат: {date_col}, столбца Y: {y_col}. Формат даты пользователя: {date_format_user}")
        df_prophet = df[[date_col, y_col]].dropna(subset=[date_col, y_col]).copy()
        logger.info(f"Размер DataFrame для Prophet после dropna: {df_prophet.shape}")

        df_prophet.rename(columns={date_col: 'ds', y_col: 'y'}, inplace=True)

        # Обработка дат
        date_parsed = False
        for date_format_attempt in ['ISO8601', date_format_user, 'mixed']:
            if date_parsed:
                break
            try:
                logger.info(f"Пытаемся распарсить даты с форматом: '{date_format_attempt}'")
                df_prophet['ds'] = pd.to_datetime(
                    df_prophet['ds'],
                    format=date_format_attempt if date_format_attempt != 'ISO8601' else None,
                    dayfirst=True,
                    errors='raise',
                    infer_datetime_format= date_format_attempt == 'mixed'
                )
                logger.info(f"Успешно преобразовали столбец 'ds' в datetime, используя формат: '{date_format_attempt}'.")
                date_parsed = True
            except Exception as e:
                logger.warning(f"Не удалось распарсить даты в формате {date_format_attempt}, пробуем следующий формат: {e}")

        if not date_parsed:
            logger.error(f"Ошибка при преобразовании столбца дат (все попытки не удались)")
            logger.error(f"Первые 5 значений столбца дат до преобразования:\n{df[[date_col]].head()}")
            suggested_format_message = "Пожалуйста, проверьте формат даты в вашем файле и выбранный формат дат в настройках загрузки.  Распространенные форматы: ДД.ММ.ГГГГ, ГГГГ-ММ-ДД, ММ/ДД/ГГГГ и ISO 8601. Если ваши даты в другом формате, возможно, потребуется изменить выпадающий список 'Формат дат' в разделе 'Загрузка Excel-файла'."
            return dbc.Alert(f"Ошибка при обработке дат для прогноза: Не удалось распознать формат даты. {suggested_format_message} ", color="danger")

        logger.info(f"Тип данных столбца 'ds' после преобразования даты: {df_prophet['ds'].dtype}")
        logger.info(f"Первые 5 значений столбца 'ds' после преобразования:\n{df_prophet['ds'].head()}")

        df_prophet.dropna(subset=['ds'], inplace=True)
        if df_prophet.empty:
            logger.warning("DataFrame для Prophet пуст после обработки дат.")
            return dbc.Alert("Все даты некорректны или отсутствуют.", color="danger")

        logger.info(f"DataFrame для Prophet перед fit:\n{df_prophet.head()}")

        model = Prophet()
        model.fit(df_prophet)

        future = model.make_future_dataframe(periods=forecast_period, freq=freq)
        forecast = model.predict(future)

        forecast.rename(columns={
            'yhat': 'Прогноз',
            'yhat_lower': 'Нижняя',
            'yhat_upper': 'Верхняя'
        }, inplace=True)


        fig = px.line(
            forecast, x='ds', y=['Прогноз', 'Нижняя', 'Верхняя'],
            title="Прогноз Prophet",
            labels={'ds': 'Дата'}
        )
        fig.add_scatter(x=df_prophet['ds'], y=df_prophet['y'], mode='markers', name='Исходные')
        logger.info("График прогноза успешно построен.")

        return html.Div([
            html.H4("Прогнозирование (Prophet)", className="text-success"),
            dcc.Graph(figure=fig)
        ])
    except Exception as e:
        logger.exception(f"Общая ошибка при выполнении прогноза")
        return dbc.Alert(f"Ошибка при прогнозе: {e}", color="danger")

def perform_machine_learning(df: pd.DataFrame, x_col: str, y_col: str, test_size: float = 0.2) -> html.Div:
    """Выполняет машинное обучение (линейная регрессия)."""
    if df is None or not x_col or not y_col:
        return dbc.Alert("Не указаны X и Y для обучения.", color="danger")
    if not pd.api.types.is_numeric_dtype(df[x_col]) or not pd.api.types.is_numeric_dtype(df[y_col]):
        return dbc.Alert("X и Y должны быть числовыми.", color="danger")

    try:
        return _perform_simple_linear_regression(df, x_col, y_col, test_size) # Используем вспомогательную функцию
    except Exception as e:
        logger.exception(f"Ошибка обучения")
        return dbc.Alert(f"Ошибка обучения: {e}", color="danger")

def perform_random_forest_regression(df: pd.DataFrame, x_col: str, y_col: str, test_size: float = 0.2) -> html.Div:
    """Выполняет регрессию Random Forest."""
    if df is None or not x_col or not y_col:
        return dbc.Alert("Укажите X и Y для Random Forest.", color="danger")
    if not pd.api.types.is_numeric_dtype(df[x_col]) or not pd.api.types.is_numeric_dtype(df[y_col]):
        return dbc.Alert("X и Y должны быть числовыми для RF.", color="danger")
    try:
        return _perform_rf_regression(df, x_col, y_col, test_size)
    except Exception as e:
        logger.exception(f"Ошибка Random Forest")
        return dbc.Alert(f"Ошибка Random Forest: {e}", color="danger")

def perform_pca(df: pd.DataFrame, n_components: int) -> html.Div:
    """Выполняет PCA."""
    if df is None or df.empty:
        return dbc.Alert("Нет данных для PCA.", color="danger")

    numeric_df = df.select_dtypes(include=['number']).dropna()
    if numeric_df.shape[1] < 2:  # Нужно хотя бы 2 числовых столбца
        return dbc.Alert("Недостаточно числовых столбцов для PCA.", color="danger")
    if numeric_df.shape[1] < n_components: #Добавил проверку
        return dbc.Alert(f"Количество числовых столбцов ({numeric_df.shape[1]}) меньше, чем количество компонент PCA ({n_components}). Уменьшите число компонент.", color="danger")

    try:
        return _perform_pca_analysis(numeric_df, n_components)
    except Exception as e:
        logger.exception(f"Ошибка PCA")
        return dbc.Alert(f"Ошибка PCA: {e}", color="danger")

def perform_clustering(df: pd.DataFrame, selected_columns: List[str], num_clusters: int) -> html.Div:
    """Выполняет кластеризацию."""
    if df is None or not selected_columns or len(selected_columns) < 2:
        return dbc.Alert("Выберите >=2 столбца для кластеризации.", color="danger")
    numeric_df = df[selected_columns].select_dtypes(include=['number']).dropna()
    if numeric_df.empty:
         return dbc.Alert("Нет числовых данных для кластеризации.", color="danger")

    try:
       return _perform_kmeans_clustering(num_clusters, numeric_df, selected_columns)
    except Exception as e:
        logger.exception(f"Ошибка кластеризации")
        return dbc.Alert(f"Ошибка кластеризации: {e}", color="danger")

def create_figure(
    df: pd.DataFrame,
    x_col: Optional[str],
    y_col: Optional[str],
    chart_type: str,
    color_col: Optional[str],
    symbol_col: Optional[str]
) -> go.Figure:
    """
    Строим различные типы графиков.
    """
    if df is None or (x_col and x_col not in df.columns) or (y_col and y_col not in df.columns):
        return go.Figure().update_layout(title="Выберите корректные столбцы для графика")

    try:
        if chart_type == 'scatter' and y_col:
            fig = px.scatter(
                df, x=x_col, y=y_col,
                color=color_col,
                symbol=symbol_col,
                title=f"Точечный график (Scatter): {y_col} от {x_col}",
                labels={str(x_col): str(x_col), str(y_col): str(y_col), str(color_col): "Цвет", str(symbol_col): "Символ"},
                hover_data=df.columns
            )
            fig.update_traces(
                hovertemplate=(
                    f"<b>{x_col}: %{{x}}<br>"
                    f"{y_col}: %{{y}}<br>"
                    "<extra></extra>"
                )
            )
        elif chart_type == 'histogram':
            fig = px.histogram(
                df, x=x_col,
                title=f"Гистограмма (Histogram): {x_col}",
                labels={str(x_col): str(x_col)}
            )
            fig.update_traces(hovertemplate='Значение: %{x}, Кол-во: %{y}')
        elif chart_type == 'line' and y_col:
            fig = px.line(
                df, x=x_col, y=y_col,
                title=f"Линейный график (Line): {y_col} от {x_col}",
                labels={str(x_col): str(x_col), str(y_col): str(y_col)},
                markers=True
            )
        elif chart_type == 'bar' and y_col:
             if pd.api.types.is_categorical_dtype(df[x_col]):
                fig = px.bar(
                    df, x=x_col, y=y_col,
                    title=f"Столбчатая (Bar): {y_col} от {x_col}",
                    labels={str(x_col): str(x_col), str(y_col): str(y_col)}
                )
             else:
                  fig = px.bar(
                        df, x=x_col, y=y_col,
                        title=f"Столбчатая (Bar): {y_col} от {x_col}",
                         labels={str(x_col): str(x_col), str(y_col): str(y_col)}
                     )
        elif chart_type == 'box' and y_col:
            fig = px.box(
                df, x=x_col, y=y_col,
                title=f"Диаграмма размаха (Box): {y_col} от {x_col}",
                labels={str(x_col): str(x_col), str(y_col): str(y_col)},
                boxmode='group'
            )
        elif chart_type == 'heatmap':
            numeric_df = df.select_dtypes(include=['number'])
            if numeric_df.empty:
                return go.Figure().update_layout(title="Нет числовых данных для тепловой карты (Heatmap)")
            corr = numeric_df.corr()
            fig = go.Figure(data=go.Heatmap(
                z=corr.values,
                x=corr.columns,
                y=corr.columns,
                colorscale='Viridis',
                colorbar=dict(title="Корр.")
            ))
            fig.update_layout(title="Корреляционная матрица (Heatmap)")

        elif chart_type == 'pie':
            if x_col and x_col in df.columns:
                fig = px.pie(
                    df, names=x_col,
                    title=f"Круговая (Pie): {x_col}",
                    labels={str(x_col): str(x_col)},
                    hole=0.2
                )
            else:
                return go.Figure().update_layout(title="Некорректный столбец для круговой (Pie)")
        elif chart_type == 'violin' and y_col:
            fig = px.violin(
                df, x=x_col, y=y_col,
                color=color_col,
                box=True,
                points='all',
                title=f"Скрипичная диаграмма (Violin): {y_col} от {x_col}",
                labels={str(x_col): str(x_col), str(y_col): str(y_col), str(color_col): "Цвет"},
                hover_data=df.columns
            )
        elif chart_type == 'area' and y_col:
            fig = px.area(
                df, x=x_col, y=y_col,
                color=color_col,
                title=f"Площадная диаграмма (Area): {y_col} от {x_col}",
                labels={str(x_col): str(x_col), str(y_col): str(y_col), str(color_col): "Цвет"},
                hover_data=df.columns
            )
        elif chart_type == 'bubble' and y_col:
            fig = px.scatter(
                df, x=x_col, y=y_col,
                color=color_col,
                size=y_col,
                title=f"Пузырьковый график (Bubble): {y_col} от {x_col}",
                labels={str(x_col): str(x_col), str(y_col): str(y_col), str(color_col): "Цвет", "size": "Размер"},
                hover_data=df.columns
            )
        else:
            return go.Figure().update_layout(title="Неподходящий тип графика или не указаны нужные столбцы")

    except Exception as e:
        logger.exception(f"Ошибка построения графика")
        return go.Figure().update_layout(title=f"Ошибка при построении графика: {e}", color="danger")

    fig.update_layout(
        xaxis_title=f"Ось X: {x_col}" if x_col else "",
        yaxis_title=f"Ось Y: {y_col}" if y_col else "",
        legend_title="Легенда",
        hovermode="closest"
    )
    return fig

def perform_regression_analysis(df: pd.DataFrame, x_col: str, y_col: str, chart_type: str) -> html.Div:
    """Выполняет регрессионный анализ."""
    if df is None or not x_col or not y_col:
        return html.Div("Укажите столбцы X и Y для регрессии.")
    if chart_type not in ['scatter', 'line', 'bar', 'box']:
        return html.Div("Регрессия применяется к Scatter/Line/Bar/Box.")
    if not pd.api.types.is_numeric_dtype(df[y_col]):
        return dbc.Alert("Столбец Y должен быть числовым.", color="danger")
    if not pd.api.types.is_numeric_dtype(df[x_col]):
        return dbc.Alert("Столбец X должен быть числовым.", color="danger")

    try:
        return _perform_regression_with_cv(df, x_col, y_col)
    except Exception as e:
        logger.exception(f"Ошибка регрессии")
        return dbc.Alert(f"Ошибка регрессии: {e}", color="danger")

# ------------------------------------------------------------------------------
# ПОИСК ПО СЛОВУ
# ------------------------------------------------------------------------------

def perform_search_by_word(
    df: pd.DataFrame,
    search_word: str,
    search_cols: Optional[List[str]],
    sum_cols: Optional[List[str]],
    condition_col: Optional[str],
    condition_op: Optional[str],
    condition_val: Optional[str]
) -> html.Div:
    """Поиск по слову в указанных столбцах с опциональным условием и суммированием."""

    if df is None or df.empty:
        return dbc.Alert("Нет данных для поиска.", color="danger")
    if not search_word or not search_cols:
        return dbc.Alert("Укажите слово и выберите столбцы для поиска.", color="warning")

    if condition_col and condition_op and condition_val:
        try:
            if condition_op in ['>', '<', '>=', '<='] and not pd.api.types.is_numeric_dtype(df[condition_col]):
               return dbc.Alert("Операторы больше/меньше доступны только для числовых столбцов.", color="danger")
            if condition_op == 'contains':
                df = df[df[condition_col].astype(str).str.contains(condition_val, case=False, na=False)]
            elif condition_op == 'not_contains':
                df = df[~df[condition_col].astype(str).str.contains(condition_val, case=False, na=False)]
            else:
                if pd.api.types.is_numeric_dtype(df[condition_col]):
                    condition_val = float(condition_val)
                query_str = f"`{condition_col}` {condition_op} @condition_val"
                df = df.query(query_str)
        except Exception as e:
            logger.exception(f"Ошибка при применении условия поиска")
            return dbc.Alert(f"Ошибка при применении условия: {e}", color="danger")

    mask = pd.Series([False]*len(df))
    for col in search_cols:
        mask = mask | df[col].astype(str).str.contains(search_word, case=False, na=False)

    found_df = df[mask]
    rows_found = found_df.shape[0]

    sum_results = {}
    if sum_cols:
        for c in sum_cols:
            if pd.api.types.is_numeric_dtype(df[c]):
                sum_results[c] = found_df[c].sum()
            else:
                sum_results[c] = "Не числовой столбец"

    columns, data = create_data_table(found_df)

    layout_parts = [
        html.H5("Результаты Поиска", className="mt-3"),
        html.P(f"Найдено строк: {rows_found}, где '{search_word}' содержится в столбцах {', '.join(search_cols)}.")
    ]

    if sum_cols:
      sum_text = "Суммы по выбранным столбцам:"
      for col, summ in sum_results.items():
          sum_text += f" **{col}**: {summ};"
      layout_parts.append(html.P(sum_text))

    if rows_found > 0:
        table_component = dash_table.DataTable(
            columns=columns,
            data=data,
            style_table={'overflowX': 'auto', 'maxHeight': '400px', 'overflowY': 'scroll'},
            style_header={
                'backgroundColor': 'lightgrey',
                'fontWeight': 'bold',
                'textAlign': 'left'
            },
            style_cell={
                'minWidth': '100px', 'width': '150px', 'maxWidth': '300px',
                'whiteSpace': 'normal'
            },
            filter_action='native',
            sort_action='native',
            sort_mode='multi'
        )
        layout_parts.append(html.Div([
            html.H6("Таблица найденных строк:"),
            table_component
        ]))


    return html.Div(layout_parts)

def calculate_frequencies(df: pd.DataFrame, category_col: str) -> html.Div:
    """ Вычисление частот встречаемости в столбце """
    if df is None or df.empty:
        return dbc.Alert("Нет данных для анализа частот.", color="danger")

    if not category_col or category_col not in df.columns:
        return dbc.Alert("Выберите столбец для анализа частот.", color="warning")

    try:
        freq_df = df[category_col].value_counts().reset_index()
        freq_df.columns = ['Значение', 'Количество']

        freq_table = dash_table.DataTable(
            columns=[
                {"name": str(i), "id": str(i)} for i in freq_df.columns
            ],
            data=freq_df.to_dict('records'),
            style_table={'overflowX': 'auto'},
            style_header={
                'backgroundColor': 'lightgrey',
                'fontWeight': 'bold',
                'textAlign': 'left'
            },
            style_cell={
                'whiteSpace': 'normal',
                'textAlign': 'left',
                'minWidth': '100px'
            },
            page_size=10,
            style_as_list_view=True
        )
        return html.Div([
            html.H4(f"Частота встречаемости значений: {category_col}", className="text-primary mt-3"),
            freq_table
        ])

    except Exception as e:
        logger.exception(f"Ошибка анализа частот")
        return dbc.Alert(f"Ошибка анализа частот: {e}", color="danger")

def perform_pivot_table(df: pd.DataFrame, index_cols: Optional[List[str]], column_cols: Optional[List[str]], values_col: Optional[str], aggfunc: str) -> Union[Tuple[pd.DataFrame, html.Div], dbc.Alert]:
    """ Выполнение сводной таблицы """
    if df is None or df.empty:
        return dbc.Alert("Нет данных для создания сводной таблицы.", color="danger")
    if not index_cols and not column_cols:
         return dbc.Alert("Выберите хотя бы один столбец для строк или столбцов сводной таблицы.", color="warning")
    if not values_col:
        return dbc.Alert("Выберите столбец значений для сводной таблицы.", color="warning")
    if values_col not in df.columns or not pd.api.types.is_numeric_dtype(df[values_col]):
        return dbc.Alert("Столбец значений должен быть числовым и присутствовать в данных.", color="danger")
    if aggfunc not in ['sum', 'mean', 'count', 'max', 'min']:
        return dbc.Alert("Неверная функция агрегации.", color="danger")

    try:
        pivot_df = df.pivot_table(
            values=values_col,
            index=index_cols,
            columns=column_cols,
            aggfunc=aggfunc
        )
        pivot_df = pivot_df.fillna(0)

        pivot_table_component = dash_table.DataTable(
            columns=[{"name": str(col), "id": str(col)} for col in pivot_df.columns],
            data=pivot_df.reset_index().to_dict('records'),
            style_table={'overflowX': 'auto', 'maxHeight': '400px', 'overflowY': 'scroll'},
            style_header={
                'backgroundColor': 'lightgrey',
                'fontWeight': 'bold',
                'textAlign': 'left'
            },
            style_cell={
                'whiteSpace': 'normal',
                'textAlign': 'left',
                'minWidth': '100px'
            },
        )
        layout = html.Div([
            html.H4("Сводная таблица", className="text-primary mt-3"),
            pivot_table_component
        ])
        return pivot_df, layout

    except Exception as e:
        logger.exception(f"Ошибка при создании сводной таблицы")
        return dbc.Alert(f"Ошибка при создании сводной таблицы: {e}", color="danger")

# ------------------------------------------------------------------------------
# ДОКУМЕНТАЦИЯ
# ------------------------------------------------------------------------------

def create_documentation() -> dbc.Card:
    """Создает карточку с документацией."""
    documentation_text = """
    ## Документация

    **Улучшенный Анализ Excel** — это мощный инструмент для анализа данных из Excel-файлов. Ниже приведено краткое руководство по использованию приложения.

    ### Загрузка данных
    1. **Загрузка файла**: Нажмите на область загрузки и выберите Excel-файл (.xls или .xlsx).
    2. **Выбор листов**: После загрузки выберите один или несколько листов для анализа.
        - **Первая строка как заголовок**: Отмечайте, если первая строка содержит названия столбцов.
        - **Ручной номер строки**: Укажите (с 0) строку, которая содержит названия.
        - **Формат дат**: Выберите формат дат, соответствующий вашим данным.
        - **Обработка текста**: Выберите как обрабатывать текст (как категории, игнорировать или как текст)
        - **Разделитель**: Выберите разделитель для чисел.
        - **Приведение в число**: Выберите, приводить ли столбец в число.

    ### Фильтрация данных
    - **Основные фильтры (X, Y):** Настройте столбцы X и Y для визуализации, а также минимальные и максимальные значения для числовых столбцов.  Для фильтрации по датам используйте компонент выбора диапазона дат.
    - **Дополнительный фильтр:** Скрываемая панель позволяет отфильтровать данные по числовому столбцу, задав пороговое значение.
    - **Динамические фильтры:** Добавляйте произвольное количество фильтров, выбирая столбец, оператор сравнения и значение.

    ### Визуализация
    - **Тип графика:** Выберите тип графика (Scatter, Line, Heatmap, Pie и т.д.) для отображения данных.
    - **Цвет и символ:**  (Для некоторых типов графиков) выберите столбцы для цветового кодирования и различения символов.
    - **Настройка заголовков:** Задайте заголовки для осей X и Y, а также общий заголовок графика.
    - **Размер шрифта:** Настройте размер шрифта для элементов графика.

    ### Анализ данных
    - **Статистика:** Просмотрите основную статистику по всем столбцам (количество, среднее, стандартное отклонение, минимум, максимум, перцентили).
    - **Корреляционная матрица:**  Изучите корреляцию между числовыми столбцами.
    - **Линейная регрессия:** Выполните линейную регрессию с кросс-валидацией, чтобы оценить зависимость между двумя числовыми столбцами.
    - **Random Forest:** Используйте регрессию Random Forest для моделирования зависимости между переменными.
    - **Прогноз (Prophet):**  Выполните прогнозирование временного ряда, указав столбец с датами и столбец со значениями.
    - **PCA (Анализ главных компонент):**  Уменьшите размерность данных, выделив главные компоненты.
    - **Кластеризация (K-Means):**  Разбейте данные на кластеры по заданному количеству.
    - **Поиск выбросов (Outlier Detection):**  Найдите аномальные значения в данных, используя Z-score.
    - **Сводная таблица (Pivot):**  Создайте сводную таблицу, агрегируя данные по выбранным столбцам.

    ### Расширенный Поиск по Слову
    - **Поиск:** Введите слово или фразу для поиска в выбранных столбцах.
    - **Суммирование:**  (Опционально) выберите числовые столбцы для суммирования найденных значений.
    - **Условие:** (Опционально) задайте дополнительное условие фильтрации для поиска.

    ### Частота
    - **Анализ частот:**  Посмотрите, как часто встречаются различные значения в выбранном категориальном столбце.

    ### Скачивание результатов
    - **CSV/Excel:** Скачайте отфильтрованные данные в формате CSV или Excel.
    - **Сводная таблица:** Скачайте результаты сводной таблицы в формате CSV.
    """

    return dbc.Card([
        dbc.CardHeader(html.H4("Документация", className="text-white"), className="bg-info"),
        dbc.CardBody([
            html.Div([
                dcc.Markdown(documentation_text, dangerously_allow_html=True)
            ])
        ])
    ], style={"marginBottom": "30px"})

# ------------------------------------------------------------------------------
# LAYOUT
# ------------------------------------------------------------------------------

app.layout = dbc.Container([
    html.Div([
        html.H1("Улучшенный Анализ Excel",
                className="text-center my-4",
                style={"fontWeight": "bold", "fontSize": "2.5rem"}),
        html.H5("Кластеризация, Поиск, и Прочая Аналитика (от Олега)",
                className="text-center text-muted mb-4"),
    ]),

    dcc.Store(id='pivot-store', data=None),
    dcc.Store(id='dynamic-filters-store', data=[]),
    dcc.Store(id='collapse-store', data={'analytics': False, 'adv_filter': False}),

    dbc.Card([
        dbc.CardHeader([
            html.H4("Загрузка Excel-файла", className="text-primary"),
            dbc.Tooltip("Выберите Excel-файл .xls/.xlsx", target="upload-data", placement="top")
        ]),
        dbc.CardBody([
            dcc.Upload(
                id='upload-data',
                children=dbc.Card(dbc.CardBody([
                    "Перетащите или ",
                    html.A("выберите Excel-файл", style={"textDecoration": "underline"})
                ])),
                style={
                    'width': '100%',
                    'height': '60px',
                    'lineHeight': '60px',
                    'borderWidth': '1px',
                    'borderStyle': 'dashed',
                    'borderRadius': '5px',
                    'textAlign': 'center',
                    'margin': '10px 0'
                },
                multiple=False,
                accept=".xls,.xlsx"
            ),
            html.Div(id='upload-message', className='text-center mt-2'),
            dbc.Row([
               dbc.Col([
                    html.H5("Выберите листы:", className='mt-4'),
                    dcc.Store(id='stored-data'),
                    dcc.Store(id='filters-store', data={}),
                    dcc.Dropdown(
                         id='sheet-dropdown',
                         options=[],
                         value=None,
                         multi=True,
                         placeholder="Список листов..."
                     ),
                    ],width=8),
                    dbc.Col([
                        dbc.Checklist(
                                options=[{"label": "Первая строка как заголовок", "value": True}],
                                value=[True],
                                id="use-first-row-header",
                             ),
                        dbc.Tooltip("Использовать первую строку как заголовки", target="use-first-row-header", placement="top"),
                        html.Br(),
                        dbc.Input(id='header-row-input', type='number', placeholder="Ручной номер строки", min=0),
                        dbc.Tooltip("Укажите строку с заголовками (начиная с 0)", target="header-row-input", placement="top"),
                        html.Br(),
                        html.Label("Формат дат:", className="fw-bold mt=2"),
                        dcc.Dropdown(
                            id='date-format-dropdown',
                            options=DATE_FORMATS,
                            value='%d.%m.%Y',
                            placeholder="Выберите формат дат"
                        ),
                        html.Br(),
                        html.Label("Обработка текста:", className="fw-bold mt=2"),
                         dcc.Dropdown(
                            id='text-handling-dropdown',
                            options=TEXT_HANDLING_OPTIONS,
                            value='keep_text',
                            placeholder="Выберите как обрабатывать текст"
                        ),
                         html.Br(),
                        html.Label("Разделитель:", className="fw-bold mt=2"),
                        dcc.Dropdown(
                            id='decimal-separator-dropdown',
                            options=DECIMAL_SEPARATORS,
                            value='.',
                            placeholder="Выберите разделитель"
                        ),
                        html.Br(),
                         dbc.Checklist(
                                options=[{"label": "Приводить в число", "value": True}],
                                value=[True],
                                id="number-handling-checkbox",
                             ),
                        dbc.Tooltip("Преобразовать в числовой формат", target="number-handling-checkbox", placement="top"),
                    ],width=4)
                 ], className='mb-2'),
        ])
    ], style={"marginBottom": "30px"}),

    dbc.Card([
        dbc.CardHeader(html.H4("Фильтры и Параметры", className="text-white"), className="bg-primary"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Столбец X:", className="fw-bold"),
                    dcc.Dropdown(id='x-axis-dropdown', options=[], value=None, placeholder="Выберите столбец X", disabled=True),
                    dbc.Tooltip("Столбец для оси X в визуализации", target='x-axis-dropdown', placement="top"),

                    html.Label("Диапазон дат (X):", className="fw-bold mt-2"),
                    dcc.DatePickerRange(
                        id='x-date-range',
                        display_format='DD.MM.YYYY',
                        start_date_placeholder_text="Начальная дата",
                        end_date_placeholder_text="Конечная дата",
                        clearable=True,
                        style={'width': '100%'}
                    ),
                ], width=6),
                dbc.Col([
                    html.Label("Столбец Y:", className="fw-bold"),
                    dcc.Dropdown(id='y-axis-dropdown', options=[], value=None, placeholder="Выберите столбец Y", disabled=True),
                    dbc.Tooltip("Столбец для оси Y в визуализации", target='y-axis-dropdown', placement="top"),
                    dbc.InputGroup([
                        dbc.InputGroupText("Мин Y"),
                        dbc.Input(id='y-min', type='number', placeholder="Мин. значение")
                    ], className='my-1'),
                    dbc.InputGroup([
                        dbc.InputGroupText("Макс Y"),
                        dbc.Input(id='y-max', type='number', placeholder="Макс. значение")
                    ], className='my-1'),
                ], width=6),
            ], className='mb-2'),

            dbc.Button("Доп. Фильтр (скрыть/показать)", id="toggle-adv-filter", color="secondary", outline=True, className="mb-2"),
            dbc.Collapse(
                dbc.Card(dbc.CardBody([
                    html.Label("Числовой столбец (> значение):", className="fw-bold"),
                    dcc.Dropdown(id='adv-filter-column', options=[], value=None, placeholder="Выберите столбец", disabled=True),
                    dbc.Tooltip("Выберите столбец и задайте пороговое значение", target='adv-filter-column', placement="top"),
                    dbc.Input(id='adv-filter-value', type='number', placeholder='Пороговое значение...'),
                    dbc.Tooltip("Задайте пороговое значение для фильтрации", target='adv-filter-value', placement="top"),

                ])),
                id="collapse-adv-filter",
                is_open=False
            ),

            html.Br(),
             # Динамические фильтры
            html.Div(id='filter-div', className='mb-2'),
            dbc.Button('Добавить фильтр', id='add-filter-btn', color='primary', size='sm', className="mt-1"),


            html.Br(),
            dbc.Button([
                html.I(className="bi bi-filter-circle me-1"),
                "Применить фильтры"
            ], id='apply-filters-btn', color='primary', className='me-2'),

            dbc.Button([
                html.I(className="bi bi-arrow-repeat me-1"),
                "Сбросить фильтры"
            ], id='reset-filters-btn', color='warning', className='me-2'),
        ])
    ], style={"marginBottom": "30px"}),

    dbc.Card([
        dbc.CardHeader(html.H4("Визуализация и Таблица", className="text-white"), className="bg-success"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Тип графика:", className="fw-bold"),
                    dcc.Dropdown(
                        id='chart-type-dropdown',
                        options=CHART_TYPES,
                        value='scatter',
                        placeholder="Выберите тип...",
                        disabled=True
                    ),
                    dbc.Tooltip("Выберите тип графика для отображения данных", target='chart-type-dropdown', placement="top"),
                ], width=6),
                dbc.Col([
                    html.Label("Цвет (Color):", className="fw-bold"),
                    dcc.Dropdown(id='color-dropdown', options=[], value=None, placeholder="Колонка для цвета", disabled=True),
                    dbc.Tooltip("Выберите столбец для цветового кодирования данных", target='color-dropdown', placement="top"),

                    html.Label("Символ (Symbol):", className='mt-2 fw-bold'),
                    dcc.Dropdown(id='symbol-dropdown', options=[], value=None, placeholder="Колонка для символов", disabled=True),
                    dbc.Tooltip("Выберите столбец для различения символов на графике", target='symbol-dropdown', placement="top"),
                ], width=6),
            ]),
            dbc.Row([
                dbc.Col([
                    html.Label("Заголовок оси X:", className="fw-bold"),
                    dbc.Input(id='x-axis-title', type='text', placeholder="Введите название оси X"),
                    html.Label("Заголовок оси Y:", className="mt-2 fw-bold"),
                    dbc.Input(id='y-axis-title', type='text', placeholder="Введите название оси Y")
                ], width=6),
                 dbc.Col([
                    html.Label("Заголовок графика:", className="fw-bold"),
                    dbc.Input(id='graph-title', type='text', placeholder="Введите заголовок"),
                      html.Label("Размер шрифта:", className='mt-2 fw-bold'),
                    dcc.Dropdown(
                        id='font-size-dropdown',
                        options=[{'label': str(i), 'value': i} for i in range(10, 21)],
                        value=12,
                        placeholder="Выберите размер шрифта"
                    )
                ], width=6)
            ]),

            dbc.Button(
                [
                    html.I(className="bi bi-arrow-clockwise me-1"),
                    "Обновить Визуализацию",
                    dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'hidden'}),
                ],
                id='update-button', color='success', className='my-3'),

            # Прогресс бар
            dbc.Progress(id="progress-bar", value=0, label="", color="success", style={"height": "10px", "marginBottom": "10px"}),

            html.Div(id='data-info', className='text-info mb-2', style={"fontSize": "0.9rem"}),
            dcc.Graph(id='data-graph'),
            dbc.Tooltip( # Добавляем Tooltip к графику
                "Этот график отображает данные, выбранные из Excel файла. Используйте выпадающие списки выше, чтобы выбрать тип графика и столбцы.",
                target='data-graph',
                placement="bottom"
            ),
            html.Div(id='table-error', className='text-danger mb-2'),
            html.H5("Таблица данных:", className='mt-3 text-primary'),
            dash_table.DataTable(
                id='data-table',
                columns=[],
                data=[],
                style_table={'overflowX': 'auto', 'height': '400px', 'overflowY': 'scroll'},
                style_header={
                    'backgroundColor': 'lightgrey',
                    'fontWeight': 'bold',
                    'textAlign': 'left'
                },
                style_cell={
                    'minWidth': '100px', 'width': '150px',
                    'whiteSpace': 'normal',
                    'textAlign': 'left'
                },
                filter_action='native',
                sort_action='native',
                sort_mode='multi',
                # Условное форматирование
                style_data_conditional=[
                    {
                        'if': {'column_type': 'numeric'},
                        'backgroundColor': '#f2f2f2',
                    },
                ],
              placeholder = "Нет данных для отображения"
            ),
            html.Div([
                html.A(
                    'Скачать CSV',
                    id='download-link',
                    download="filtered_data.csv",
                    href="",
                    target="_blank",
                    className='btn btn-secondary me-2'
                ),
                html.A(
                    'Скачать Excel',
                    id='download-excel-link',
                    download="filtered_data.xlsx",
                    href="",
                    target="_blank",
                    className='btn btn-success'
                )
            ]),
        ])
    ], style={"marginBottom": "30px"}),

    dbc.Card([
        dbc.CardHeader(html.H4("Расширенный Поиск по Слову", className="text-white"), className="bg-info"),
        dbc.CardBody([
            html.Label("Слово для поиска:", className="fw-bold"),
            dbc.Tooltip("Введите слово для поиска в выбранных столбцах", target='search-word', placement="top"),
            dbc.Input(id='search-word', type='text', placeholder='Введите слово...', debounce=True),  # Добавляем debounce
            html.Br(),

            html.Label("Столбцы для поиска:", className="fw-bold"),
            dcc.Dropdown(
                id='search-columns-dropdown',
                options=[],
                value=None,
                placeholder="Выберите столбцы...",
                multi=True
            ),
            html.Br(),

            html.Label("Столбцы для суммирования (опционально):", className="fw-bold"),
            dcc.Dropdown(
                id='sum-columns-dropdown',
                options=[],
                value=None,
                placeholder="Выберите столбцы для суммирования...",
                multi=True
            ),
            html.Br(),

            html.Label("Дополнительные условия (опционально):", className="fw-bold"),
            dbc.Row([
                dbc.Col([
                    dcc.Dropdown(
                        id='condition-column-dropdown',
                        options=[],
                        value=None,
                        placeholder="Столбец...",
                        multi=False
                    ),
                ], width=4),
                dbc.Col([
                    dcc.Dropdown(
                        id='condition-operator-dropdown',
                        options=[
                            {'label': 'Равно', 'value': '=='},
                            {'label': 'Не равно', 'value': '!='},
                            {'label': 'Больше', 'value': '>'},
                            {'label': 'Меньше', 'value': '<'},
                            {'label': 'Больше или равно', 'value': '>='},
                            {'label': 'Меньше или равно', 'value': '<='},
                            {'label': 'Содержит', 'value': 'contains'},
                            {'label': 'Не содержит', 'value': 'not_contains'},
                        ],
                        value=None,
                        placeholder="Оператор",
                        multi=False
                    ),
                ], width=4),
                dbc.Col([
                    dbc.Input(
                        id='condition-value-input',
                        type='text',
                        placeholder='Значение...'
                    ),
                ], width=4),
            ], className='mb-2'),
            html.Br(),

            dbc.Button([
                html.I(className="bi bi-search me-1"),
                "Выполнить Поиск"
            ], id='search-button', color='info'),
            html.Div(id='search-output', className='mt-3')
        ])
    ], style={"marginBottom": "30px"}),

    dbc.Card([
            dbc.CardHeader(html.H4("Частота встречаемости значений в столбце", className="text-white"), className="bg-info"),
            dbc.CardBody([
                 html.Label("Выберите столбец:", className="fw-bold"),
                dcc.Dropdown(
                    id='category-column-dropdown',
                    options=[],
                    value=None,
                    placeholder="Выберите столбец..."
                ),
                html.Br(),
                dbc.Button("Показать частоты", id='frequency-button', color='info', className='mt-2'),
                 html.Div(id='frequency-output', className='mt-3')
                ])
            ], style={"marginBottom": "30px"}),


    dbc.Card([
        dbc.CardHeader(html.H4("Расширенный Анализ", className="text-white"), className="bg-secondary"),
        dbc.CardBody([
            dbc.Button("Показать Аналитику", id="toggle-analytics", color="secondary", outline=True, className="mb-2"),
            dbc.Collapse(
                dbc.Card(dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.H5("Статистика", className="text-muted"),
                            html.Div(id='stats-output', className='my-3'),

                            html.H5("Корреляционная Матрица", className="text-muted"),
                            dcc.Graph(id='correlation-heatmap'),

                            html.H5("Линейная Регрессия", className="text-muted"),
                            html.Div(id='regression-output', className='my-3'),
                        ], width=6),

                        dbc.Col([
                            html.H5("Прогноз (Prophet)", className="text-muted"),
                            html.Label("Столбец с датами:", className="fw-bold"),
                            dcc.Dropdown(id='date-column-dropdown', options=[], value=None, placeholder="Выберите столбец с датами"),
                            dbc.InputGroup([
                                dbc.InputGroupText("Период (шаги):"),
                                dbc.Input(id='forecast-period', type='number', value=12, min=1, max=120, placeholder="Период"),
                                dbc.InputGroupText("Частота:"),
                                dcc.Dropdown(
                                    id='forecast-freq',
                                    options=FORECAST_FREQUENCIES,
                                    value='MS',
                                    style={'width': '100px'}
                                ),
                            ], className='my-2'),
                            html.Div(id='forecast-output', className='mb-3'),
                            dbc.Button(
                                "Запустить Прогноз",
                                id='forecast-button',
                                color='success',
                                className='mt-2'
                            ),


                            html.H5("Машинное Обучение (Лин.рег)", className="text-muted"),
                            dbc.InputGroup([
                                dbc.InputGroupText("test_size:"),
                                dbc.Input(id='ml-test-size', type='number', value=0.2, min=0.05, max=0.95, step=0.05),
                                dbc.Button('Запустить', id='ml-button', color='primary', className='ms-2')
                            ], className='my-3'),
                            dbc.Tooltip("Укажите размер тестовой выборки и запустите обучение", target='ml-button', placement="top"),
                            html.Div(id='ml-output'),

                            html.H5("Random Forest", className="text-muted"),
                            dbc.InputGroup([
                                dbc.InputGroupText("test_size:"),
                                dbc.Input(id='rf-test-size', type='number', value=0.2, min=0.05, max=0.95, step=0.05),
                                dbc.Button('Запустить RF', id='rf-button', color='info', className='ms-2')
                            ], className='my-3'),
                            dbc.Tooltip("Укажите размер тестовой выборки и запустите Random Forest", target='rf-button', placement="top"),
                            html.Div(id='rf-output'),
                        ], width=6),
                    ])
                ])),
                id="collapse-analytics",
                is_open=False
            )
        ])
    ], style={"marginBottom": "30px"}),

    dbc.Card([
        dbc.CardHeader(html.H4("PCA и Кластеризация", className="text-white"), className="bg-dark"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.H5("PCA (Главные Компоненты)", className="text-warning"),
                    dcc.Slider(
                        id='pca-components',
                        min=2, max=10, step=1, value=2,
                        marks={i: str(i) for i in range(2, 11)},
                        tooltip={"placement": "bottom", "always_visible": True}
                    ),
                    dbc.Tooltip("Выберите количество главных компонент для анализа", target='pca-components', placement="top"),
                    dbc.Button('Выполнить PCA', id='pca-button', color='warning', className='mt-2'),
                    html.Div(id='pca-output', className='mt-3')
                ], width=6),
                dbc.Col([
                    html.H5("Кластеризация (K-Means)", className="text-warning"),
                    html.Label("Выберите числовые столбцы:", className="fw-bold"),
                    dcc.Dropdown(
                        id='cluster-columns-dropdown',
                        options=[],
                        value=None,
                        placeholder="Выберите столбцы...",
                        multi=True
                    ),
                    html.Label("Количество кластеров:", className='mt-2 fw-bold'),
                    dbc.Input(id='num-clusters', type='number', value=3, min=2, step=1, style={'width': '100px'}, placeholder="Количество кластеров"),
                    dbc.Button('Выполнить', id='cluster-button', color='secondary', className='mt-2'),
                    html.Div(id='cluster-output', className='mt-3')
                ], width=6),
            ])
        ])
    ], style={"marginBottom": "30px"}),

    dbc.Card([
        dbc.CardHeader(html.H4("Поиск Выбросов (Outlier Detection)", className="text-white"), className="bg-secondary"),
        dbc.CardBody([
            html.Label("Порог (threshold) для |Z-score|:", className="fw-bold"),
            dcc.Slider(
                id='outlier-threshold',
                min=1, max=5, step=0.5, value=3,
                marks={i: str(i) for i in range(1, 6)},
                tooltip={"placement": "bottom", "always_visible": True}
            ),
            dbc.Button("Показать выбросы", id='outlier-button', color='secondary', className='mt-2'),
            html.Div(id='outlier-output', className='mt-2'),
        ])
    ], style={"marginBottom": "30px"}),

    dbc.Card([
        dbc.CardHeader(html.H4("Сводная Таблица (Pivot)", className="text-white"), className="bg-info"),
        dbc.CardBody([
            html.Label("Столбцы (Index) для строк сводной:", className="fw-bold"),
            dcc.Dropdown(
                id='pivot-index',
                options=[],
                value=None,
                placeholder="Выберите столбец (или несколько)",
                multi=True
            ),
            html.Br(),
            html.Label("Столбцы (Columns) для колонок сводной:", className="fw-bold"),
            dcc.Dropdown(
                id='pivot-columns',
                options=[],
                value=None,
                placeholder="Выберите столбец (или несколько)",
                multi=True
            ),
            html.Br(),
            html.Label("Числовой столбец (Values) для агрегации:", className="fw-bold"),
            dcc.Dropdown(
                id='pivot-values',
                options=[],
                value=None,
                placeholder="Выберите числовой столбец"
            ),
            html.Br(),
            html.Label("Функция агрегации:", className="fw-bold"),
            dcc.Dropdown(
                id='pivot-aggfunc',
                options=AGGREGATION_FUNCTIONS,
                value='sum',
                placeholder="Выберите тип агрегации"
            ),
            html.Br(),
            dbc.Button("Построить сводную таблицу", id='pivot-button', color='info'),
            html.Div(id='pivot-output', className='mt-3'),

            html.A(
                'Скачать Pivot CSV',
                id='download-pivot-link',
                download="pivot_table.csv",
                href="",
                target="_blank",
                className='btn btn-secondary mt-2'
            )
        ])
    ], style={"marginBottom": "30px"}),

    create_documentation()

], fluid=True)

# ------------------------------------------------------------------------------
# КОЛЛБЭКИ
# ------------------------------------------------------------------------------

# Коллбэк для условного форматирования таблицы
@app.callback(
    Output('data-table', 'style_data_conditional'),
    Input('data-table', 'columns')
)
def update_table_style(columns):
    if not columns:
        return []

    style_conditions = [
        {
            'if': {'column_type': 'numeric'},
            'backgroundColor': '#f2f2f2',
        },
    ]

    for col in columns:
        col_id = col['id']
        style_conditions.extend([
            {
                'if': {
                    'filter_query': f'{{{col_id}}} > 0',
                    'column_type': 'numeric',
                    'column_id': col_id
                },
                'color': 'darkgreen',
                'fontWeight': 'bold'
            },
            {
                'if': {
                    'filter_query': f'{{{col_id}}} < 0',
                    'column_type': 'numeric',
                    'column_id': col_id
                },
                'color': 'darkred',
                'fontWeight': 'bold'
            },
             {
                'if': {
                    'filter_query': f'{{{col_id}}} is blank',
                    'column_id': col_id
                },
                'backgroundColor': 'lightyellow',
            },
        ])
    return style_conditions


# Обновляем график, таблицу, статистику, ссылки CSV и Excel (с индикатором загрузки)
@app.callback(
    Output('data-graph', 'figure'),
    Output('data-table', 'columns'),
    Output('data-table', 'data'),
    Output('table-error', 'children'),
    Output('stats-output', 'children'),
    Output('correlation-heatmap', 'figure'),
    Output('regression-output', 'children'),
    Output('download-link', 'href'),
    Output('download-excel-link', 'href'),
    Output('data-info', 'children'),
    Output('update-button', 'children'),
    Output('progress-bar', 'value'),
    Output('progress-bar', 'label'),
    Input('update-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('x-axis-dropdown', 'value'),
    State('y-axis-dropdown', 'value'),
    State('chart-type-dropdown', 'value'),
    State('color-dropdown', 'value'),
    State('symbol-dropdown', 'value'),
    State('dynamic-filters-store', 'data'),
    State('x-axis-title', 'value'),
    State('y-axis-title', 'value'),
    State('graph-title', 'value'),
    State('font-size-dropdown', 'value')
)
def update_graph(n_clicks,
                 stored_data,
                 sheet_names,
                 filters,
                 x_col,
                 y_col,
                 chart_type,
                 color_col,
                 symbol_col,
                 dynamic_filters,
                x_axis_title,
                y_axis_title,
                 graph_title,
                 font_size
                 ):
    if not stored_data or not sheet_names:
        raise PreventUpdate

    # Disable the button and show loading spinner
    loading_button = [
        html.I(className="bi bi-arrow-clockwise me-1"),
        "Обновить Визуализацию",
        dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'}),
    ]

    progress = 0
    progress_label = ""

    df = combine_data(stored_data, sheet_names)

    progress = 10
    progress_label = "Объединение данных..."


    if df is None or df.empty:
       return (
            go.Figure().update_layout(title='Нет данных'),
            [], [],
            "Нет данных для отображения.",
            dbc.Alert('Нет данных.', color='danger'),
            go.Figure(),
            html.Div(),
            "",
            "", #  excel link
             "Нет данных для отображения.",
            loading_button,
            progress,
            progress_label
        )

    before_shape = df.shape
    df = apply_all_filters(df, filters or {})
    progress = 30
    progress_label = "Применение фильтров..."

    if dynamic_filters:
        df = apply_dynamic_filters(df, dynamic_filters)
    after_shape = df.shape
    data_info_text = f"До фильтров: {before_shape[0]} строк, {before_shape[1]} столбцов. После фильтров: {after_shape[0]} строк, {after_shape[1]} столбцов."

    fig = create_figure(df, x_col, y_col, chart_type, color_col, symbol_col)
    fig.update_layout(
      title=graph_title,
      xaxis_title=x_axis_title,
      yaxis_title=y_axis_title,
        font=dict(size=font_size)
    )
    progress = 50
    progress_label = "Построение графика..."

    table_cols, table_data = create_data_table(df)
    stats_out = perform_statistical_analysis(df)
    table_error = None if table_data else "Нет данных после фильтрации."
    progress = 70
    progress_label = "Создание таблицы..."


    if chart_type == 'heatmap':
        corr_fig = fig
    else:
        numeric_df = df.select_dtypes(include=['number'])
        if numeric_df.shape[1] >= 2:
            corr = numeric_df.corr()
            corr_fig = go.Figure(data=go.Heatmap(
                z=corr.values,
                x=corr.columns,
                y=corr.columns,
                colorscale='Viridis',
                colorbar=dict(title="Корр.")
            ))
            corr_fig.update_layout(title="Корреляционная матрица")
        else:
            corr_fig = go.Figure().update_layout(title="Недостаточно числовых данных для корреляции.")

    reg_out = perform_regression_analysis(df, x_col, y_col, chart_type)
    progress = 85
    progress_label = "Выполнение анализа..."


    # Скачивание CSV
    if df.empty:
        csv_str = ""
        excel_str = ""
    else:
        df_download = df.copy()
        date_columns = df_download.select_dtypes(include=['datetime', 'datetimetz']).columns
        for c in date_columns:
            df_download[c] = df_download[c].dt.strftime('%d.%m.%Y')
        csv_data = df_download.to_csv(index=False, encoding='utf-8')
        csv_str = "data:text/csv;charset=utf-8," + base64.b64encode(csv_data.encode()).decode()

        # Скачивание в Excel (используем BytesIO)
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            df_download.to_excel(writer, sheet_name='Filtered Data', index=False)
        excel_data = excel_buffer.getvalue()
        excel_str = "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + base64.b64encode(excel_data).decode()


    progress = 100
    progress_label="Готово"

    button_text =  [
                    html.I(className="bi bi-arrow-clockwise me-1"),
                    "Обновить Визуализацию",
                   ]

    return (
        fig,
        table_cols, table_data,
        table_error,
        stats_out,
        corr_fig,
        reg_out,
        csv_str,
        excel_str, #  excel
        data_info_text,
        button_text,
        progress, #  прогресс
        progress_label
    )

# 12) Прогноз Prophet (отдельный callback)
@app.callback(
    Output('forecast-output', 'children'),
     Output('forecast-button', 'children'), # Изменяем текст во время выполнения
    Input('forecast-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('date-column-dropdown', 'value'),
    State('y-axis-dropdown', 'value'),
    State('forecast-period', 'value'),
    State('forecast-freq', 'value'),
    State('date-format-dropdown', 'value'),
     State('dynamic-filters-store', 'data'), # Добавляем динамические фильтры
    prevent_initial_call=True
)
def forecast_callback(n_clicks, stored_data, sheet_names, filters, date_col, y_col, forecast_period, freq, date_format_value, dynamic_filters):
    if not n_clicks:
        raise PreventUpdate

    loading_button = [
        "Запустить Прогноз",
        dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'}),  # Показываем спиннер
    ]


    if not stored_data or not sheet_names:
        return dbc.Alert("Загрузите файл и выберите листы.", color="warning"),  loading_button # Возвращаем Alert
    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if dynamic_filters: # Применяем динамические фильтры
        df = apply_dynamic_filters(df, dynamic_filters)
    if df is None:
        return dbc.Alert("Нет данных для прогноза.", color="danger"), loading_button
    if not date_col:
        return dbc.Alert("Выберите столбец с датами для прогнозирования.", color="warning"), loading_button
    if not y_col:
        return dbc.Alert("Выберите столбец со значениями (Y) для прогнозирования.", color="warning"), loading_button
    if date_col not in df.columns:
        return dbc.Alert(f"Столбец '{date_col}' не найден в данных.", color="danger"), loading_button
    if y_col not in df.columns:
        return dbc.Alert(f"Столбец '{y_col}' не найден в данных.", color="danger"), loading_button
    if not pd.api.types.is_numeric_dtype(df[y_col]):
        return dbc.Alert("Столбец Y должен содержать числовые данные.", color="warning"), loading_button


    result = perform_forecast(df, date_col, y_col, forecast_period, freq, date_format_value)

    button_text = [
                    "Запустить Прогноз"
                   ]
    return result, button_text # Возвращаем результат и обычный текст

# 13) Машинное обучение (линейная регрессия)
@app.callback(
    Output('ml-output', 'children'),
    Output('ml-button', 'children'), # Изменяем текст во время выполнения
    Input('ml-button', 'n_clicks'),
    State('ml-test-size', 'value'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('x-axis-dropdown', 'value'),
    State('y-axis-dropdown', 'value'),
     State('dynamic-filters-store', 'data'), # Добавляем динамические фильтры
    prevent_initial_call=True
)
def ml_callback(n_clicks, test_size, stored_data, sheet_names, filters, x_col, y_col, dynamic_filters):
    """Запускает машинное обучение (лин. регрессию)."""
    if not n_clicks:
        raise PreventUpdate
    loading_button = [
        'Запустить',
        dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'})  # Показываем спиннер
    ]

    if not stored_data or not sheet_names:
        return dbc.Alert("Загрузите файл и выберите листы.", color="warning"), loading_button
    if not 0.05 <= test_size <= 0.95:
        return dbc.Alert("Значение `test_size` должно быть в диапазоне от 0.05 до 0.95.", color="danger"), loading_button # Валидация test_size

    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if dynamic_filters: # Применяем динамические
         df = apply_dynamic_filters(df, dynamic_filters)

    result = perform_machine_learning(df, x_col, y_col, test_size)

    button_text = [
        'Запустить'
    ]

    return result, button_text  # Возвращаем результат и обычный текст

# 14) Random Forest
@app.callback(
    Output('rf-output', 'children'),
    Output('rf-button', 'children'),  # Изменяем текст во время выполнения
    Input('rf-button', 'n_clicks'),
    State('rf-test-size', 'value'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('x-axis-dropdown', 'value'),
    State('y-axis-dropdown', 'value'),
     State('dynamic-filters-store', 'data'), # Добавляем динамические фильтры
    prevent_initial_call=True
)
def rf_callback(n_clicks, test_size, stored_data, sheet_names, filters, x_col, y_col, dynamic_filters):
    if not n_clicks:
        raise PreventUpdate
    loading_button = [
        'Запустить RF',
        dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'})  # Показываем спиннер
    ]
    if not stored_data or not sheet_names:
        return dbc.Alert("Сначала загрузите файл и выберите листы.", color="warning"), loading_button # Alert
    if not 0.05 <= test_size <= 0.95:
        return dbc.Alert("Значение `test_size` должно быть в диапазоне от 0.05 до 0.95.", color="danger"), loading_button # Валидация

    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if dynamic_filters:
        df = apply_dynamic_filters(df, dynamic_filters)

    result = perform_random_forest_regression(df, x_col, y_col, test_size)

    button_text = [
       'Запустить RF'
    ]

    return result, button_text # Результат и обычный текст

# 15) Кластеризация
@app.callback(
    Output('cluster-output', 'children'),
      Output('cluster-button', 'children'), # Изменяем текст
    Input('cluster-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('cluster-columns-dropdown', 'value'),
    State('num-clusters', 'value'),
     State('dynamic-filters-store', 'data'), # Добавляем динамические
    prevent_initial_call=True
)
def cluster_callback(n_clicks, stored_data, sheet_names, filters, selected_cols, n_clusters, dynamic_filters):
    """Выполняет кластеризацию."""
    if not n_clicks:
        raise PreventUpdate
    loading_button = [
        'Выполнить',
        dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'}) # Спиннер
    ]
    if not stored_data or not sheet_names:
        return dbc.Alert("Нет данных для кластеризации.", color="warning"), loading_button
    if not n_clusters or n_clusters < 2:
        return dbc.Alert("Число кластеров должно быть >= 2.", color="danger"), loading_button # Валидация

    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if dynamic_filters:
         df = apply_dynamic_filters(df, dynamic_filters)
    result = perform_clustering(df, selected_cols, n_clusters)

    button_text = [
       'Выполнить'
    ]
    return result, button_text

# 16) PCA
@app.callback(
    Output('pca-output', 'children'),
     Output('pca-button', 'children'), # Изменяем текст
    Input('pca-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('pca-components', 'value'),
    State('dynamic-filters-store', 'data'), # Добавляем динамические
    prevent_initial_call=True
)
def pca_callback(n_clicks, stored_data, sheet_names, filters, n_components, dynamic_filters):
    """Выполняет PCA."""
    if not n_clicks:
        raise PreventUpdate
    loading_button = [
        'Выполнить PCA',
        dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'}) # Спиннер
    ]
    if not stored_data or not sheet_names:
        return dbc.Alert("Нет данных для PCA.", color="warning"), loading_button
    if not n_components or n_components < 2:
        return dbc.Alert("Количество компонент PCA должно быть >= 2.", color="danger"), loading_button  # Валидация

    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if "dynamic_filters" in filters:  #  динамические фильтры, если есть
        df = apply_dynamic_filters(df, filters.get("dynamic_filters"))
    result = perform_pca(df, n_components)

    button_text = [
      'Выполнить PCA'
    ]
    return result, button_text

# 17) Поиск по слову
@app.callback(
    Output('search-output', 'children'),
      Output('search-button', 'children'), # Изменяем текст
    Input('search-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('search-word', 'value'),
    State('search-columns-dropdown', 'value'),
    State('sum-columns-dropdown', 'value'),
    State('condition-column-dropdown', 'value'),
    State('condition-operator-dropdown', 'value'),
    State('condition-value-input', 'value'),
    State('dynamic-filters-store', 'data'),  # Добавляем динамические фильтры
    prevent_initial_call=True
)
def search_word_callback(n_clicks,
                         stored_data,
                         sheet_names,
                         filters,
                         search_word,
                         search_cols,
                         sum_cols,
                         condition_col,
                         condition_op,
                         condition_val,
                        dynamic_filters):
    """Выполняет поиск по слову."""
    if not n_clicks:
        raise PreventUpdate
    loading_button = [
        html.I(className="bi bi-search me-1"),
        "Выполнить Поиск",
         dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'}) # Спиннер
    ]

    if not stored_data or not sheet_names:
        return dbc.Alert("Сначала загрузите Excel-файл и выберите листы.", color="warning"), loading_button

    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if dynamic_filters:
          df = apply_dynamic_filters(df, dynamic_filters)
    if df is None or df.empty:
        return dbc.Alert("Нет данных после фильтрации — поиск невозможен.", color="danger"), loading_button

    result = perform_search_by_word(df, search_word, search_cols, sum_cols, condition_col, condition_op, condition_val)

    button_text = [
         html.I(className="bi bi-search me-1"),
        "Выполнить Поиск"
    ]
    return result, button_text
# 18) Выбросы
@app.callback(
    Output('outlier-output', 'children'),
     Output('outlier-button', 'children'), # Изменяем текст
    Input('outlier-button', 'n_clicks'),
    State('outlier-threshold', 'value'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
     State('dynamic-filters-store', 'data'), # Добавляем динамические
    prevent_initial_call=True
)
def outlier_callback(n_clicks, threshold, stored_data, sheet_names, filters, dynamic_filters):
    """Определяет выбросы."""
    if not n_clicks:
        raise PreventUpdate
    loading_button = [
        "Показать выбросы",
        dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'}) # Спиннер
    ]
    if not stored_data or not sheet_names:
        return dbc.Alert("Сначала загрузите Excel-файл и выберите листы.", color="warning"), loading_button
    if not threshold or not 1 <= threshold <= 5:
        return dbc.Alert("Порог для выбросов должен быть в диапазоне от 1 до 5.", color="danger"), loading_button

    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if dynamic_filters:
         df = apply_dynamic_filters(df, dynamic_filters)
    result = perform_outlier_detection(df, threshold)

    button_text = [
         "Показать выбросы"
    ]
    return result, button_text

# 19) СВОДНАЯ ТАБЛИЦА: Генерация + Сохранение в Store
@app.callback(
    Output('pivot-output', 'children'),
    Output('pivot-store', 'data'),  # Сохраняем данные сводной таблицы
     Output('pivot-button', 'children'),# Изменяем текст
    Input('pivot-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('pivot-index', 'value'),
    State('pivot-columns', 'value'),
    State('pivot-values', 'value'),
    State('pivot-aggfunc', 'value'),
    State('dynamic-filters-store', 'data'),# Добавляем динамические
    prevent_initial_call=True
)
def pivot_callback(n_clicks,
                   stored_data,
                   sheet_names,
                   filters,
                   pivot_index,
                   pivot_columns,
                   pivot_values,
                   pivot_aggfunc,
                    dynamic_filters):
    """Создает сводную таблицу."""
    if not n_clicks:
        raise PreventUpdate
    loading_button = [
        "Построить сводную таблицу",
        dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'}) # Спиннер
    ]
    if not stored_data or not sheet_names:
        return [dbc.Alert("Сначала загрузите Excel-файл и выберите лист(ы).", color="warning"), None, loading_button]

    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if dynamic_filters:
         df = apply_dynamic_filters(df, dynamic_filters)
    result = perform_pivot_table(df, pivot_index, pivot_columns, pivot_values, pivot_aggfunc)
    if isinstance(result, dbc.Alert):  # Если вернулся Alert
        return [result, None, loading_button]  # Возвращаем Alert, None для pivot-store, и обычный текст
    elif isinstance(result, tuple) and len(result) == 2: # Если вернулся (DataFrame, html.Div)
        pivot_df, pivot_layout = result
        pivot_reset = pivot_df.reset_index(drop=False) # Сбрасываем индекс
        pivot_data = pivot_reset.to_dict('records')  #  в словарь
        pivot_cols = list(pivot_reset.columns) #  колонки
        pivot_serialized = { # Сериализуем
            "data": pivot_data,
            "columns": pivot_cols
        }
        button_text = [
        "Построить сводную таблицу"
        ]
        return [pivot_layout, pivot_serialized, button_text]  # Возвращаем layout, данные для Store, и обычный текст
    else:
        return [dbc.Alert("Неизвестный формат результата сводной таблицы.", color="danger"), None, loading_button]

# 20) Скачивание сводной таблицы (Pivot) в CSV
@app.callback(
    Output('download-pivot-link', 'href'),
    Input('pivot-store', 'data')  # Следим за изменением pivot-store
)
def download_pivot_csv(pivot_data):
    """
    Генерируем CSV "на лету" из pivot_data (словарь), если он не None
    """
    if not pivot_data:
        return ""  # Если данных нет, возвращаем пустую строку (ссылка неактивна)
    try:
        # Распаковываем данные из словаря
        df_data = pivot_data["data"]
        df_cols = pivot_data["columns"]
        pivot_df = pd.DataFrame(df_data, columns=df_cols) # Собираем DataFrame
        if pivot_df.empty: # Если DataFrame пустой
            return ""
        return (
            "data:text/csv;charset=utf-8,"
            + base64.b64encode(pivot_df.to_csv(index=False, encoding='utf-8').encode()).decode()
        )  # кодируем в base64
    except Exception as e:
        logger.exception(f"Ошибка выгрузки Pivot CSV")
        return ""

# 21) Частоты встречаемости
@app.callback(
    Output('frequency-output', 'children'),
    Output('frequency-button', 'children'), # Изменяем текст
    Input('frequency-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('category-column-dropdown', 'value'),
      State('dynamic-filters-store', 'data'), # Добавляем динамические
    prevent_initial_call=True
)
def frequency_callback(n_clicks, stored_data, sheet_names, filters, category_col, dynamic_filters):
    """ Вычисление частот встречаемости в столбце """
    if not n_clicks:
        raise PreventUpdate
    loading_button = [
       "Показать частоты",
       dbc.Spinner(size="sm", color="light", type="border", spinnerClassName="ms-2", spinner_style={'visibility': 'visible'}) # Спиннер
    ]

    if not stored_data or not sheet_names:
        return dbc.Alert("Нет данных для анализа частот.", color="danger"), loading_button
    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if dynamic_filters:
        df = apply_dynamic_filters(df, dynamic_filters)
    result = calculate_frequencies(df, category_col)

    button_text = [
       "Показать частоты"
    ]
    return result, button_text

# ------------------------------------------------------------------------------
# КОЛЛБЭКИ для динамических фильтров (Добавление и удаление)
# ------------------------------------------------------------------------------

# Callback for Adding a Filter
@app.callback(
    Output('filter-div', 'children', allow_duplicate=True),  # Разрешаем дубликаты
    Output('dynamic-filters-store', 'data', allow_duplicate=True),  # Разрешаем дубликаты
    Input('add-filter-btn', 'n_clicks'),
    State('dynamic-filters-store', 'data'),
    State('sheet-dropdown', 'value'),
    State('stored-data', 'data'),
    prevent_initial_call=True
)
def add_filter(n_clicks, filters, sheet_names, stored_data):
    """Добавляет новый динамический фильтр."""
    if not n_clicks:
        raise PreventUpdate
    if not stored_data or not sheet_names:
        return [], filters  # Возвращаем пустой список, если нет данных

    df = combine_data(stored_data, sheet_names)
    if df is None or df.empty:
        return [], filters

    col_options = [{'label': str(col), 'value': str(col)} for col in df.columns]

    new_filter = {'column': None, 'operator': None, 'value': None}  # Новый фильтр
    updated_filters = filters + [new_filter]  # Добавляем новый фильтр

    # Создаем компоненты фильтров
    filter_components = [
        create_dynamic_filter_component(filter_data, i, col_options)
        for i, filter_data in enumerate(updated_filters)
    ]

    return filter_components, updated_filters  # Возвращаем компоненты и обновленные данные


# Callback for Deleting a Filter
@app.callback(
    Output('filter-div', 'children', allow_duplicate=True), # Разрешаем дубликаты
    Output('dynamic-filters-store', 'data', allow_duplicate=True), # Разрешаем дубликаты
    Input({'type': 'delete-filter-btn', 'index': ALL}, 'n_clicks'), # ALL - все кнопки
    State('dynamic-filters-store', 'data'),
    State('sheet-dropdown', 'value'),
    State('stored-data', 'data'),
    prevent_initial_call=True
)
def delete_dynamic_filter(n_clicks_list, filters, sheet_names, stored_data):
    """Удаляет динамический фильтр."""
    if not any(n_clicks_list):  # Если ни одна кнопка не нажата
        raise PreventUpdate

    ctx = dash.callback_context
    if not ctx.triggered:
        return [], filters

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]  # Получаем ID нажатой кнопки
    index_to_delete = int(re.search(r'index":(\d+)', button_id).group(1))  # Получаем индекс

    # Обновляем список фильтров, удаляя выбранный
    updated_filters = [
         f
         for i, f in enumerate(filters)
        if i != index_to_delete
    ]

    col_options = []
    if stored_data and sheet_names:
        df = combine_data(stored_data, sheet_names)
        if df is not None and not df.empty:
             col_options = [{'label': str(col), 'value': str(col)} for col in df.columns]

    # Создаем компоненты для оставшихся фильтров
    filter_components = [
        create_dynamic_filter_component(filter_data, i, col_options)
        for i, filter_data in enumerate(updated_filters)
    ]
    return filter_components, updated_filters
# Callback for updating dynamic filters in store
@app.callback(
    Output('dynamic-filters-store', 'data', allow_duplicate=True), # Разрешаем дубликаты
    Input({'type': 'filter-column-dropdown', 'index': ALL}, 'value'),
    Input({'type': 'filter-operator-dropdown', 'index': ALL}, 'value'),
    Input({'type': 'filter-value-input', 'index': ALL}, 'value'),
    State('dynamic-filters-store', 'data'),
    prevent_initial_call=True
)
def update_dynamic_filter_data(col_values, op_values, value_values, filters):
    """Обновляет данные динамических фильтров в хранилище."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return filters

    prop_id = ctx.triggered[0]['prop_id']
    index = int(re.search(r'index":(\d+)', prop_id).group(1)) # Получаем индекс из ID

    #  пустой список, если filters не инициализированы
    if not filters or not isinstance(filters, list):
        filters = []

    # Дополняем список фильтров, если нужно
    while len(filters) <= index:
        filters.append({})

    filter_item = filters[index]

    # Обновляем соответствующее поле фильтра
    if 'column' in prop_id:
         filter_item['column'] = col_values[index]
    elif 'operator' in prop_id:
        filter_item['operator'] = op_values[index]
    elif 'value' in prop_id:
        filter_item['value'] = value_values[index]

    filters[index] = filter_item # Обновляем
    return filters

# Update filter data with store data
@app.callback(
    Output('filter-div', 'children'),
    Input('dynamic-filters-store', 'data'),
    State('sheet-dropdown', 'value'),
    State('stored-data', 'data')
)
def update_filters_on_store_change(filters, sheet_names, stored_data):
    """Обновляет компоненты фильтров на основе данных из хранилища."""
    if not filters or not isinstance(filters, list):
        return []  # Возвращаем пустой список

    col_options = []
    if stored_data and sheet_names:
        df = combine_data(stored_data, sheet_names)
        if df is not None and not df.empty:
            col_options = [{'label': str(col), 'value': str(col)} for col in df.columns]

    return [
        create_dynamic_filter_component(filter_data, i, col_options)
        for i, filter_data in enumerate(filters)
    ]

# ------------------------------------------------------------------------------
# Callbacks for enabling/disabling dropdowns
# ------------------------------------------------------------------------------

@app.callback(
    Output('x-axis-dropdown', 'disabled', allow_duplicate=True),  # Разрешаем дубликаты
    Output('y-axis-dropdown', 'disabled', allow_duplicate=True),
    Output('chart-type-dropdown', 'disabled', allow_duplicate=True),
    Output('color-dropdown', 'disabled', allow_duplicate=True),
    Output('symbol-dropdown', 'disabled', allow_duplicate=True),
    Output('adv-filter-column', 'disabled', allow_duplicate=True), # Разрешаем дубликаты
    Output('search-columns-dropdown', 'options', allow_duplicate=True),
    Output('sum-columns-dropdown', 'options', allow_duplicate=True),
    Output('condition-column-dropdown', 'options', allow_duplicate=True),
    Output('category-column-dropdown', 'options', allow_duplicate=True),
    Output('pivot-index', 'options', allow_duplicate=True),
    Output('pivot-columns', 'options', allow_duplicate=True), # Разрешаем дубликаты
    Output('pivot-values', 'options', allow_duplicate=True), # Разрешаем дубликаты
     Output('cluster-columns-dropdown', 'options', allow_duplicate=True),
    Output('date-column-dropdown', 'options', allow_duplicate=True),
     Output('x-axis-dropdown', 'options', allow_duplicate=True),
    Output('y-axis-dropdown', 'options', allow_duplicate=True),
    Input('sheet-dropdown', 'value'),  # Изменение выбранных листов
     State('stored-data', 'data'),
    Input('stored-data', 'data')
)
def enable_dropdowns(sheet_names, stored_data, _):
     if not stored_data or not sheet_names:
          return True, True, True, True, True, True, [], [], [], [], [], [], [], [], [], [], [] # Все отключено
     df = combine_data(stored_data, sheet_names)
     if df is None or df.empty:
        return True, True, True, True, True, True, [], [], [], [], [], [], [], [], [], [], []  # Все отключено

     col_options = [{'label': str(col), 'value': str(col)} for col in df.columns]

     return False, False, False, False, False, False, col_options, col_options, col_options, col_options, col_options, col_options, col_options, col_options, col_options, col_options, col_options # Все включено


# ------------------------------------------------------------------------------
# Callbacks for Upload file
# ------------------------------------------------------------------------------

@app.callback(
    Output('stored-data', 'data'),
    Output('sheet-dropdown', 'options'),
    Output('sheet-dropdown', 'value'),
    Output('upload-message', 'children'),
    Output('x-axis-dropdown', 'options'),
    Output('y-axis-dropdown', 'options'),
    Output('adv-filter-column', 'options'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    State('header-row-input', 'value'),
    State('use-first-row-header', 'value'),
    State('date-format-dropdown', 'value'),
    State('text-handling-dropdown', 'value'),
    State('decimal-separator-dropdown', 'value'),
    State('number-handling-checkbox', 'value'),
    prevent_initial_call=True
)
def load_data(contents, filename, header_row, use_first_row_header, date_format, text_handling, decimal_separator, number_handling_checkbox):
    """Загружает данные из Excel файла."""
    if not contents:
        raise PreventUpdate

    try:
        number_handling = bool(number_handling_checkbox and number_handling_checkbox[0]) if number_handling_checkbox else True

        parsed_data = parse_contents(contents, filename, header_row,
                                     bool(use_first_row_header and use_first_row_header[0]),
                                      date_format, text_handling, decimal_separator, number_handling)

        if 'error' in parsed_data:
            return None, [], None, dbc.Alert(parsed_data['error'], color="danger"), [], [], []

        sheet_options = [{'label': str(sheet), 'value': str(sheet)} for sheet in parsed_data.keys()]
        first_sheet = list(parsed_data.keys())[0] if parsed_data else None

        df = combine_data(parsed_data, first_sheet)
        col_options = [{'label': str(col), 'value': str(col)} for col in df.columns] if df is not None else []
        return parsed_data, sheet_options, [first_sheet] if first_sheet else None,  dbc.Alert(f"Файл '{filename}' успешно загружен.", color="success"), col_options, col_options, col_options
    except Exception as e:
         logger.exception(f"Общая ошибка при загрузке файла")
         return None, [], None, dbc.Alert(f"Ошибка при загрузке файла: {e}", color="danger"), [], [], []

# ------------------------------------------------------------------------------
# Callback for toggle advanced filter
# ------------------------------------------------------------------------------

@app.callback(
    Output("collapse-adv-filter", "is_open"),
    Output('collapse-store', 'data', allow_duplicate=True),
    Input("toggle-adv-filter", "n_clicks"),
    State("collapse-adv-filter", "is_open"),
    State('collapse-store', 'data'),
    prevent_initial_call=True
)
def toggle_adv_filter(n, is_open, stored_data):
    """Скрывает/показывает доп. фильтр."""
    if n:
         stored_data['adv_filter'] = not is_open
         return not is_open, stored_data
    return is_open, stored_data

# ------------------------------------------------------------------------------
# Callback for applying filters to the store
# ------------------------------------------------------------------------------

@app.callback(
    Output('filters-store', 'data'),
    Input('apply-filters-btn', 'n_clicks'),
    State('x-axis-dropdown', 'value'),
    # State('x-min', 'value'), # Убираем
    # State('x-max', 'value'), # Убираем
    State('y-axis-dropdown', 'value'),
    State('y-min', 'value'),
    State('y-max', 'value'),
     State('adv-filter-column', 'value'),
    State('adv-filter-value', 'value'),
     State('dynamic-filters-store', 'data'), # Добавляем динамические
    State('x-date-range', 'start_date'),  # Добавляем начальную дату
    State('x-date-range', 'end_date'),    # Добавляем конечную дату
    # State('y-date-range', 'start_date'),  # Если есть фильтр по датам для Y
    # State('y-date-range', 'end_date'),
    prevent_initial_call=True
)
def apply_filters(n_clicks, x_col, y_col, y_min, y_max, adv_col, adv_val, dynamic_filters,
                    x_start_date, x_end_date): #, y_start_date, y_end_date):
    if not n_clicks:
        raise PreventUpdate
    # Добавили проверку на None, т.к. значения могут быть None при сбросе
    if x_min is not None and x_max is not None and x_min > x_max:
        return dash.no_update, dbc.Alert("Минимальное значение X не может быть больше максимального.", color="warning") #Добавили

    if y_min is not None and y_max is not None and y_min > y_max:
        return dash.no_update, dbc.Alert("Минимальное значение Y не может быть больше максимального.", color="warning")

    return {
        'x_col': x_col,
        'x_min': x_min,  #  используем x_min и x_max, если они числовые
        'x_max': x_max,
        'x_start_date': x_start_date,  # Добавляем начальную и конечную даты
        'x_end_date': x_end_date,
        'y_col': y_col,
        'y_min': y_min,
        'y_max': y_max,
        'adv_col': adv_col,
        'adv_val': adv_val,
        'dynamic_filters': dynamic_filters, # Добавляем динамические фильтры
        # 'y_start_date': y_start_date,  # Если есть фильтр по датам для Y
        # 'y_end_date': y_end_date
    }

# ------------------------------------------------------------------------------
# Callback for Resetting filters
# ------------------------------------------------------------------------------

@app.callback(
    Output('x-axis-dropdown', 'value'), # Сбрасываем X
    Output('y-axis-dropdown', 'value'), # Сбрасываем Y
    Output('x-min', 'value'),
    Output('x-max', 'value'),
    Output('y-min', 'value'),
    Output('y-max', 'value'),
     Output('adv-filter-column', 'value'), # Сбрасываем доп. фильтр
    Output('adv-filter-value', 'value'),
     Output('dynamic-filters-store', 'data', allow_duplicate=True), # Сбрасываем динамические
    Output('x-date-range', 'start_date'),  # Сбрасываем начальную дату
    Output('x-date-range', 'end_date'),    # Сбрасываем конечную дату
    # Output('y-date-range', 'start_date'),  # Если есть для Y
    # Output('y-date-range', 'end_date'),
    Input('reset-filters-btn', 'n_clicks'),
     prevent_initial_call=True
)
def reset_filters(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return None, None, None, None, None, None, None, None, [], None, None  # , None, None

# ------------------------------------------------------------------------------
# Callback for toggle analytics
# ------------------------------------------------------------------------------

@app.callback(
    Output("collapse-analytics", "is_open"),
    Output('collapse-store', 'data', allow_duplicate=True),
    Input("toggle-analytics", "n_clicks"),
    State("collapse-analytics", "is_open"),
    State('collapse-store', 'data'),
    prevent_initial_call=True
)
def toggle_analytics(n, is_open, stored_data):
    """Скрывает/показывает секцию аналитики."""
    if n:
        stored_data['analytics'] = not is_open
        return not is_open, stored_data
    return is_open, stored_data

# Коллбэк, который устанавливает начальное состояние панелей
@app.callback(
    Output('collapse-analytics', 'is_open', allow_duplicate='initial_duplicate'),
    Output('collapse-adv-filter', 'is_open', allow_duplicate='initial_duplicate'),
    Input('collapse-store', 'data'),
    prevent_initial_call='initial_duplicate'
)
def set_initial_collapses(stored_data):
  return stored_data.get('analytics', False), stored_data.get('adv_filter', False)
# ------------------------------------------------------------------------------
# ЗАПУСК
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    app.run_server(debug=True)