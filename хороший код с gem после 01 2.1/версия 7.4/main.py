# main.py

import streamlit as st
import numpy as np
import pandas as pd
import os
import joblib
import yaml
import json

from data_model import WarehouseParams, validate_inputs
from calculations import (
    calculate_additional_metrics,
    calculate_roi,
    calculate_irr,
    calculate_total_bep,
    monte_carlo_simulation,
    calculate_financials,
    min_loan_amount_for_bep,
    calculate_monthly_bep,
    calculate_areas,
    calculate_npv
)
from utils import (
    normalize_shares,
    load_params_from_file,
    save_params_to_file,
    load_css,
)
from streamlit_ui import (
    MetricDisplay,
    ChartDisplay,
    TableDisplay,
    display_tab1_header,
    display_tab1_metrics,
    display_tab1_bep,
    display_tab1_chart,
    display_tab1_analysis,
    display_tab1,
    display_tab2_header,
    display_tab2_basic_forecast,
    display_tab2_ml_forecast,
    display_tab2_monte_carlo,
    display_tab3_header,
    display_tab3_bep_info,
    display_tab3_monthly_bep,
    display_tab3_sensitivity,
    display_tab4_header,
    display_tab4_area_metrics,
    display_tab4_storage_table,
    display_tab4_profit_table,
    display_tab4_results,
    compare_params,
)
from ml_models import prepare_ml_data, load_ml_model
from app_state import AppState


# Настраиваем страницу
st.set_page_config(page_title="Экономическая модель склада 📦", layout="wide")

# Загружаем CSS
load_css("style.css")

# Заголовок
st.markdown("# Экономическая модель склада (на русском языке)")
st.markdown(
    "Все расчёты выполняются автоматически при изменении параметров в боковой панели. "
    "Просто меняйте параметры — результаты обновятся."
)

# Инициализируем состояние
app_state = AppState()

# Загружаем default_params
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)
default_params = config["default_params"]

# Извлекаем forecast_method (если None, берём "Базовый")
selected_forecast_method = app_state.get("forecast_method") or "Базовый"
# poly_degree также, если None, то = 2
poly_degree = app_state.get("poly_degree") or 2
n_estimators = app_state.get("n_estimators") or 100

df_for_ml = app_state.get("df_for_ml")
ml_model = app_state.get("ml_model")
features = app_state.get("features") or ["Месяц", "Lag_1", "Lag_2", "Rolling_Mean_3", "Rolling_Mean_5"]
auto_feature_selection = app_state.get("auto_feature_selection") or False


def reset_params():
    """
    Сбрасывает параметры к значениям по умолчанию из config.yaml.
    """
    # Сбрасываем все ключи в app_state к дефолтным значениям
    app_state.load_default_state()
    st.session_state["uploaded_file"] = None
    st.session_state["df_for_ml"] = None
    st.session_state["ml_model"] = None
    st.session_state["forecast_method"] = "Базовый"

    # Сбросим активную «вкладку» (радио) при сбросе
    if "active_tab" in st.session_state:
        st.session_state.active_tab = "Вкладка 1"

    st.rerun()


# Считываем query_params, если есть
query_params = st.query_params
if query_params:
    if "params" in query_params:
        try:
            loaded_params = json.loads(query_params["params"])
            for key, value in loaded_params.items():
                if key in default_params:
                    app_state.set(key, value)
            if "shares" in loaded_params:
                app_state.shares.update(loaded_params["shares"])
            st.success("Параметры успешно загружены из URL.")
        except Exception as e:
            st.error(f"Ошибка загрузки параметров из URL: {e}")

