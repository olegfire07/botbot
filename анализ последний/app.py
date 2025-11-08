import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import base64
import io
from dash import dash_table
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from prophet import Prophet
from dash.exceptions import PreventUpdate
from flask_caching import Cache
import logging
import datetime

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
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
app.title = "Быстрый Анализ файлов Excel (.xlsx) от Олега"
server = app.server

# ------------------------------------------------------------------------------
# КЭШ
# ------------------------------------------------------------------------------
cache = Cache(app.server, config={
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 300
})

# ------------------------------------------------------------------------------
# ФУНКЦИИ ЧТЕНИЯ И СЕРИАЛИЗАЦИИ ДАННЫХ
# ------------------------------------------------------------------------------
def parse_contents(contents, filename):
    """
    Считываем Excel-файл (xls, xlsx), конвертируем datetime-столбцы
    в текст (формат ДД.ММ.ГГГГ), сериализуем в словарь.
    """
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        if 'xls' in filename:
            df = pd.read_excel(io.BytesIO(decoded), sheet_name=None, parse_dates=True)
        else:
            return {'error': f'Неподдерживаемый формат файла: {filename}'}
    except Exception as e:
        return {'error': f'Ошибка при обработке файла {filename}: {e}'}

    df_serialized = {}
    for sheet, data in df.items():
        df_sheet = pd.DataFrame(data)
        # Преобразуем datetime-столбцы в строки (ДД.ММ.ГГГГ)
        date_cols = df_sheet.select_dtypes(include=['datetime', 'datetimetz']).columns
        for col in date_cols:
            df_sheet[col] = df_sheet[col].dt.strftime('%d.%m.%Y')
        # Убедимся, что названия столбцов являются строками
        df_sheet.columns = df_sheet.columns.astype(str)
        # Преобразуем название листа в строку
        sheet_str = str(sheet)
        df_serialized[sheet_str] = df_sheet.to_dict('records')
        logger.debug(f"Sheet '{sheet_str}' has been parsed with {len(df_serialized[sheet_str])} records.")
    return df_serialized

@cache.memoize()
def combine_data(stored_data, sheet_names):
    """
    Объединяем несколько листов в один DataFrame (конкатенация).
    Преобразуем '%d.%m.%Y' обратно в datetime.
    """
    if not stored_data or not sheet_names:
        return None

    # List comprehension для сбора DataFrame
    df_list = [
        pd.DataFrame(stored_data[sheet])
        for sheet in sheet_names
        if sheet in stored_data
    ]
    if not df_list:
        return None

    # Удаляем лишние обратные слэши в названиях столбцов
    for df_ in df_list:
        df_.columns = df_.columns.astype(str).str.replace(r'\\', '', regex=True)

    combined_df = pd.concat(df_list, ignore_index=True)

    # Преобразуем потенциальные даты обратно (ДД.ММ.ГГГГ -> datetime)
    date_cols = combined_df.select_dtypes(include=['object']).columns
    for col in date_cols:
        try:
            combined_df[col] = pd.to_datetime(combined_df[col], format='%d.%m.%Y', dayfirst=True, errors='ignore')
        except:
            continue

    logger.info(f"Объединённый DataFrame: {combined_df.shape[0]} строк, {combined_df.shape[1]} столбцов.")
    return combined_df

# ------------------------------------------------------------------------------
# ФУНКЦИИ ФИЛЬТРАЦИИ
# ------------------------------------------------------------------------------
def apply_all_filters(df, filters):
    """
    Набор фильтров (x_min, x_max, y_min, y_max, adv_col>adv_val).
    """
    if df is None or df.empty:
        return df
    
    x_col = filters.get('x_col')
    x_min = filters.get('x_min')
    x_max = filters.get('x_max')
    y_col = filters.get('y_col')
    y_min = filters.get('y_min')
    y_max = filters.get('y_max')
    adv_col = filters.get('adv_col')
    adv_val = filters.get('adv_val')

    # Фильтр по X
    if x_col and x_col in df.columns:
        if x_min is not None:
            df = df[df[x_col] >= x_min]
        if x_max is not None:
            df = df[df[x_col] <= x_max]

    # Фильтр по Y
    if y_col and y_col in df.columns:
        if y_min is not None:
            df = df[df[y_col] >= y_min]
        if y_max is not None:
            df = df[df[y_col] <= y_max]

    # Доп. фильтр (adv_col > adv_val) - объединено условие
    if adv_col and adv_col in df.columns and adv_val is not None and pd.api.types.is_numeric_dtype(df[adv_col]):
        df = df[df[adv_col] > adv_val]

    logger.info(f"После фильтров: {df.shape[0]} строк, {df.shape[1]} столбцов.")
    return df

# ------------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ, ВЫНЕСЕННЫЕ ПО СОВЕТУ SOURCERY
# ------------------------------------------------------------------------------
def _perform_regression_with_cv(df, x_col, y_col):
    """
    Вспомогательный метод для линейной регрессии с кросс-валидацией (cv=5).
    """
    df_reg = df[[x_col, y_col]].dropna()
    X = df_reg[[x_col]]
    y = df_reg[y_col]
    model = LinearRegression()
    cv_scores = cross_val_score(model, X, y, cv=5, scoring='r2')
    cv_mean_r2 = np.mean(cv_scores)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    slope = model.coef_[0]
    intercept = model.intercept_

    return html.Div([
        html.H4("Линейная Регрессия (с кросс-валидацией)", className="text-secondary"),
        html.P(f"Средний R² (cv=5): {cv_mean_r2:.4f}"),
        html.P(f"Перехват (Intercept): {intercept:.4f}"),
        html.P(f"Коэффициент (Slope): {slope:.4f}"),
        html.P(f"MSE на тесте: {mse:.4f}"),
        html.P(f"R² на тесте: {r2:.4f}")
    ])