# Боковая панель
with st.sidebar:
    st.markdown("## Ввод параметров")
    if st.button("🔄 Сбросить параметры"):
        reset_params()

    # Настройка темы
    with st.sidebar.expander("### Настройка темы", expanded=False):
        theme_options = ["Стандартная", "Темная"]
        current_theme = app_state.get("selected_theme") or "Стандартная"
        theme_index = theme_options.index(current_theme) if current_theme in theme_options else 0
        selected_theme = st.selectbox(
            "🎨 Выберите тему",
            theme_options,
            index=theme_index,
            help="Выберите тему для приложения."
        )
        app_state.set("selected_theme", selected_theme)

        # Задаём основной цвет
        main_color = st.color_picker('Выберите основной цвет', value=app_state.get("main_color") or "#007bff", help="Выберите цвет, который будет использоваться в качестве основного.")
        app_state.set("main_color", main_color)

        # Загружаем CSS
        if selected_theme == "Темная":
           load_css("dark_style.css")
        else:
           load_css("style.css")


    # -------------------------
    # ВСЕ ПАРАМЕТРЫ (НЕ УДАЛЯЕМ НИЧЕГО!), 
    # как в исходном коде: Основные, Распределение площади, и т.д.
    # -------------------------

    with st.sidebar.expander("### Основные параметры", expanded=False):
        total_area = st.number_input(
            "📏 Общая площадь (м²)",
            value=app_state.get("total_area"),
            step=10,
            min_value=1,
            format="%i",
            help="Общая арендуемая площадь склада в квадратных метрах.",
        )
        app_state.set("total_area", total_area)
        if total_area <= 0:
            st.error("Общая площадь должна быть больше нуля.")

        rental_cost_per_m2 = st.number_input(
            "💰 Стоимость аренды (руб./м²/мес.)",
            value=app_state.get("rental_cost_per_m2"),
            step=50,
            min_value=1,
            format="%i",
            help="Ежемесячная аренда за один квадратный метр.",
        )
        app_state.set("rental_cost_per_m2", rental_cost_per_m2)
        if rental_cost_per_m2 <= 0:
            st.error("Стоимость аренды должна быть больше нуля.")

        useful_area_ratio_slider = st.slider(
            "📐 Доля полезной площади (%)",
            40,
            80,
            int(app_state.get("useful_area_ratio") * 100),
            5,
            help="Процент полезной площади от общей площади склада.",
        )
        useful_area_ratio = useful_area_ratio_slider / 100.0
        app_state.set("useful_area_ratio", useful_area_ratio)
        if not 0 < useful_area_ratio <= 1:
            st.error("Доля полезной площади должна быть между 0 и 100%.")


    with st.sidebar.expander("### Распределение площади", expanded=False):
        mode = st.radio(
            "Режим распределения площади",
            ["Ручной", "Автоматический"],
            index=0,
            help="Выберите режим: ручной ввод или автоматическое распределение по долям.",
        )
        app_state.set("mode", mode)
        if mode == "Ручной":
            st.markdown("#### Ручной ввод площадей (м²)")
            temp_usable = total_area * useful_area_ratio

            col1, col2 = st.columns(2)
            storage_area_manual = col1.number_input(
                "Простое",
                value=app_state.get("storage_area_manual"),
                step=10.0,
                min_value=0.0,
                format="%.2f",
                help="Площадь под простое хранение.",
            )
            app_state.set("storage_area_manual", storage_area_manual)
            if storage_area_manual < 0:
                st.error("Площадь хранения должна быть ≥ 0.")

            loan_area_manual = col2.number_input(
                "Займы",
                value=app_state.get("loan_area_manual"),
                step=10.0,
                min_value=0.0,
                format="%.2f",
                help="Площадь под займы.",
            )
            app_state.set("loan_area_manual", loan_area_manual)
            if loan_area_manual < 0:
                st.error("Площадь под займы должна быть ≥ 0.")

            col3, col4 = st.columns(2)
            vip_area_manual = col3.number_input(
                "VIP",
                value=app_state.get("vip_area_manual"),
                step=10.0,
                min_value=0.0,
                format="%.2f",
                help="Площадь под VIP-хранение.",
            )
            app_state.set("vip_area_manual", vip_area_manual)
            if vip_area_manual < 0:
                st.error("Площадь VIP должна быть ≥ 0.")

            short_term_area_manual = col4.number_input(
                "Краткосрочное",
                value=app_state.get("short_term_area_manual"),
                step=10.0,
                min_value=0.0,
                format="%.2f",
                help="Площадь под краткосрочное хранение.",
            )
            app_state.set("short_term_area_manual", short_term_area_manual)
            if short_term_area_manual < 0:
                st.error("Площадь краткосрочного должна быть ≥ 0.")

            total_manual_set = (
                storage_area_manual
                + loan_area_manual
                + vip_area_manual
                + short_term_area_manual
            )
            leftover = temp_usable - total_manual_set
            st.write(
                f"Не распределено: {leftover:.2f} м² из {temp_usable:.2f} м² полезной площади."
            )
        else:
            st.markdown("#### Автоматическое распределение площадей")
            st.write("Площади распределяются автоматически в соответствии с заданными долями.")

    with st.sidebar.expander("### Тарифы и плотности", expanded=False):
        storage_fee = st.number_input(
            "💳 Тариф простого (руб./м²/мес.)",
            value=app_state.get("storage_fee"),
            step=100,
            min_value=0,
            format="%i",
            help="Ежемесячный тариф за простой склад (руб./м²).",
        )
        app_state.set("storage_fee", storage_fee)
        if storage_fee < 0:
            st.error("Тариф простого должен быть ≥ 0.")

        col1, col2 = st.columns(2)
        shelves_per_m2 = col1.number_input(
            "📚 Полок на 1 м²",
            value=app_state.get("shelves_per_m2"),
            step=1,
            min_value=1,
            max_value=100,
            format="%i",
            help="Количество полок на 1 м².",
        )
        app_state.set("shelves_per_m2", shelves_per_m2)
        if shelves_per_m2 < 1:
            st.error("Количество полок должно быть ≥ 1")

        short_term_daily_rate = col2.number_input(
            "🕒 Тариф краткосрочного (руб./день/м²)",
            value=app_state.get("short_term_daily_rate"),
            step=10.0,
            min_value=0.0,
            format="%.2f",
            help="Тариф за 1 м² краткосрочного хранения в день.",
        )
        app_state.set("short_term_daily_rate", short_term_daily_rate)
        if short_term_daily_rate < 0:
            st.error("Тариф краткосрочного должен быть ≥ 0.")

        vip_extra_fee = st.number_input(
            "👑 Наценка VIP (руб./м²/мес.)",
            value=app_state.get("vip_extra_fee"),
            step=50.0,
            min_value=0.0,
            format="%.2f",
            help="Наценка для VIP (руб./м²).",
        )
        app_state.set("vip_extra_fee", vip_extra_fee)
        if vip_extra_fee < 0:
            st.error("Наценка VIP должна быть ≥ 0.")

    with st.sidebar.expander("### Оценка и займы", expanded=False):
        item_evaluation_slider = st.slider(
            "🔍 Оценка вещи (%)",
            0,
            100,
            int(app_state.get("item_evaluation") * 100),
            5,
            help="Процент оценки стоимости вещи (под залог).",
        )
        item_evaluation = item_evaluation_slider / 100.0
        app_state.set("item_evaluation", item_evaluation)

        item_realization_markup = st.number_input(
            "📈 Наценка реализации (%)",
            value=app_state.get("item_realization_markup"),
            step=5.0,
            min_value=0.0,
            max_value=100.0,
            format="%.1f",
            help="Наценка при реализации вещей.",
        )
        app_state.set("item_realization_markup", item_realization_markup)

        average_item_value = st.number_input(
            "💲 Средняя оценка вещи (руб.)",
            value=app_state.get("average_item_value"),
            step=500,
            min_value=0,
            format="%i",
            help="Средняя стоимость одной вещи (руб.).",
        )
        app_state.set("average_item_value", average_item_value)

        loan_interest_rate = st.number_input(
            "💳 Ставка займов (%/день)",
            value=app_state.get("loan_interest_rate"),
            step=0.01,
            min_value=0.0,
            format="%.3f",
            help="Дневная ставка (%) для займов.",
        )
        app_state.set("loan_interest_rate", loan_interest_rate)

        loan_term_days = st.number_input(
            "📅 Средний срок займа (дней)",
            value=app_state.get("loan_term_days"),
            step=1,
            min_value=1,
            format="%i",
            help="Средний срок займа в днях.",
        )
        app_state.set("loan_term_days", loan_term_days)

    with st.sidebar.expander("### Реализация (%)", expanded=False):
        realization_share_storage_slider = st.slider(
            "Простое",
            0,
            100,
            int(app_state.get("realization_share_storage") * 100),
            5,
            help="Процент вещей из простого хранения, идущих на реализацию.",
        )
        realization_share_storage = realization_share_storage_slider / 100.0
        app_state.set("realization_share_storage", realization_share_storage)

        realization_share_loan_slider = st.slider(
            "Займы",
            0,
            100,
            int(app_state.get("realization_share_loan") * 100),
            5,
            help="Процент вещей из займов, идущих на реализацию.",
        )
        realization_share_loan = realization_share_loan_slider / 100.0
        app_state.set("realization_share_loan", realization_share_loan)

        realization_share_vip_slider = st.slider(
            "VIP",
            0,
            100,
            int(app_state.get("realization_share_vip") * 100),
            5,
            help="Процент вещей из VIP, которые будут реализованы.",
        )
        realization_share_vip = realization_share_vip_slider / 100.0
        app_state.set("realization_share_vip", realization_share_vip)

        realization_share_short_term_slider = st.slider(
            "Краткосрочное",
            0,
            100,
            int(app_state.get("realization_share_short_term") * 100),
            5,
            help="Процент вещей из краткосрочного хранения на реализацию.",
        )
        realization_share_short_term = realization_share_short_term_slider / 100.0
        app_state.set("realization_share_short_term", realization_share_short_term)

    with st.sidebar.expander("### Процент заполняемости", expanded=False):
        storage_fill_rate_slider = st.slider(
            "Простое",
            0,
            100,
            int(app_state.get("storage_fill_rate") * 100),
            5,
            help="Процент заполнения площади простого хранения.",
        )
        storage_fill_rate = storage_fill_rate_slider / 100.0
        app_state.set("storage_fill_rate", storage_fill_rate)

        loan_fill_rate_slider = st.slider(
            "Займы",
            0,
            100,
            int(app_state.get("loan_fill_rate") * 100),
            5,
            help="Процент заполнения площади займов.",
        )
        loan_fill_rate = loan_fill_rate_slider / 100.0
        app_state.set("loan_fill_rate", loan_fill_rate)

        vip_fill_rate_slider = st.slider(
            "VIP",
            0,
            100,
            int(app_state.get("vip_fill_rate") * 100),
            5,
            help="Процент заполнения VIP-секции.",
        )
        vip_fill_rate = vip_fill_rate_slider / 100.0
        app_state.set("vip_fill_rate", vip_fill_rate)

        short_term_fill_rate_slider = st.slider(
            "Краткосрочное",
            0,
            100,
            int(app_state.get("short_term_fill_rate") * 100),
            5,
            help="Процент заполнения краткосрочного хранения.",
        )
        short_term_fill_rate = short_term_fill_rate_slider / 100.0
        app_state.set("short_term_fill_rate", short_term_fill_rate)

    with st.sidebar.expander("### Плотность (вещей/м²)", expanded=False):
        storage_items_density = st.number_input(
            "Простое",
            value=app_state.get("storage_items_density"),
            step=1,
            min_value=1,
            format="%i",
            help="Плотность хранения (вещей на м²) для простого.",
        )
        app_state.set("storage_items_density", storage_items_density)

        loan_items_density = st.number_input(
            "Займы",
            value=app_state.get("loan_items_density"),
            step=1,
            min_value=1,
            format="%i",
            help="Плотность хранения для займов (вещи/м²).",
        )
        app_state.set("loan_items_density", loan_items_density)

        vip_items_density = st.number_input(
            "VIP",
            value=app_state.get("vip_items_density"),
            step=1,
            min_value=1,
            format="%i",
            help="Плотность хранения для VIP (вещи/м²).",
        )
        app_state.set("vip_items_density", vip_items_density)

        short_term_items_density = st.number_input(
            "Краткосрочное",
            value=app_state.get("short_term_items_density"),
            step=1,
            min_value=1,
            format="%i",
            help="Плотность хранения для краткосрочного (вещи/м²).",
        )
        app_state.set("short_term_items_density", short_term_items_density)

    with st.sidebar.expander("### Отток клиентов/вещей (%)", expanded=False):
        storage_monthly_churn_num = st.number_input(
            "Простое (%)",
            value=app_state.get("storage_monthly_churn") * 100,
            step=0.1,
            min_value=0.0,
            max_value=100.0,
            format="%.1f",
            help="Ежемесячный отток простого хранения.",
        )
        storage_monthly_churn = storage_monthly_churn_num / 100.0
        app_state.set("storage_monthly_churn", storage_monthly_churn)

        loan_monthly_churn_num = st.number_input(
            "Займы (%)",
            value=app_state.get("loan_monthly_churn") * 100,
            step=0.1,
            min_value=0.0,
            max_value=100.0,
            format="%.1f",
            help="Отток по займам.",
        )
        loan_monthly_churn = loan_monthly_churn_num / 100.0
        app_state.set("loan_monthly_churn", loan_monthly_churn)

        vip_monthly_churn_num = st.number_input(
            "VIP (%)",
            value=app_state.get("vip_monthly_churn") * 100,
            step=0.1,
            min_value=0.0,
            max_value=100.0,
            format="%.1f",
            help="Отток VIP.",
        )
        vip_monthly_churn = vip_monthly_churn_num / 100.0
        app_state.set("vip_monthly_churn", vip_monthly_churn)

        short_term_monthly_churn_num = st.number_input(
            "Краткосрочное (%)",
            value=app_state.get("short_term_monthly_churn") * 100,
            step=0.1,
            min_value=0.0,
            max_value=100.0,
            format="%.1f",
            help="Отток по краткосрочному.",
        )
        short_term_monthly_churn = short_term_monthly_churn_num / 100.0
        app_state.set("short_term_monthly_churn", short_term_monthly_churn)

    with st.sidebar.expander("### Финансы (ежемесячные)", expanded=False):
        salary_expense = st.number_input(
            "Зарплата (руб./мес.)",
            value=app_state.get("salary_expense"),
            step=10000,
            min_value=0,
            format="%i",
            help="Общие затраты на зарплату (руб./мес.).",
        )
        app_state.set("salary_expense", salary_expense)

        miscellaneous_expenses = st.number_input(
            "Прочие (руб./мес.)",
            value=app_state.get("miscellaneous_expenses"),
            step=5000,
            min_value=0,
            format="%i",
            help="Прочие ежемесячные расходы.",
        )
        app_state.set("miscellaneous_expenses", miscellaneous_expenses)

        depreciation_expense = st.number_input(
            "Амортизация (руб./мес.)",
            value=app_state.get("depreciation_expense"),
            step=5000,
            min_value=0,
            format="%i",
            help="Ежемесячная амортизация.",
        )
        app_state.set("depreciation_expense", depreciation_expense)

        marketing_expenses = st.number_input(
            "Маркетинг (руб./мес.)",
            value=app_state.get("marketing_expenses"),
            step=5000,
            min_value=0,
            format="%i",
            help="Затраты на маркетинг.",
        )
        app_state.set("marketing_expenses", marketing_expenses)

        insurance_expenses = st.number_input(
            "Страхование (руб./мес.)",
            value=app_state.get("insurance_expenses"),
            step=1000,
            min_value=0,
            format="%i",
            help="Ежемесячная страховка.",
        )
        app_state.set("insurance_expenses", insurance_expenses)

        taxes = st.number_input(
            "Налоги (руб./мес.)",
            value=app_state.get("taxes"),
            step=5000,
            min_value=0,
            format="%i",
            help="Налоговые отчисления (руб./мес).",
        )
        app_state.set("taxes", taxes)

        utilities_expenses = st.number_input(
            "Коммуналка (руб./мес.)",
            value=app_state.get("utilities_expenses"),
            step=5000,
            min_value=0,
            format="%i",
            help="Коммунальные услуги (руб./мес.).",
        )
        app_state.set("utilities_expenses", utilities_expenses)

        maintenance_expenses = st.number_input(
            "Обслуживание (руб./мес.)",
            value=app_state.get("maintenance_expenses"),
            step=5000,
            min_value=0,
            format="%i",
            help="Обслуживание склада (руб./мес).",
        )
        app_state.set("maintenance_expenses", maintenance_expenses)

    with st.sidebar.expander("### Финансы (единовременные)", expanded=False):
        one_time_setup_cost = st.number_input(
            "Настройка (руб.)",
            value=app_state.get("one_time_setup_cost"),
            step=5000,
            min_value=0,
            format="%i",
            help="Единовременные затраты на настройку склада.",
        )
        app_state.set("one_time_setup_cost", one_time_setup_cost)

        one_time_equipment_cost = st.number_input(
            "Оборудование (руб.)",
            value=app_state.get("one_time_equipment_cost"),
            step=5000,
            min_value=0,
            format="%i",
            help="Единовременные затраты на оборудование.",
        )
        app_state.set("one_time_equipment_cost", one_time_equipment_cost)

        one_time_other_costs = st.number_input(
            "Другие (руб.)",
            value=app_state.get("one_time_other_costs"),
            step=5000,
            min_value=0,
            format="%i",
            help="Прочие единовременные расходы.",
        )
        app_state.set("one_time_other_costs", one_time_other_costs)

        one_time_legal_cost = st.number_input(
            "Юридические (руб.)",
            value=app_state.get("one_time_legal_cost"),
            step=5000,
            min_value=0,
            format="%i",
            help="Единовременные юридические расходы.",
        )
        app_state.set("one_time_legal_cost", one_time_legal_cost)

        one_time_logistics_cost = st.number_input(
            "Логистика (руб.)",
            value=app_state.get("one_time_logistics_cost"),
            step=5000,
            min_value=0,
            format="%i",
            help="Единовременные логистические расходы.",
        )
        app_state.set("one_time_logistics_cost", one_time_logistics_cost)

    with st.sidebar.expander("### Переменные расходы", expanded=False):
        packaging_cost_per_m2 = st.number_input(
            "Упаковка (руб./м²)",
            value=app_state.get("packaging_cost_per_m2"),
            step=5.0,
            min_value=0.0,
            format="%.2f",
            help="Стоимость упаковки на 1 м² площади.",
        )
        app_state.set("packaging_cost_per_m2", packaging_cost_per_m2)
        if packaging_cost_per_m2 < 0:
            st.error("Стоимость упаковки должна быть ≥ 0.")

        electricity_cost_per_m2 = st.number_input(
            "Электричество (руб./м²)",
            value=app_state.get("electricity_cost_per_m2"),
            step=10.0,
            min_value=0.0,
            format="%.1f",
            help="Стоимость электроэнергии на 1 м².",
        )
        app_state.set("electricity_cost_per_m2", electricity_cost_per_m2)
        if electricity_cost_per_m2 < 0:
            st.error("Стоимость электричества должна быть ≥ 0.")

    with st.sidebar.expander("### Инфляция и рост", expanded=False):
        monthly_inflation_rate_val = st.number_input(
            "Инфляция (%/мес.)",
            value=app_state.get("monthly_inflation_rate") * 100,
            step=0.1,
            min_value=0.0,
            format="%.1f",
            help="Ежемесячная инфляция (%).",
        )
        monthly_inflation_rate = monthly_inflation_rate_val / 100.0
        app_state.set("monthly_inflation_rate", monthly_inflation_rate)

        monthly_rent_growth_val = st.number_input(
            "📈 Рост аренды (%/мес.)",
            value=app_state.get("monthly_rent_growth") * 100,
            step=0.5,
            min_value=0.0,
            format="%.1f",
            help="Рост аренды в месяц (%).",
        )
        monthly_rent_growth = monthly_rent_growth_val / 100.0
        app_state.set("monthly_rent_growth", monthly_rent_growth)

        monthly_salary_growth_val = st.number_input(
            "📈 Рост зарплаты (%/мес.)",
            value=app_state.get("monthly_salary_growth") * 100,
            step=0.1,
            min_value=0.0,
            format="%.1f",
            help="Ежемесячный рост зарплаты (%).",
        )
        monthly_salary_growth = monthly_salary_growth_val / 100.0
        app_state.set("monthly_salary_growth", monthly_salary_growth)

        monthly_other_expenses_growth_val = st.number_input(
            "📈 Рост прочих расходов (%/мес.)",
            value=app_state.get("monthly_other_expenses_growth") * 100,
            step=0.1,
            min_value=0.0,
            format="%.1f",
            help="Ежемесячный рост прочих расходов (%).",
        )
        monthly_other_expenses_growth = monthly_other_expenses_growth_val / 100.0
        app_state.set("monthly_other_expenses_growth", monthly_other_expenses_growth)

    with st.sidebar.expander("### Расширенные параметры и прогнозирование", expanded=False):
        disable_extended = st.checkbox(
            "🚫 Отключить расширенные параметры",
            value=app_state.get("disable_extended"),
            help="Если включено, расширенные параметры игнорируются.",
        )
        app_state.set("disable_extended", disable_extended)

        if not disable_extended:
            time_horizon_val = st.slider(
                "🕒 Горизонт прогноза (мес.)",
                1, 24,
                value=app_state.get("time_horizon"),
                help="Сколько месяцев прогнозируем.",
            )
            app_state.set("time_horizon", time_horizon_val)

            default_probability_val = st.number_input(
                "⚠️ Вероятность невозврата (%)",
                value=app_state.get("default_probability") * 100,
                step=1.0,
                min_value=0.0,
                max_value=100.0,
                format="%.1f",
                help="Вероятность невозврата (для займов).",
            )
            default_probability = default_probability_val / 100.0
            app_state.set("default_probability", default_probability)

            liquidity_factor_val = st.number_input(
                "💧 Коэффициент ликвидности",
                value=app_state.get("liquidity_factor"),
                step=0.1,
                min_value=0.1,
                format="%.1f",
                help="Коэффициент ликвидности.",
            )
            app_state.set("liquidity_factor", liquidity_factor_val)

            safety_factor_val = st.number_input(
                "🛡 Коэффициент запаса",
                value=app_state.get("safety_factor"),
                step=0.1,
                min_value=0.1,
                format="%.1f",
                help="Коэффициент запаса для устойчивости.",
            )
            app_state.set("safety_factor", safety_factor_val)

            loan_grace_period_val = st.number_input(
                "⏳ Льготный период (мес.)",
                value=app_state.get("loan_grace_period"),
                step=1,
                min_value=0,
                format="%i",
                help="Льготный период по займам (мес).",
            )
            app_state.set("loan_grace_period", loan_grace_period_val)

            monthly_income_growth_val = st.number_input(
                "📈 Рост доходов (%/мес.)",
                value=app_state.get("monthly_income_growth") * 100,
                step=0.5,
                format="%.1f",
                help="Предполагаемый рост доходов в месяц.",
            )
            monthly_income_growth = monthly_income_growth_val / 100.0
            app_state.set("monthly_income_growth", monthly_income_growth)

            monthly_expenses_growth_val = st.number_input(
                "📉 Рост расходов (%/мес.)",
                value=app_state.get("monthly_expenses_growth") * 100,
                step=0.5,
                format="%.1f",
                help="Предполагаемый рост расходов в месяц.",
            )
            monthly_expenses_growth = monthly_expenses_growth_val / 100.0
            app_state.set("monthly_expenses_growth", monthly_expenses_growth)
        else:
            app_state.set("time_horizon", 1)
            app_state.set("default_probability", 0.0)
            app_state.set("liquidity_factor", 1.0)
            app_state.set("safety_factor", 1.2)
            app_state.set("loan_grace_period", 0)
            app_state.set("monthly_income_growth", 0.0)
            app_state.set("monthly_expenses_growth", 0.0)

        fm_options = [
            "Базовый",
            "ML (линейная регрессия)",
            "ML (полиномиальная регрессия)",
            "Симуляция Монте-Карло",
            "ML (случайный лес)",
            "ML (SVR)",
            "ML (XGBoost)",
        ]
        current_fm = app_state.get("forecast_method") or "Базовый"
        fm_index = fm_options.index(current_fm) if current_fm in fm_options else 0
        forecast_method_sel = st.selectbox(
            "📊 Метод прогнозирования",
            fm_options,
            index=fm_index,
            help="Выберите метод прогноза.",
        )
        app_state.set("forecast_method", forecast_method_sel)

        if forecast_method_sel == "Симуляция Монте-Карло":
            monte_carlo_simulations_val = st.number_input(
                "🎲 Симуляций Монте-Карло",
                value=app_state.get("monte_carlo_simulations"),
                step=10,
                min_value=10,
                format="%i",
                help="Число симуляций в Монте-Карло.",
            )
            app_state.set("monte_carlo_simulations", monte_carlo_simulations_val)

            monte_carlo_deviation_val = st.number_input(
                "🔀 Отклонения (0.1 = ±10%)",
                value=app_state.get("monte_carlo_deviation"),
                step=0.01,
                min_value=0.01,
                format="%.2f",
                help="Отклонение для Монте-Карло (доля).",
            )
            app_state.set("monte_carlo_deviation", monte_carlo_deviation_val)

            monte_carlo_seed_val = st.number_input(
                "🔑 Seed",
                value=app_state.get("monte_carlo_seed"),
                step=1,
                format="%i",
                help="Зерно случайности (Монте-Карло).",
            )
            app_state.set("monte_carlo_seed", monte_carlo_seed_val)

            mc_dist_options = ["Равномерное", "Нормальное", "Треугольное"]
            current_dist = app_state.get("monte_carlo_distribution") or "Равномерное"
            mc_dist_index = mc_dist_options.index(current_dist) if current_dist in mc_dist_options else 0
            monte_carlo_distribution_sel = st.selectbox(
                "Распределение",
                mc_dist_options,
                index=mc_dist_index,
                help="Тип распределения для симуляции Монте-Карло.",
            )
            app_state.set("monte_carlo_distribution", monte_carlo_distribution_sel)

            if monte_carlo_distribution_sel == "Нормальное":
                mc_normal_mean_val = st.number_input(
                    "Среднее",
                    value=app_state.get("monte_carlo_normal_mean") or 0.0,
                    step=0.1,
                    format="%.1f",
                    help="Среднее для нормального распределения.",
                )
                app_state.set("monte_carlo_normal_mean", mc_normal_mean_val)

                mc_normal_std_val = st.number_input(
                    "Ст. откл.",
                    value=app_state.get("monte_carlo_normal_std") or 0.1,
                    step=0.01,
                    min_value=0.01,
                    format="%.2f",
                    help="Ст. отклонение для нормального распределения.",
                )
                app_state.set("monte_carlo_normal_std", mc_normal_std_val)

            if monte_carlo_distribution_sel == "Треугольное":
                mc_triang_left_val = st.number_input(
                   "Мин. значение",
                   value=app_state.get("monte_carlo_triang_left") or 0.0,
                   step=0.1,
                   format="%.1f",
                   help="Мин. значение для треугольного распределения.",
                )
                app_state.set("monte_carlo_triang_left", mc_triang_left_val)

                mc_triang_mode_val = st.number_input(
                    "Мода",
                    value=app_state.get("monte_carlo_triang_mode") or 1.0,
                    step=0.1,
                    format="%.1f",
                    help="Мода для треугольного распределения.",
                )
                app_state.set("monte_carlo_triang_mode", mc_triang_mode_val)

                mc_triang_right_val = st.number_input(
                    "Макс. значение",
                    value=app_state.get("monte_carlo_triang_right") or 2.0,
                    step=0.1,
                    format="%.1f",
                    help="Макс. значение для треугольного распределения.",
                )
                app_state.set("monte_carlo_triang_right", mc_triang_right_val)

        enable_ml_settings_val = st.checkbox(
            "🤖 Включить расширенный ML-прогноз",
            value=app_state.get("enable_ml_settings"),
            help="Доп. настройки для ML-прогноза.",
        )
        app_state.set("enable_ml_settings", enable_ml_settings_val)

        if forecast_method_sel == "ML (полиномиальная регрессия)" and enable_ml_settings_val:
            poly_degree_val = st.number_input(
                "Степень полинома",
                min_value=1,
                max_value=5,
                value=app_state.get("poly_degree") or 2,
                step=1,
                format="%i",
                help="Степень полинома для полиномиальной регрессии.",
            )
            app_state.set("poly_degree", poly_degree_val)
        else:
            app_state.set("poly_degree", 2)

        if forecast_method_sel == "ML (случайный лес)" and enable_ml_settings_val:
            n_estimators_val = st.number_input(
                "Количество деревьев",
                min_value=10,
                max_value=500,
                value=app_state.get("n_estimators") or 100,
                step=10,
                format="%i",
                help="Количество деревьев для случайного леса.",
            )
            app_state.set("n_estimators", n_estimators_val)
            features_options = ["Месяц", "Lag_1", "Lag_2", "Rolling_Mean_3", "Rolling_Mean_5"]
            selected_features = st.multiselect("Выберите признаки",
                                               options=features_options,
                                               default=features_options,
                                               help="Выберите признаки для обучения ML модели.")
            app_state.set("features", selected_features)
        elif forecast_method_sel in ["ML (SVR)", "ML (XGBoost)"]  and enable_ml_settings_val:
            features_options = ["Месяц", "Lag_1", "Lag_2", "Rolling_Mean_3", "Rolling_Mean_5"]
            selected_features = st.multiselect("Выберите признаки",
                                               options=features_options,
                                               default=features_options,
                                               help="Выберите признаки для обучения ML модели.")
            app_state.set("features", selected_features)
        else:
            app_state.set("n_estimators", 100)
            app_state.set("features", ["Месяц", "Lag_1", "Lag_2", "Rolling_Mean_3", "Rolling_Mean_5"])

        if forecast_method_sel in ["ML (случайный лес)", "ML (SVR)", "ML (XGBoost)"] and enable_ml_settings_val:
            param_search_options = ["Нет", "GridSearchCV", "RandomizedSearchCV"]
            param_search_method = st.selectbox("Поиск параметров",
                                               param_search_options,
                                               index=0,
                                               help="Выберите метод поиска параметров",
                                               )
            app_state.set("param_search_method",param_search_method)

            auto_feature_selection_val = st.checkbox(
                "🤖 Автоматический выбор признаков",
                value=app_state.get("auto_feature_selection"),
                help="Включить автоматический выбор признаков",
            )
            app_state.set("auto_feature_selection", auto_feature_selection_val)
        else:
            app_state.set("param_search_method","Нет")
            app_state.set("auto_feature_selection", False)

    # Загрузка данных для ML, если нужно
    forecast_method = app_state.get("forecast_method") or "Базовый"
    enable_ml_settings_val = app_state.get("enable_ml_settings")
    if enable_ml_settings_val and forecast_method.startswith("ML"):
        uploaded_file = st.file_uploader(
            "Загрузить данные для ML-модели (CSV/Excel)",
            type=["csv", "xlsx"],
            help="Загрузите файл с историческими данными для ML.",
        )
        if uploaded_file is not None:
            file_extension = os.path.splitext(uploaded_file.name)[1]
            try:
                if file_extension == ".csv":
                    df_for_ml = pd.read_csv(uploaded_file)
                elif file_extension == ".xlsx":
                    df_for_ml = pd.read_excel(uploaded_file)
                else:
                    raise ValueError("Формат не поддерживается (только CSV или Excel).")
                st.success("Файл успешно загружен для ML.")
                app_state.set("df_for_ml", df_for_ml)
            except Exception as e:
                st.error(f"Ошибка загрузки файла: {e}")
                app_state.set("df_for_ml", None)
        else:
            app_state.set("df_for_ml", None)

        uploaded_model = st.file_uploader(
            "Загрузить ML-модель",
            type=["pkl"],
            help="Загрузите ранее обученную ML-модель (формат .pkl)",
        )
        app_state.set("uploaded_model", uploaded_model)
    else:
        app_state.set("df_for_ml", None)
        app_state.set("uploaded_model", None)

    st.sidebar.markdown("---")
    if st.sidebar.button("Сохранить параметры"):
        if "saved_params" not in st.session_state:
            st.session_state.saved_params = {}
        param_name = f"Сохраненные параметры {len(st.session_state.saved_params) + 1}"

        params_to_save = {}
        for k in default_params.keys():
            params_to_save[k] = app_state.get(k)
        params_to_save["shares"] = dict(app_state.shares)

        st.session_state.saved_params[param_name] = params_to_save
        st.success(f"Параметры сохранены: {param_name}")

    uploaded_file_sess = st.sidebar.file_uploader(
        "Загрузить параметры (JSON или YAML)",
        type=["json", "yaml", "yml"],
        help="Загрузите ранее сохранённый файл с параметрами.",
    )
    if uploaded_file_sess:
        try:
            if uploaded_file_sess.name.endswith(".json"):
                loaded_params = json.load(uploaded_file_sess)
            elif uploaded_file_sess.name.endswith((".yaml", ".yml")):
                loaded_params = yaml.safe_load(uploaded_file_sess)
            else:
                raise ValueError("Неподдерживаемый формат (должен быть JSON или YAML).")

            for key, value in loaded_params.items():
                if key in default_params:
                    app_state.set(key, value)
            if "shares" in loaded_params:
                app_state.shares.update(loaded_params["shares"])
            st.success("Параметры успешно загружены из файла.")
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка при загрузке файла: {e}")

    if "saved_params" in st.session_state and st.session_state.saved_params:
        selected_param = st.selectbox("Сравнить с:",
                                       options=list(st.session_state.saved_params.keys()),
                                       index=0,
                                       help="Выберите параметры для сравнения.",
                                       )
    else:
       selected_param = None

    if st.sidebar.button("Сохранить в файл"):
        try:
            filename = st.text_input("Имя файла для сохранения", "warehouse_params")
            file_format = st.selectbox("Формат файла", ["json", "yaml"])
            if filename:
                params_to_save = {}
                for k in default_params.keys():
                    params_to_save[k] = app_state.get(k)
                params_to_save["shares"] = dict(app_state.shares)

                file_data = save_params_to_file(params_to_save, filename, file_format)
                st.download_button(
                    label="Скачать параметры",
                    data=file_data,
                    file_name=f"{filename}.{file_format}",
                    mime=f"application/{file_format}",
                )
        except Exception as e:
            st.error(f"Ошибка при сохранении в файл: {e}")

# Теперь формируем WarehouseParams
forecast_method = app_state.get("forecast_method") or "Базовый"
params = WarehouseParams(
    total_area=app_state.get("total_area"),
    rental_cost_per_m2=app_state.get("rental_cost_per_m2"),
    useful_area_ratio=app_state.get("useful_area_ratio"),
    mode=app_state.get("mode") or "Ручной",
    storage_share=app_state.shares["storage_share"],
    loan_share=app_state.shares["loan_share"],
    vip_share=app_state.shares["vip_share"],
    short_term_share=app_state.shares["short_term_share"],
    storage_area_manual=app_state.get("storage_area_manual"),
    loan_area_manual=app_state.get("loan_area_manual"),
    vip_area_manual=app_state.get("vip_area_manual"),
    short_term_area_manual=app_state.get("short_term_area_manual"),
    storage_fee=app_state.get("storage_fee"),
    shelves_per_m2=app_state.get("shelves_per_m2"),
    short_term_daily_rate=app_state.get("short_term_daily_rate"),
    vip_extra_fee=app_state.get("vip_extra_fee"),
    item_evaluation=app_state.get("item_evaluation"),
    item_realization_markup=app_state.get("item_realization_markup"),
    average_item_value=app_state.get("average_item_value"),
    loan_interest_rate=app_state.get("loan_interest_rate"),
    loan_term_days=app_state.get("loan_term_days"),
    realization_share_storage=app_state.get("realization_share_storage"),
    realization_share_loan=app_state.get("realization_share_loan"),
    realization_share_vip=app_state.get("realization_share_vip"),
    realization_share_short_term=app_state.get("realization_share_short_term"),
    storage_items_density=app_state.get("storage_items_density"),
    loan_items_density=app_state.get("loan_items_density"),
    vip_items_density=app_state.get("vip_items_density"),
    short_term_items_density=app_state.get("short_term_items_density"),
    storage_fill_rate=app_state.get("storage_fill_rate"),
    loan_fill_rate=app_state.get("loan_fill_rate"),
    vip_fill_rate=app_state.get("vip_fill_rate"),
    short_term_fill_rate=app_state.get("short_term_fill_rate"),
    storage_monthly_churn=app_state.get("storage_monthly_churn"),
    loan_monthly_churn=app_state.get("loan_monthly_churn"),
    vip_monthly_churn=app_state.get("vip_monthly_churn"),
    short_term_monthly_churn=app_state.get("short_term_monthly_churn"),
    salary_expense=app_state.get("salary_expense"),
    miscellaneous_expenses=app_state.get("miscellaneous_expenses"),
    depreciation_expense=app_state.get("depreciation_expense"),
    marketing_expenses=app_state.get("marketing_expenses"),
    insurance_expenses=app_state.get("insurance_expenses"),
    taxes=app_state.get("taxes"),
    utilities_expenses=app_state.get("utilities_expenses"),
    maintenance_expenses=app_state.get("maintenance_expenses"),
    one_time_setup_cost=app_state.get("one_time_setup_cost"),
    one_time_equipment_cost=app_state.get("one_time_equipment_cost"),
    one_time_other_costs=app_state.get("one_time_other_costs"),
    one_time_legal_cost=app_state.get("one_time_legal_cost"),
    one_time_logistics_cost=app_state.get("one_time_logistics_cost"),
    time_horizon=app_state.get("time_horizon"),
    monthly_rent_growth=app_state.get("monthly_rent_growth"),
    default_probability=app_state.get("default_probability"),
    liquidity_factor=app_state.get("liquidity_factor"),
    safety_factor=app_state.get("safety_factor"),
    loan_grace_period=app_state.get("loan_grace_period"),
    monthly_income_growth=app_state.get("monthly_income_growth"),
    monthly_expenses_growth=app_state.get("monthly_expenses_growth"),
    forecast_method=forecast_method,
    monte_carlo_simulations=app_state.get("monte_carlo_simulations"),
    monte_carlo_deviation=app_state.get("monte_carlo_deviation"),
    monte_carlo_seed=app_state.get("monte_carlo_seed"),
    enable_ml_settings=app_state.get("enable_ml_settings"),
    electricity_cost_per_m2=app_state.get("electricity_cost_per_m2"),
    monthly_inflation_rate=app_state.get("monthly_inflation_rate"),
    monthly_salary_growth=app_state.get("monthly_salary_growth"),
    monthly_other_expenses_growth=app_state.get("monthly_other_expenses_growth"),
    packaging_cost_per_m2=app_state.get("packaging_cost_per_m2"),
    poly_degree=poly_degree,
    n_estimators=n_estimators,
    features=features,
    monte_carlo_distribution = app_state.get("monte_carlo_distribution"),
    monte_carlo_normal_mean = app_state.get("monte_carlo_normal_mean"),
    monte_carlo_normal_std = app_state.get("monte_carlo_normal_std"),
    monte_carlo_triang_left = app_state.get("monte_carlo_triang_left"),
    monte_carlo_triang_mode = app_state.get("monte_carlo_triang_mode"),
    monte_carlo_triang_right = app_state.get("monte_carlo_triang_right"),
    auto_feature_selection=auto_feature_selection,
    param_search_method=app_state.get("param_search_method")
)