def _perform_simple_linear_regression(df, x_col, y_col, test_size):
    """
    Вспомогательный метод для простой линейной регрессии (train_test_split, fit/predict).
    """
    df_ = df[[x_col, y_col]].dropna()
    X = df_[[x_col]]
    y = df_[y_col]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    return html.Div([
        html.H4("Результаты (простая лин. регрессия)", className="text-info"),
        html.P(f"MSE: {mse:.2f}"),
        html.P(f"R²: {r2:.2f}")
    ])

def _perform_rf_regression(df, x_col, y_col, test_size):
    """
    Вспомогательный метод для RandomForestRegressor.
    """
    df_ = df[[x_col, y_col]].dropna()
    X = df_[[x_col]]
    y = df_[y_col]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    return html.Div([
        html.H4("Результаты Random Forest", className="text-info"),
        html.P(f"MSE: {mse:.2f}"),
        html.P(f"R²: {r2:.2f}")
    ])

def _perform_pca_analysis(numeric_df, n_components):
    """
    Вспомогательный метод для PCA-анализа (стандартизация, построение графиков).
    """
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    numeric_scaled = scaler.fit_transform(numeric_df)
    pca = PCA(n_components=n_components)
    pcs = pca.fit_transform(numeric_scaled)
    explained_variance = pca.explained_variance_ratio_
    pc_cols = [f'ПК{i+1}' for i in range(n_components)]
    df_pca = pd.DataFrame(data=pcs, columns=pc_cols)

    fig_variance = px.bar(
        x=pc_cols, y=explained_variance,
        labels={'x': 'Компоненты', 'y': 'Доля дисперсии'},
        title="Объяснённая дисперсия (PCA)",
        color_discrete_sequence=['#636EFA']
    )
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

def _perform_kmeans_clustering(num_clusters, numeric_df, selected_columns):
    """
    Вспомогательный метод для K-Means-кластеризации.
    """
    kmeans = KMeans(n_clusters=num_clusters, random_state=42)
    clusters = kmeans.fit_predict(numeric_df)
    df_clustered = numeric_df.copy()
    df_clustered["Кластер"] = clusters.astype(str)
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