# Валидируем
is_valid, error_message = validate_inputs(params)
if not is_valid:
    st.error(f"Ошибка ввода данных: {error_message}")
else:
    # Считаем распределение площадей
    areas = calculate_areas(params)
    for k, v in areas.items():
        setattr(params, k, v)

    # --- СТАРЫЙ способ (st.tabs): не удаляем, а просто комментируем ---
    #
    # tab1, tab2_, tab3_, tab4_ = st.tabs([
    #     "📊 Общие результаты",
    #     "📈 Прогнозирование",
    #     "🔍 Точка безубыточности",
    #     "📋 Детализация",
    # ])
    # # Здесь был вызов display_tab1(tab1, ...) и т.д.
    #
    # -----------------------------------------------------------------

    # --- Новый способ: radio + st.session_state["active_tab"] ---
    st.markdown("---")
    st.markdown("### Выберите вкладку:")
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Вкладка 1"

    tabs_list = ["Вкладка 1", "Вкладка 2", "Вкладка 3", "Вкладка 4"]
    chosen = st.radio(
        "Вкладки:",
        tabs_list,
        index=tabs_list.index(st.session_state.active_tab),
        key="active_tab",
        horizontal=True
    )

    if chosen == "Вкладка 1":
        # Раньше вызывали: display_tab1(st, base_financials, pm, pr, roi_val, irr_val, ...)
        # НЕЛЬЗЯ передавать st, тк тогда внутри display_tab1_header(tab, ...) будет with st:
        # => TypeError('module' object does not support the context manager protocol)
        
        # Исправляем:
        tab_container = st.container()  # создаём контейнер
        base_financials = calculate_financials(params, disable_extended=False)
        irr_val = calculate_irr(
            [-params.one_time_setup_cost - params.one_time_equipment_cost - params.one_time_other_costs - params.one_time_legal_cost - params.one_time_logistics_cost]
            + [base_financials["profit"]]*params.time_horizon
        )
        pm, pr = calculate_additional_metrics(
            base_financials["total_income"],
            base_financials["total_expenses"],
            base_financials["profit"]
        )
        roi_val = calculate_roi(base_financials["total_income"], base_financials["total_expenses"])
        npv_val = calculate_npv(
            [-params.one_time_setup_cost - params.one_time_equipment_cost - params.one_time_other_costs - params.one_time_legal_cost - params.one_time_logistics_cost]
            + [base_financials["profit"]]*params.time_horizon,
            0.05
        )
        # Вызов display_tab1 и передаём именно tab_container:
        display_tab1(
            tab_container,
            base_financials,
            pm,
            pr,
            roi_val,
            irr_val,
            params,
            selected_param=app_state.get("selected_param"),
            main_color=app_state.get("main_color") or "#007bff",
            npv=npv_val
        )

    elif chosen == "Вкладка 2":
        tab_container = st.container()
        base_financials = calculate_financials(params, disable_extended=False)
        display_tab2_header(tab_container)
        if params.forecast_method == "Базовый":
            display_tab2_basic_forecast(tab_container, base_financials, params)
        elif params.forecast_method.startswith("ML"):
            display_tab2_ml_forecast(
                tab_container,
                params.enable_ml_settings,
                selected_forecast_method,
                ml_model,
                df_for_ml,
                params,
                base_financials
            )
        elif params.forecast_method == "Симуляция Монте-Карло":
            display_tab2_monte_carlo(tab_container, base_financials, params)

    elif chosen == "Вкладка 3":
        tab_container = st.container()
        base_financials = calculate_financials(params, disable_extended=False)
        display_tab3_header(tab_container)
        display_tab3_bep_info(tab_container, base_financials, params)
        display_tab3_monthly_bep(tab_container, base_financials, params)
        display_tab3_sensitivity(tab_container, params, disable_extended=False)

    else:  # "Вкладка 4"
        tab_container = st.container()
        base_financials = calculate_financials(params, disable_extended=False)
        irr_val = calculate_irr(
            [-params.one_time_setup_cost - params.one_time_equipment_cost - params.one_time_other_costs - params.one_time_legal_cost - params.one_time_logistics_cost]
            + [base_financials["profit"]]*params.time_horizon
        )
        display_tab4_header(tab_container)
        display_tab4_area_metrics(tab_container, params)
        display_tab4_storage_table(tab_container, params, base_financials)
        display_tab4_profit_table(tab_container, params, base_financials)
        display_tab4_results(tab_container, base_financials, params, irr_val)