# ------------------------------------------------------------------------------
# ФУНКЦИИ АНАЛИТИКИ И ВИЗУАЛИЗАЦИИ
# ------------------------------------------------------------------------------
def create_figure(df, x_col, y_col, chart_type, color_col, symbol_col):
    """
    Строим различные типы графиков: scatter, histogram, line, bar, box, heatmap, pie, violin, area, bubble.
    """
    if df is None or x_col not in df.columns or (y_col and y_col not in df.columns):
        return go.Figure().update_layout(title="Выберите корректные столбцы для графика")

    try:
        if chart_type == 'scatter' and y_col:
            fig = px.scatter(
                df, x=x_col, y=y_col,
                color=color_col,
                symbol=symbol_col,
                title=f"Точечный график (Scatter): {y_col} от {x_col}",
                labels={x_col: x_col, y_col: y_col, color_col: "Цвет", symbol_col: "Символ"},
                hover_data=df.columns
            )
            fig.update_traces(hovertemplate='<b>%{x}</b><br>%{y}<extra></extra>')
        elif chart_type == 'histogram':
            fig = px.histogram(
                df, x=x_col,
                title=f"Гистограмма (Histogram): {x_col}",
                labels={x_col: x_col}
            )
            fig.update_traces(hovertemplate='Значение: %{x}, Кол-во: %{y}')
        elif chart_type == 'line' and y_col:
            fig = px.line(
                df, x=x_col, y=y_col,
                title=f"Линейный график (Line): {y_col} от {x_col}",
                labels={x_col: x_col, y_col: y_col},
                markers=True
            )
        elif chart_type == 'bar' and y_col:
            fig = px.bar(
                df, x=x_col, y=y_col,
                title=f"Столбчатая (Bar): {y_col} от {x_col}",
                labels={x_col: x_col, y_col: y_col}
            )
        elif chart_type == 'box' and y_col:
            fig = px.box(
                df, x=x_col, y=y_col,
                title=f"Диаграмма размаха (Box): {y_col} от {x_col}",
                labels={x_col: x_col, y_col: y_col},
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
            if x_col in df.columns:
                fig = px.pie(
                    df, names=x_col,
                    title=f"Круговая (Pie): {x_col}",
                    labels={x_col: x_col},
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
                labels={x_col: x_col, y_col: y_col, color_col: "Цвет"},
                hover_data=df.columns
            )
        elif chart_type == 'area' and y_col:
            fig = px.area(
                df, x=x_col, y=y_col,
                color=color_col,
                title=f"Площадная диаграмма (Area): {y_col} от {x_col}",
                labels={x_col: x_col, y_col: y_col, color_col: "Цвет"},
                hover_data=df.columns
            )
        elif chart_type == 'bubble' and y_col:
            fig = px.scatter(
                df, x=x_col, y=y_col,
                color=color_col,
                size=y_col,
                title=f"Пузырьковый график (Bubble): {y_col} от {x_col}",
                labels={x_col: x_col, y_col: y_col, color_col: "Цвет", "size": "Размер"},
                hover_data=df.columns
            )
        else:
            return go.Figure().update_layout(title="Неподходящий тип графика или не указаны нужные столбцы")
    except Exception as e:
        logger.error(f"Ошибка построения графика: {e}")
        return go.Figure().update_layout(title=f"Ошибка при построении графика: {e}")

    fig.update_layout(
        xaxis_title=f"Ось X: {x_col}",
        yaxis_title=f"Ось Y: {y_col}" if y_col else "",
        legend_title="Легенда",
        hovermode="closest"
    )
    return fig

def create_data_table(df):
    """
    Преобразуем DataFrame -> (columns, data) для dash_table
    """
    if df is None or df.empty:
        return [], []
    columns = [{"name": str(i), "id": str(i)} for i in df.columns]
    data = df.to_dict('records')
    return columns, data

def perform_statistical_analysis(df):
    """
    Обычная статистика describe() с переименованными колонками.
    """
    if df is None or df.empty:
        return dbc.Alert("Нет данных для статистического анализа.", color="danger")
    try:
        stats = df.describe().T.reset_index()
        stats.rename(columns={
            'index': 'Столбец',
            'count': 'Количество',
            'mean': 'Среднее',
            'std': 'Станд. отклонение',
            'min': 'Минимум',
            '25%': '25-й перцентиль',
            '50%': 'Медиана',
            '75%': '75-й перцентиль',
            'max': 'Максимум'
        }, inplace=True)
        stats_table = dash_table.DataTable(
            columns=[{"name": i, "id": i} for i in stats.columns],
            data=stats.to_dict('records'),
            style_table={'overflowX': 'auto'},
            style_cell={
                'whiteSpace': 'normal',
                'textAlign': 'left'
            },
            page_size=20,
            style_as_list_view=True
        )
        return html.Div([
            html.H4("Основная статистика", className="text-primary mt-3"),
            stats_table
        ])
    except Exception as e:
        return dbc.Alert(f"Ошибка статистического анализа: {e}", color="danger")

def perform_regression_analysis(df, x_col, y_col, chart_type):
    """
    Линейная регрессия + cross_val_score (cv=5).
    """
    if df is None or not x_col or not y_col:
        return html.Div("Укажите столбцы X и Y для регрессии.")
    if chart_type not in ['scatter', 'line', 'bar', 'box']:
        return html.Div("Регрессия применяется к Scatter/Line/Bar/Box.")
    if not pd.api.types.is_numeric_dtype(df[y_col]):
        return dbc.Alert("Столбец Y должен быть числовым.", color="danger")
    if not pd.api.types.is_numeric_dtype(df[x_col]):
        return dbc.Alert("Столбец X должен быть числовым.", color="danger")
    try:
        # Логику регрессии выносим во вспомогательную функцию:
        return _perform_regression_with_cv(df, x_col, y_col)
    except Exception as e:
        return dbc.Alert(f"Ошибка регрессии: {e}", color="danger")

def perform_forecast(df, date_col, y_col, forecast_period, freq):
    """
    Прогноз Prophet. date_col -> ds, y_col -> y.
    """
    if df is None or not date_col or not y_col or not pd.api.types.is_numeric_dtype(df[y_col]):
        return html.Div("Для прогноза укажите корректные столбцы (Дата, Y).")
    try:
        df_prophet = df[[date_col, y_col]].dropna(subset=[date_col, y_col]).copy()
        df_prophet.rename(columns={date_col: 'ds', y_col: 'y'}, inplace=True)
        df_prophet['ds'] = pd.to_datetime(df_prophet['ds'], format='%d.%m.%Y', dayfirst=True, errors='coerce')
        df_prophet.dropna(subset=['ds'], inplace=True)
        if df_prophet.empty:
            return dbc.Alert("Все даты некорректны или отсутствуют.", color="danger")

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

        return html.Div([
            html.H4("Прогнозирование (Prophet)", className="text-success"),
            dcc.Graph(figure=fig)
        ])
    except Exception as e:
        return dbc.Alert(f"Ошибка при прогнозе: {e}", color="danger")

def perform_machine_learning(df, x_col, y_col, test_size=0.2):
    """
    Простая лин. регрессия (train_test_split, fit/predict).
    """
    if df is None or not x_col or not y_col:
        return dbc.Alert("Не указаны X и Y для обучения.", color="danger")
    if not pd.api.types.is_numeric_dtype(df[x_col]) or not pd.api.types.is_numeric_dtype(df[y_col]):
        return dbc.Alert("X и Y должны быть числовыми.", color="danger")
    try:
        # Логику выносим во вспомогательную функцию:
        return _perform_simple_linear_regression(df, x_col, y_col, test_size)
    except Exception as e:
        return dbc.Alert(f"Ошибка обучения: {e}", color="danger")

def perform_random_forest_regression(df, x_col, y_col, test_size=0.2):
    """
    RandomForestRegressor (X, Y числовые).
    """
    if df is None or not x_col or not y_col:
        return dbc.Alert("Укажите X и Y для Random Forest.", color="danger")
    if not pd.api.types.is_numeric_dtype(df[x_col]) or not pd.api.types.is_numeric_dtype(df[y_col]):
        return dbc.Alert("X и Y должны быть числовыми для RF.", color="danger")
    try:
        # Логику выносим во вспомогательную функцию:
        return _perform_rf_regression(df, x_col, y_col, test_size)
    except Exception as e:
        return dbc.Alert(f"Ошибка Random Forest: {e}", color="danger")

def perform_pca(df, n_components):
    """
    PCA: Преобразование числовых столбцов, вывод bar-графика дисперсии и scatter (PC1 vs PC2).
    """
    if df is None or df.empty:
        return dbc.Alert("Нет данных для PCA.", color="danger")
    numeric_df = df.select_dtypes(include=['number']).dropna()
    if numeric_df.shape[1] < 2:
        return dbc.Alert("Недостаточно числовых столбцов для PCA.", color="danger")
    try:
        # Логику выносим во вспомогательную функцию:
        return _perform_pca_analysis(numeric_df, n_components)
    except Exception as e:
        return dbc.Alert(f"Ошибка PCA: {e}", color="danger")

def perform_clustering(df, selected_columns, num_clusters):
    """
    K-Means кластеризация. Нужно >= 2 числовых столбца.
    """
    if df is None or not selected_columns or len(selected_columns) < 2:
        return dbc.Alert("Выберите >=2 столбца для кластеризации.", color="danger")
    numeric_df = df[selected_columns].select_dtypes(include=['number']).dropna()
    if numeric_df.empty:
        return dbc.Alert("Нет числовых данных для кластеризации.", color="danger")
    try:
        # Логику выносим во вспомогательную функцию:
        return _perform_kmeans_clustering(num_clusters, numeric_df, selected_columns)
    except Exception as e:
        return dbc.Alert(f"Ошибка кластеризации: {e}", color="danger")

# ------------------------------------------------------------------------------
# ПОИСК ПО СЛОВУ
# ------------------------------------------------------------------------------
def perform_search_by_word(df, search_word, search_cols, sum_cols, condition_col, condition_op, condition_val):
    """
    Ищем search_word в search_cols, выводим таблицу + опционально суммируем sum_cols.
    Применяем дополнительные условия, если они заданы.
    """
    if df is None or df.empty:
        return dbc.Alert("Нет данных для поиска.", color="danger")
    if not search_word or not search_cols:
        return dbc.Alert("Укажите слово и выберите столбцы для поиска.", color="warning")
    
    # Фильтрация по условию, если задано
    if condition_col and condition_op and condition_val:
        try:
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
            return dbc.Alert(f"Ошибка при применении условия: {e}", color="danger")
    
    # Поиск слова в выбранных столбцах
    mask = pd.Series([False]*len(df))
    for col in search_cols:
        mask = mask | df[col].astype(str).str.contains(search_word, case=False, na=False)
    found_df = df[mask]
    rows_found = found_df.shape[0]
    
    sum_results = {}
    if sum_cols:
        for col in sum_cols:
            if pd.api.types.is_numeric_dtype(df[col]):
                sum_results[col] = found_df[col].sum()
            else:
                sum_results[col] = "Не числовой столбец"
    
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

# ------------------------------------------------------------------------------
# ДОКУМЕНТАЦИЯ
# ------------------------------------------------------------------------------
def create_documentation():
    """
    Создаёт раздел документации для приложения.
    """
    documentation_text = """
    ## Документация

    **Быстрый Анализ файлов Excel** — мощный инструмент для анализа данных из Excel-файлов. Ниже приведено краткое руководство по использованию приложения.

    ### Загрузка данных
    1. **Загрузка файла**: Нажмите на область загрузки и выберите Excel-файл (.xls или .xlsx).
    2. **Выбор листов**: После загрузки выберите один или несколько листов для анализа.

    ### Фильтрация данных
    - **Столбец X и Y**: Выберите столбцы для осей X и Y на графике.
    - **Минимальные и максимальные значения**: Установите диапазоны для выбранных столбцов.
    - **Дополнительный фильтр**: При необходимости можно добавить дополнительный фильтр, выбрав числовой столбец и указав пороговое значение.

    ### Визуализация
    - **Тип графика**: Выберите тип графика из выпадающего списка (Scatter, Histogram, Line, Bar, Box, Heatmap, Pie, Violin, Area, Bubble).
    - **Цвет и Символ**: При необходимости выберите столбцы для цветового кодирования и различения символов на графике.
    - **Обновление графика**: Нажмите кнопку "Обновить Визуализацию" для отображения графика.

    ### Анализ данных
    - **Статистика**: Просмотрите основную статистику данных.
    - **Корреляционная матрица**: Анализируйте корреляции между числовыми столбцами.
    - **Линейная Регрессия**: Выполните линейную регрессию с кросс-валидацией.
    - **Прогнозирование (Prophet)**: Постройте прогноз на основе временных рядов.
    - **Машинное Обучение**: Выполните простую линейную регрессию или Random Forest для предсказаний.
    - **PCA и Кластеризация**: Проведите анализ главных компонентов и кластеризацию данных.

    ### Расширенный Поиск по Слову
    - **Поиск**: Введите слово для поиска.
    - **Столбцы для поиска**: Выберите один или несколько столбцов, в которых будет производиться поиск.
    - **Столбцы для суммирования**: При необходимости выберите один или несколько столбцов для суммирования найденных значений.
    - **Дополнительные условия**:
        - **Столбец**: Выберите столбец, на основе которого будет применяться условие.
        - **Оператор**: Выберите оператор сравнения (равно, не равно, больше и т.д.).
        - **Значение**: Укажите значение или текст для условия.
    - **Выполнение поиска**: Нажмите кнопку "Выполнить Поиск" для отображения результатов.

    ### Загрузка результатов
    - **Скачать CSV**: После применения фильтров вы можете скачать отфильтрованные данные в формате CSV.

    **Примечание**: Все интерактивные элементы снабжены всплывающими подсказками для облегчения использования приложения.
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
# LAYOUT (Одна страница)
# ------------------------------------------------------------------------------
app.layout = dbc.Container([
    # Заголовок приложения
    html.Div([
        html.H1("Быстрый Анализ файлов Excel (ФИАНИТ-ЛОМБАРД)", 
                className="text-center my-4", 
                style={"fontWeight": "bold", "fontSize": "2.5rem"}),
        html.H5("Кластеризация, Поиск, и Прочая Аналитика (от Олега)", 
                className="text-center text-muted mb-4"),
    ]),

    # Блок загрузки
    dbc.Card([
        dbc.CardHeader([
            html.H4("Загрузка Excel-файла"),
            # Всплывающая подсказка на иконке
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
        ])
    ], style={"marginBottom": "30px"}),

    # Фильтры
    dbc.Card([
        dbc.CardHeader(html.H4("Фильтры и Параметры", className="text-white"), className="bg-primary"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Столбец X:", className="fw-bold"),
                    dcc.Dropdown(id='x-axis-dropdown', options=[], value=None, placeholder="Выберите столбец X"),
                    dbc.Tooltip("Столбец для оси X в визуализации", target='x-axis-dropdown'),
                    dbc.InputGroup([
                        dbc.InputGroupText("Мин X"),
                        dbc.Input(id='x-min', type='number', placeholder="Минимальное значение")
                    ], className='my-1'),
                    dbc.InputGroup([
                        dbc.InputGroupText("Макс X"),
                        dbc.Input(id='x-max', type='number', placeholder="Максимальное значение")
                    ], className='my-1'),
                ], width=6),
                dbc.Col([
                    html.Label("Столбец Y:", className="fw-bold"),
                    dcc.Dropdown(id='y-axis-dropdown', options=[], value=None, placeholder="Выберите столбец Y"),
                    dbc.Tooltip("Столбец для оси Y в визуализации", target='y-axis-dropdown'),
                    dbc.InputGroup([
                        dbc.InputGroupText("Мин Y"),
                        dbc.Input(id='y-min', type='number', placeholder="Минимальное значение")
                    ], className='my-1'),
                    dbc.InputGroup([
                        dbc.InputGroupText("Макс Y"),
                        dbc.Input(id='y-max', type='number', placeholder="Максимальное значение")
                    ], className='my-1'),
                ], width=6),
            ], className='mb-2'),

            dbc.Button("Доп. Фильтр (скрыть/показать)", id="toggle-adv-filter", color="secondary", outline=True, className="mb-2"),
            dbc.Collapse(
                dbc.Card(dbc.CardBody([
                    html.Label("Числовой столбец (> значение):"),
                    dcc.Dropdown(id='adv-filter-column', options=[], value=None, placeholder="Выберите столбец"),
                    dbc.Input(id='adv-filter-value', type='number', placeholder='Пороговое значение...'),
                ])),
                id="collapse-adv-filter",
                is_open=False
            ),

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

    # Визуализация и Таблица
    dbc.Card([
        dbc.CardHeader(html.H4("Визуализация и Таблица", className="text-white"), className="bg-success"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Тип графика:", className="fw-bold"),
                    dcc.Dropdown(
                        id='chart-type-dropdown',
                        options=[
                            {'label': 'Точечный (Scatter)', 'value': 'scatter'},
                            {'label': 'Гистограмма (Histogram)', 'value': 'histogram'},
                            {'label': 'Линейный (Line)', 'value': 'line'},
                            {'label': 'Столбчатая (Bar)', 'value': 'bar'},
                            {'label': 'Размах (Box)', 'value': 'box'},
                            {'label': 'Тепловая карта (Heatmap)', 'value': 'heatmap'},
                            {'label': 'Круговая (Pie)', 'value': 'pie'},
                            {'label': 'Скрипичная диаграмма (Violin)', 'value': 'violin'},
                            {'label': 'Площадная диаграмма (Area)', 'value': 'area'},
                            {'label': 'Пузырьковый график (Bubble)', 'value': 'bubble'},
                        ],
                        value='scatter', 
                        placeholder="Выберите тип..."
                    ),
                    dbc.Tooltip("Выберите тип графика для отображения данных", target='chart-type-dropdown'),
                ], width=6),
                dbc.Col([
                    html.Label("Цвет (Color):", className="fw-bold"),
                    dcc.Dropdown(id='color-dropdown', options=[], value=None, placeholder="Колонка для цвета"),
                    dbc.Tooltip("Выберите столбец для цветового кодирования данных", target='color-dropdown'),
                    html.Label("Символ (Symbol):", className='mt-2 fw-bold'),
                    dcc.Dropdown(id='symbol-dropdown', options=[], value=None, placeholder="Колонка для символов"),
                    dbc.Tooltip("Выберите столбец для различения символов на графике", target='symbol-dropdown'),
                ], width=6),
            ]),

            dbc.Button([
                html.I(className="bi bi-arrow-clockwise me-1"),
                "Обновить Визуализацию"
            ], id='update-button', color='success', className='my-3'),

            html.Div(id='data-info', className='text-info mb-2', style={"fontSize": "0.9rem"}),

            dcc.Graph(id='data-graph'),

            html.H5("Таблица данных:", className='mt-3 text-primary'),
            dash_table.DataTable(
                id='data-table',
                columns=[],
                data=[],
                style_table={'overflowX': 'auto', 'height': '400px', 'overflowY': 'scroll'},
                style_cell={
                    'minWidth': '100px', 'width': '150px', 'maxWidth': '300px',
                    'whiteSpace': 'normal'
                },
                filter_action='native',
                sort_action='native',
                sort_mode='multi'
            ),
            html.A(
                'Скачать CSV',
                id='download-link',
                download="filtered_data.csv",
                href="",
                target="_blank",
                className='btn btn-secondary my-2'
            )
        ])
    ], style={"marginBottom": "30px"}),

    # Расширенный Поиск по слову
    dbc.Card([
        dbc.CardHeader(html.H4("Расширенный Поиск по Слову", className="text-white"), className="bg-info"),
        dbc.CardBody([
            html.Label("Слово для поиска:", className="fw-bold"),
            dbc.Input(id='search-word', type='text', placeholder='Введите слово...'),
            dbc.Tooltip("Введите слово для поиска в выбранных столбцах", target='search-word'),
            html.Br(),
            
            html.Label("Столбцы для поиска:", className="fw-bold"),
            dcc.Dropdown(
                id='search-columns-dropdown',
                options=[], 
                value=None, 
                placeholder="Выберите столбцы...",
                multi=True
            ),
            dbc.Tooltip("Выберите один или несколько столбцов, в которых будет производиться поиск", target='search-columns-dropdown'),
            html.Br(),
            
            html.Label("Столбцы для суммирования (опционально):", className="fw-bold"),
            dcc.Dropdown(
                id='sum-columns-dropdown',
                options=[], 
                value=None, 
                placeholder="Выберите столбцы для суммирования...",
                multi=True
            ),
            dbc.Tooltip("Выберите один или несколько столбцов для вычисления суммы найденных значений", target='sum-columns-dropdown'),
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
            dbc.Tooltip("Задайте условие фильтрации: столбец, оператор и значение", target='condition-value-input'),
            html.Br(),
            
            dbc.Button([
                html.I(className="bi bi-search me-1"),
                "Выполнить Поиск"
            ], id='search-button', color='info'),
            html.Div(id='search-output', className='mt-3')
        ])
    ], style={"marginBottom": "30px"}),

    # Расширенный анализ и модели
    dbc.Card([
        dbc.CardHeader(html.H4("Расширенный Анализ и Модели", className="text-white"), className="bg-secondary"),
        dbc.CardBody([
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
                    dbc.Tooltip("Выберите столбец, содержащий даты для прогноза", target='date-column-dropdown'),
                    dbc.InputGroup([
                        dbc.InputGroupText("Период (шаги):"),
                        dbc.Input(id='forecast-period', type='number', value=12, min=1, max=120),
                        dbc.InputGroupText("Частота:"),
                        dcc.Dropdown(
                            id='forecast-freq',
                            options=[
                                {'label': 'Дни (D)', 'value': 'D'},
                                {'label': 'Недели (W)', 'value': 'W'},
                                {'label': 'Месяцы (MS)', 'value': 'MS'},
                            ],
                            value='MS',
                            style={'width': '100px'}
                        ),
                    ], className='my-2'),
                    html.Div(id='forecast-output', className='mb-3'),

                    html.H5("Машинное Обучение (Лин.рег)", className="text-muted"),
                    dbc.InputGroup([
                        dbc.InputGroupText("test_size:"),
                        dbc.Input(id='ml-test-size', type='number', value=0.2, min=0.05, max=0.95, step=0.05),
                        dbc.Button('Запустить', id='ml-button', color='primary', className='ms-2')
                    ], className='my-3'),
                    html.Div(id='ml-output'),

                    html.H5("Random Forest", className="text-muted"),
                    dbc.InputGroup([
                        dbc.InputGroupText("test_size:"),
                        dbc.Input(id='rf-test-size', type='number', value=0.2, min=0.05, max=0.95, step=0.05),
                        dbc.Button('Запустить RF', id='rf-button', color='info', className='ms-2')
                    ], className='my-3'),
                    html.Div(id='rf-output'),
                ], width=6),
            ])
        ])
    ], style={"marginBottom": "30px"}),

    # PCA и Кластеризация
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
                    dbc.Tooltip("Выберите количество главных компонент для анализа", target='pca-components'),
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
                    dbc.Tooltip("Выберите два или более числовых столбца для кластеризации", target='cluster-columns-dropdown'),
                    html.Label("Количество кластеров:", className='mt-2 fw-bold'),
                    dbc.Input(id='num-clusters', type='number', value=3, min=2, step=1, style={'width': '100px'}),
                    dbc.Tooltip("Укажите количество кластеров для алгоритма K-Means", target='num-clusters'),
                    dbc.Button('Выполнить', id='cluster-button', color='secondary', className='mt-2'),
                    html.Div(id='cluster-output', className='mt-3')
                ], width=6),
            ])
        ])
    ], style={"marginBottom": "30px"}),

    # Документация
    create_documentation()

], fluid=True)

# ------------------------------------------------------------------------------
# КОЛЛБЭКИ
# ------------------------------------------------------------------------------

# Обработка загрузки файла
@app.callback(
    Output('stored-data', 'data'),
    Output('sheet-dropdown', 'options'),
    Output('sheet-dropdown', 'value'),
    Output('upload-message', 'children'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def handle_upload(contents, filename):
    if contents is None:
        raise PreventUpdate
    parsed = parse_contents(contents, filename)
    logger.debug(f"Parsed data: {parsed}")
    if 'error' in parsed:
        return {}, [], None, dbc.Alert(parsed['error'], color='danger')

    sheets = list(parsed.keys())
    opts = [{'label': s, 'value': s} for s in sheets]
    default_sheet = sheets[0] if sheets else None
    return parsed, opts, default_sheet, dbc.Alert("Файл успешно загружен!", color='success')

# Обновление опций для осей X, Y, дополнительных фильтров и столбца дат
@app.callback(
    Output('x-axis-dropdown', 'options'),
    Output('x-axis-dropdown', 'value'),
    Output('y-axis-dropdown', 'options'),
    Output('y-axis-dropdown', 'value'),
    Output('adv-filter-column', 'options'),
    Output('adv-filter-column', 'value'),
    Output('date-column-dropdown', 'options'),
    Output('date-column-dropdown', 'value'),
    Input('sheet-dropdown', 'value'),
    State('stored-data', 'data')
)
def update_xy_options(sheet_names, stored_data):
    if not stored_data or not sheet_names:
        return [], None, [], None, [], None, [], None
    df = combine_data(stored_data, sheet_names)
    if df is None or df.empty:
        return [], None, [], None, [], None, [], None

    cols = df.columns
    col_opts = [{'label': c, 'value': c} for c in cols]

    # Определяем потенциальные столбцы дат
    date_opts = []
    for c in cols:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            date_opts.append({'label': c, 'value': c})
        else:
            sample = df[c].dropna().head(10)
            try:
                pd.to_datetime(sample, format='%d.%m.%Y', dayfirst=True, errors='raise')
                date_opts.append({'label': c, 'value': c})
            except:
                continue

    x_val = cols[0] if len(cols) > 0 else None
    y_val = cols[1] if len(cols) > 1 else None
    adv_val = None

    return (
        col_opts, x_val,   # x-axis
        col_opts, y_val,   # y-axis
        col_opts, adv_val, # adv-filter
        date_opts, (date_opts[0]['value'] if date_opts else None)
    )

# Обновление опций для цветового и символьного кодирования
@app.callback(
    Output('color-dropdown', 'options'),
    Output('color-dropdown', 'value'),
    Output('symbol-dropdown', 'options'),
    Output('symbol-dropdown', 'value'),
    Input('sheet-dropdown', 'value'),
    State('stored-data', 'data')
)
def update_color_symbol(sheet_names, stored_data):
    if not stored_data or not sheet_names:
        return [], None, [], None
    df = combine_data(stored_data, sheet_names)
    if df is None or df.empty:
        return [], None, [], None

    cols = df.columns
    opts = [{'label': c, 'value': c} for c in cols]
    return opts, None, opts, None

# Обновление опций для кластеризации
@app.callback(
    Output('cluster-columns-dropdown', 'options'),
    Output('cluster-columns-dropdown', 'value'),
    Input('sheet-dropdown', 'value'),
    State('stored-data', 'data')
)
def update_cluster_columns(sheet_names, stored_data):
    if not stored_data or not sheet_names:
        return [], None
    df = combine_data(stored_data, sheet_names)
    if df is None or df.empty:
        return [], None

    numeric_cols = df.select_dtypes(include=['number']).columns
    cluster_opts = [{'label': c, 'value': c} for c in numeric_cols]
    default_val = numeric_cols[:2].tolist() if len(numeric_cols) >= 2 else None
    return cluster_opts, default_val

# Обновление опций для поиска и суммирования
@app.callback(
    Output('search-columns-dropdown', 'options'),
    Output('search-columns-dropdown', 'value'),
    Output('sum-columns-dropdown', 'options'),
    Output('sum-columns-dropdown', 'value'),
    Output('condition-column-dropdown', 'options'),
    Output('condition-column-dropdown', 'value'),
    Input('sheet-dropdown', 'value'),
    State('stored-data', 'data')
)
def update_search_sum_condition_columns(sheet_names, stored_data):
    if not stored_data or not sheet_names:
        return [], None, [], None, [], None
    df = combine_data(stored_data, sheet_names)
    if df is None or df.empty:
        return [], None, [], None, [], None

    cols = df.columns
    col_opts = [{'label': c, 'value': c} for c in cols]

    return (
        col_opts, None,  # Столбцы для поиска
        col_opts, None,  # Столбцы для суммирования
        col_opts, None   # Столбец для условий
    )

# Переключение дополнительного фильтра
@app.callback(
    Output("collapse-adv-filter", "is_open"),
    Input("toggle-adv-filter", "n_clicks"),
    State("collapse-adv-filter", "is_open")
)
def toggle_collapse(n_clicks, is_open):
    return not is_open if n_clicks else is_open

# Применение фильтров
@app.callback(
    Output('filters-store', 'data'),
    Input('apply-filters-btn', 'n_clicks'),
    State('x-axis-dropdown', 'value'),
    State('x-min', 'value'),
    State('x-max', 'value'),
    State('y-axis-dropdown', 'value'),
    State('y-min', 'value'),
    State('y-max', 'value'),
    State('adv-filter-column', 'value'),
    State('adv-filter-value', 'value'),
    prevent_initial_call=True
)
def apply_filters_callback(n_clicks, x_col, x_min, x_max, y_col, y_min, y_max, adv_col, adv_val):
    if not n_clicks:
        raise PreventUpdate
    new_filters = {
        'x_col': x_col,
        'x_min': x_min,
        'x_max': x_max,
        'y_col': y_col,
        'y_min': y_min,
        'y_max': y_max,
        'adv_col': adv_col,
        'adv_val': adv_val
    }
    logger.info(f"Применяем фильтры: {new_filters}")
    return new_filters

# Сброс фильтров
@app.callback(
    Output('filters-store', 'data', allow_duplicate=True),
    Input('reset-filters-btn', 'n_clicks'),
    prevent_initial_call=True
)
def reset_filters_callback(n_clicks):
    if n_clicks:
        cache.clear()
        logger.info("Сброс фильтров и кэша.")
        return {}
    raise PreventUpdate

# Обновление графика, таблицы, статистики и прочего
@app.callback(
    Output('data-graph', 'figure'),
    Output('data-table', 'columns'),
    Output('data-table', 'data'),
    Output('stats-output', 'children'),
    Output('correlation-heatmap', 'figure'),
    Output('regression-output', 'children'),
    Output('forecast-output', 'children'),
    Output('download-link', 'href'),
    Output('data-info', 'children'),
    Input('update-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('x-axis-dropdown', 'value'),
    State('y-axis-dropdown', 'value'),
    State('chart-type-dropdown', 'value'),
    State('forecast-period', 'value'),
    State('color-dropdown', 'value'),
    State('symbol-dropdown', 'value'),
    State('date-column-dropdown', 'value'),
    State('forecast-freq', 'value')
)
def update_graph(n_clicks, stored_data, sheet_names, filters, 
                 x_col, y_col, chart_type, forecast_period,
                 color_col, symbol_col, date_col, freq):
    if not stored_data or not sheet_names:
        raise PreventUpdate

    df = combine_data(stored_data, sheet_names)
    if df is None or df.empty:
        return (
            go.Figure().update_layout(title='Нет данных'),
            [], [],
            dbc.Alert('Нет данных.', color='danger'),
            go.Figure(),
            html.Div(),
            html.Div(),
            "",
            "Нет данных для отображения."
        )

    before_shape = df.shape
    df = apply_all_filters(df, filters or {})
    after_shape = df.shape
    data_info_text = f"До фильтров: {before_shape[0]} строк, {before_shape[1]} столбцов. После фильтров: {after_shape[0]} строк, {after_shape[1]} столбцов."

    fig = create_figure(df, x_col, y_col, chart_type, color_col, symbol_col)
    table_cols, table_data = create_data_table(df)
    stats_out = perform_statistical_analysis(df)

    # Если тип графика heatmap, corr_fig = fig
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
    forecast_out = perform_forecast(df, date_col, y_col, forecast_period, freq)

    # Скачивание CSV
    if df.empty:
        csv_str = ""
    else:
        df_download = df.copy()
        date_columns = df_download.select_dtypes(include=['datetime', 'datetimetz']).columns
        for c in date_columns:
            df_download[c] = df_download[c].dt.strftime('%d.%m.%Y')
        csv_data = df_download.to_csv(index=False, encoding='utf-8')
        csv_str = "data:text/csv;charset=utf-8," + base64.b64encode(csv_data.encode()).decode()

    return (
        fig,
        table_cols, table_data,
        stats_out,
        corr_fig,
        reg_out,
        forecast_out,
        csv_str,
        data_info_text
    )

# Машинное обучение: простая линейная регрессия
@app.callback(
    Output('ml-output', 'children'),
    Input('ml-button', 'n_clicks'),
    State('ml-test-size', 'value'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('x-axis-dropdown', 'value'),
    State('y-axis-dropdown', 'value')
)
def ml_callback(n_clicks, test_size, stored_data, sheet_names, filters, x_col, y_col):
    if not n_clicks:
        raise PreventUpdate
    if not stored_data or not sheet_names:
        return dbc.Alert("Загрузите файл и выберите листы.", color="warning")
    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    return perform_machine_learning(df, x_col, y_col, test_size)

# Машинное обучение: Random Forest
@app.callback(
    Output('rf-output', 'children'),
    Input('rf-button', 'n_clicks'),
    State('rf-test-size', 'value'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('x-axis-dropdown', 'value'),
    State('y-axis-dropdown', 'value')
)
def rf_callback(n_clicks, test_size, stored_data, sheet_names, filters, x_col, y_col):
    if not n_clicks:
        raise PreventUpdate
    if not stored_data or not sheet_names:
        return dbc.Alert("Сначала загрузите файл и выберите листы.", color="warning")
    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    return perform_random_forest_regression(df, x_col, y_col, test_size)

# Кластеризация
@app.callback(
    Output('cluster-output', 'children'),
    Input('cluster-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('cluster-columns-dropdown', 'value'),
    State('num-clusters', 'value')
)
def cluster_callback(n_clicks, stored_data, sheet_names, filters, selected_cols, n_clusters):
    if not n_clicks:
        raise PreventUpdate
    if not stored_data or not sheet_names:
        return dbc.Alert("Нет данных для кластеризации.", color="warning")
    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    return perform_clustering(df, selected_cols, n_clusters)

# PCA
@app.callback(
    Output('pca-output', 'children'),
    Input('pca-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('pca-components', 'value')
)
def pca_callback(n_clicks, stored_data, sheet_names, filters, n_components):
    if not n_clicks:
        raise PreventUpdate
    if not stored_data or not sheet_names:
        return dbc.Alert("Нет данных для PCA.", color="warning")
    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    return perform_pca(df, n_components)

# Расширенный поиск по слову
@app.callback(
    Output('search-output', 'children'),
    Input('search-button', 'n_clicks'),
    State('stored-data', 'data'),
    State('sheet-dropdown', 'value'),
    State('filters-store', 'data'),
    State('search-word', 'value'),
    State('search-columns-dropdown', 'value'),
    State('sum-columns-dropdown', 'value'),
    State('condition-column-dropdown', 'value'),
    State('condition-operator-dropdown', 'value'),
    State('condition-value-input', 'value')
)
def search_word_callback(n_clicks, stored_data, sheet_names, filters, search_word, search_cols, sum_cols, condition_col, condition_op, condition_val):
    if not n_clicks:
        raise PreventUpdate
    if not stored_data or not sheet_names:
        return dbc.Alert("Сначала загрузите Excel-файл и выберите листы.", color="warning")
    
    df = combine_data(stored_data, sheet_names)
    df = apply_all_filters(df, filters or {})
    if df is None or df.empty:
        return dbc.Alert("Нет данных после фильтрации — поиск невозможен.", color="danger")
    
    return perform_search_by_word(df, search_word, search_cols, sum_cols, condition_col, condition_op, condition_val)

# ------------------------------------------------------------------------------
# ЗАПУСК
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    app.run_server(debug=True)