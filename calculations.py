# calculations.py

import numpy as np
import pandas as pd
import logging
import numpy_financial as npf
import streamlit as st
from data_model import WarehouseParams

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@st.cache_data
def calculate_irr(cash_flows):
    """
    Рассчитывает IRR (внутренняя норма доходности) в процентах.

    Args:
        cash_flows (list): Список денежных потоков, где отрицательные значения - это инвестиции, а положительные - доходы.

    Returns:
        float: Внутренняя норма доходности в процентах. Возвращает 0.0 в случае ошибки или если IRR не может быть рассчитан.
    """
    try:
        irr = npf.irr(cash_flows)
        return irr * 100 if irr is not None and not np.isnan(irr) else 0.0
    except Exception as e:
        logging.error(f"Ошибка при расчёте IRR: {e}")
        return 0.0


@st.cache_data
def calculate_areas(params: WarehouseParams):
    """
    Распределяет общую площадь склада на различные типы хранения (простое, займы, VIP, краткосрочное).

    Args:
        params (WarehouseParams): Объект с параметрами склада, включая общую площадь, доли и режим распределения.

    Returns:
        dict: Словарь с распределенными площадями (usable_area, storage_area, loan_area, vip_area, short_term_area).
    """
    try:
        usable_area = params.total_area * params.useful_area_ratio # Расчет полезной площади

        if params.mode == "Ручной":
            total_manual = (
                params.storage_area_manual
                + params.loan_area_manual
                + params.vip_area_manual
                + params.short_term_area_manual
            )
            if total_manual > usable_area > 0:
                factor = usable_area / total_manual  # Коэффициент масштабирования для ручного режима
                storage_area = params.storage_area_manual * factor
                loan_area = params.loan_area_manual * factor
                vip_area = params.vip_area_manual * factor
                short_term_area = params.short_term_area_manual * factor
            else:
                storage_area = params.storage_area_manual
                loan_area = params.loan_area_manual
                vip_area = params.vip_area_manual
                short_term_area = params.short_term_area_manual
        else:
            storage_area = usable_area * params.storage_share # Автоматическое распределение площадей по долям
            loan_area = usable_area * params.loan_share
            vip_area = usable_area * params.vip_share
            short_term_area = usable_area * params.short_term_share

        return {
            "usable_area": usable_area,
            "storage_area": storage_area,
            "loan_area": loan_area,
            "vip_area": vip_area,
            "short_term_area": short_term_area,
        }
    except Exception as e:
        logging.error(f"Ошибка при расчёте площадей: {e}")
        return {
            "usable_area": 0,
            "storage_area": 0,
            "loan_area": 0,
            "vip_area": 0,
            "short_term_area": 0,
        }


def calculate_items(area, shelves, density, fill_rate):
    """
    Считает количество вещей в определенной области хранения.

     Args:
        area (float): Площадь области хранения.
        shelves (int): Количество полок на 1 м².
        density (int): Плотность хранения (вещей на м²).
        fill_rate (float): Процент заполненности области (от 0 до 1).

    Returns:
        float: Общее количество вещей в области.
    """
    try:
        return area * shelves * density * fill_rate # Расчет количества вещей
    except Exception as e:
        logging.error(f"Ошибка при расчёте количества вещей: {e}")
        return 0


@st.cache_data
def calculate_financials(params: WarehouseParams, disable_extended: bool, amortize_one_time_expenses=False):
    """
    Рассчитывает ежемесячные финансовые показатели склада (доходы, расходы, прибыль).

    Args:
        params (WarehouseParams): Объект с параметрами склада.
        disable_extended (bool): Если True, то не используются расширенные параметры (например, амортизация единовременных расходов).
        amortize_one_time_expenses (bool): Если True, то единовременные расходы амортизируются на весь горизонт планирования.

    Returns:
        dict: Словарь с финансовыми показателями (total_income, total_expenses, profit и др.)
    """
    try:
        storage_items = calculate_items( # Расчет количества вещей
            params.storage_area, params.shelves_per_m2,
            params.storage_items_density, params.storage_fill_rate
        )
        loan_items = calculate_items( # Расчет количества вещей
            params.loan_area, params.shelves_per_m2,
            params.loan_items_density, params.loan_fill_rate
        )
        vip_items = calculate_items( # Расчет количества вещей
            params.vip_area, params.shelves_per_m2,
            params.vip_items_density, params.vip_fill_rate
        )
        short_term_items = calculate_items( # Расчет количества вещей
            params.short_term_area, params.shelves_per_m2,
            params.short_term_items_density, params.short_term_fill_rate
        )

        # Доход
        storage_income = params.storage_area * params.storage_fee  # Доход от простого хранения
        vip_income = params.vip_area * (params.storage_fee + params.vip_extra_fee) # Доход от VIP-хранения
        short_term_income = params.short_term_area * params.short_term_daily_rate * 30 # Доход от краткосрочного хранения

        loan_items_interest = loan_items * (1 - params.realization_share_loan) # Количество вещей под процент
        loan_items_realized = loan_items * params.realization_share_loan # Количество вещей под реализацию

        loan_evaluated_interest = (
            params.average_item_value
            * params.item_evaluation
            * loan_items_interest
        ) # Оценочная стоимость вещей под процент
        daily_loan_rate = max(params.loan_interest_rate / 100.0, 0)
        loan_interest_income = (
            loan_evaluated_interest
            * daily_loan_rate
            * params.loan_term_days
            * (1 - params.default_probability)
        )  # Доход от процентов по займам

        loan_evaluated_real = (
            params.average_item_value
            * params.item_evaluation
            * loan_items_realized
        )  # Оценочная стоимость вещей под реализацию
        loan_realization = loan_evaluated_real * (params.item_realization_markup / 100.0) # Доход от реализации займов

        loan_income = loan_interest_income + loan_realization # Общий доход от займов

        # Реализация
        def calc_realization(items, markup):
            return (
                params.average_item_value
                * params.item_evaluation
                * items
                * (markup / 100.0)
            ) # Расчет дохода от реализации

        storage_realization = calc_realization( # Доход от реализации простого хранения
            storage_items * params.realization_share_storage,
            params.item_realization_markup
        )
        vip_realization = calc_realization( # Доход от реализации VIP-хранения
            vip_items * params.realization_share_vip,
            params.item_realization_markup
        )
        short_term_realization = calc_realization(  # Доход от реализации краткосрочного хранения
            short_term_items * params.realization_share_short_term,
            params.item_realization_markup
        )
        realization_income = ( # Общий доход от реализации
            storage_realization
            + vip_realization
            + short_term_realization
        )

        total_income = (  # Общий доход
            storage_income
            + vip_income
            + short_term_income
            + loan_income
            + realization_income
        )

        # Расходы
        monthly_rent = params.total_area * params.rental_cost_per_m2  # Расходы на аренду
        electricity_cost = params.total_area * params.electricity_cost_per_m2  # Расходы на электричество
        packaging_cost = params.total_area * params.packaging_cost_per_m2 # Расходы на упаковку

        total_monthly_expenses = (   # Общие ежемесячные расходы
            monthly_rent
            + params.salary_expense
            + params.miscellaneous_expenses
            + params.depreciation_expense
            + params.marketing_expenses
            + params.insurance_expenses
            + params.taxes
            + params.utilities_expenses
            + params.maintenance_expenses
            + electricity_cost
            + packaging_cost
        )

        params.one_time_expenses = ( # Общие единовременные расходы
            params.one_time_setup_cost
            + params.one_time_equipment_cost
            + params.one_time_other_costs
            + params.one_time_legal_cost
            + params.one_time_logistics_cost
        )

        if amortize_one_time_expenses and params.time_horizon > 0:
            profit = (  # Прибыль с амортизацией единовременных расходов
                total_income
                - total_monthly_expenses
                - (params.one_time_expenses / params.time_horizon)
            )
        elif params.time_horizon > 0:
            profit = (  # Прибыль без амортизации единовременных расходов
                total_income
                - total_monthly_expenses
            )
            if params.time_horizon > 0:
              profit -= params.one_time_expenses
        else:
            profit = total_income - total_monthly_expenses # Прибыль без амортизации и time_horizon

        return {
            "total_income": total_income,
            "total_expenses": total_monthly_expenses,
            "profit": profit,
            "storage_income": storage_income,
            "vip_income": vip_income,
            "short_term_income": short_term_income,
            "loan_income_after_realization": loan_income,
            "loan_income": loan_income,
            "realization_income": realization_income,
            "storage_realization": storage_realization,
            "vip_realization": vip_realization,
            "short_term_realization": short_term_realization,
            "loan_realization": loan_realization,
            "storage_items": storage_items,
            "loan_items": loan_items,
            "vip_items": vip_items,
            "short_term_items": short_term_items,
            "loan_interest_income": loan_interest_income,
        }
    except Exception as e:
        logging.error(f"Ошибка в calculate_financials: {e}")
        return {
            "total_income": 0,
            "total_expenses": 0,
            "profit": 0,
            "storage_income": 0,
            "vip_income": 0,
            "short_term_income": 0,
            "loan_income_after_realization": 0,
            "loan_income": 0,
            "realization_income": 0,
            "storage_realization": 0,
            "vip_realization": 0,
            "short_term_realization": 0,
            "loan_realization": 0,
            "storage_items": 0,
            "loan_items": 0,
            "vip_items": 0,
            "short_term_items": 0,
            "loan_interest_income": 0,
        }


@st.cache_data
def calculate_total_bep(financials: dict, params: WarehouseParams):
    """
    Рассчитывает общую точку безубыточности (BEP) в денежном выражении (рублях)

    Args:
        financials (dict): Словарь с финансовыми показателями, как результат работы функции calculate_financials
        params (WarehouseParams): Объект с параметрами склада

    Returns:
        float: Точка безубыточности (общие расходы). Возвращает float("inf"), если доход равен нулю.
    """
    try:
        total_expenses = float(financials["total_expenses"])
        if params.time_horizon > 0:
            total_expenses += float(params.one_time_expenses) / float(params.time_horizon)
        return float("inf") if financials["total_income"] == 0 else total_expenses  # Возвращает бесконечность если нет дохода
    except Exception as e:
        logging.error(f"Ошибка при расчёте BEP: {e}")
        return float("inf")


@st.cache_data
def calculate_monthly_bep(financials: dict, params: WarehouseParams):
    """
    Рассчитывает помесячную точку безубыточности.

     Args:
        financials (dict): Словарь с финансовыми показателями, как результат работы функции calculate_financials.
        params (WarehouseParams): Объект с параметрами склада.

    Returns:
        pd.DataFrame: DataFrame с помесячным BEP, где 'Месяц' - месяц, а 'Необходимый доход для BEP' -  доход для достижения безубыточности
    """
    try:
        months = np.arange(1, params.time_horizon + 1, dtype=float)

        rent = (
            float(params.total_area)
            * float(params.rental_cost_per_m2)
            * (1 + float(params.monthly_rent_growth)) ** months
        ).astype(float)
        salary = (
            float(params.salary_expense)
            * (1 + float(params.monthly_salary_growth)) ** months
        ).astype(float)
        other_exp = (
            float(params.miscellaneous_expenses)
            * (1 + float(params.monthly_other_expenses_growth)) ** months
        ).astype(float)

        total_exp = (
            rent
            + salary
            + other_exp
            + float(params.depreciation_expense)
            + float(params.marketing_expenses)
            + float(params.insurance_expenses)
            + float(params.taxes)
            + float(params.utilities_expenses)
            + float(params.maintenance_expenses)
        ).astype(float)

        if params.time_horizon > 0:
            addition = float(params.one_time_expenses) / float(params.time_horizon)
            total_exp = total_exp + addition

        return pd.DataFrame(
            {
                "Месяц": months,
                "Необходимый доход для BEP": total_exp
            }
        )
    except Exception as e:
        logging.error(f"Ошибка при расчёте помесячного BEP: {e}")
        return pd.DataFrame()


def calculate_additional_metrics(total_income, total_expenses, profit):
    """
    Вычисляет и возвращает маржу прибыли и рентабельность.

    Args:
        total_income (float): Общий доход.
        total_expenses (float): Общие расходы.
        profit (float): Общая прибыль.

    Returns:
         tuple: Кортеж (profit_margin, profitability), где profit_margin - это маржа прибыли в процентах, profitability - рентабельность в процентах.
    """
    try:
        profit_margin = (profit / total_income * 100) if total_income else 0
        profitability = (profit / total_expenses * 100) if total_expenses else 0
        return profit_margin, profitability
    except Exception as e:
        logging.error(f"Ошибка при расчёте дополнительных метрик: {e}")
        return 0, 0


def calculate_roi(total_income, total_expenses):
    """
    Вычисляет ROI (Return on Investment).

    Args:
       total_income (float): Общий доход.
       total_expenses (float): Общие расходы.

    Returns:
        float: ROI в процентах. Возвращает None если total_expenses равен нулю.
    """
    try:
        if total_expenses == 0:
            return None
        return (total_income - total_expenses) / total_expenses * 100
    except Exception as e:
        logging.error(f"Ошибка при расчёте ROI: {e}")
        return None


@st.cache_data
def calculate_npv(cash_flows, rate):
    """
    Рассчитывает NPV (чистая приведенная стоимость).

    Args:
        cash_flows (list): Список денежных потоков.
        rate (float): Ставка дисконтирования.

    Returns:
        float: NPV. Возвращает 0.0 в случае ошибки.
    """
    try:
        return npf.npv(rate, cash_flows)
    except Exception as e:
        logging.error(f"Ошибка при расчёте NPV: {e}")
        return 0.0


@st.cache_data
def monte_carlo_simulation(
    base_income,
    base_expenses,
    time_horizon,
    simulations,
    deviation,
    seed,
    monthly_income_growth,
    monthly_expenses_growth,
    distribution_type="Равномерное",
    normal_mean=0.0,
    normal_std=0.1,
    triang_left=0.0,
    triang_mode=1.0,
    triang_right=2.0
):
    """
    Проводит симуляцию Монте-Карло для доходов и расходов.

    Args:
        base_income (float): Базовый ежемесячный доход.
        base_expenses (float): Базовые ежемесячные расходы.
        time_horizon (int): Горизонт прогноза в месяцах.
        simulations (int): Количество симуляций.
        deviation (float): Максимальное отклонение (для равномерного распределения, как доля от 1).
        seed (int): Зерно для генератора случайных чисел.
        monthly_income_growth (float): Ежемесячный рост доходов.
        monthly_expenses_growth (float): Ежемесячный рост расходов.
        distribution_type (str): Тип распределения для симуляции ("Равномерное", "Нормальное", "Треугольное").
        normal_mean (float): Среднее для нормального распределения.
        normal_std (float): Стандартное отклонение для нормального распределения.
        triang_left (float): Левая граница для треугольного распределения.
        triang_mode (float): Мода для треугольного распределения.
        triang_right (float): Правая граница для треугольного распределения.

    Returns:
        pd.DataFrame: DataFrame со средними значениями дохода, расходов и прибыли по месяцам.
    """
    try:
        np.random.seed(seed)
        months = np.arange(1, time_horizon + 1) # Месяцы

        inc_growth = (1 + monthly_income_growth) ** months  # Рост доходов по месяцам
        exp_growth = (1 + monthly_expenses_growth) ** months # Рост расходов по месяцам

        if distribution_type == "Нормальное":
            inc_factors = np.random.normal(normal_mean, normal_std, (simulations, time_horizon)) # Нормальное распределение для доходов
            exp_factors = np.random.normal(normal_mean, normal_std, (simulations, time_horizon)) # Нормальное распределение для расходов
        elif distribution_type == "Треугольное":
            inc_factors = np.random.triangular(triang_left, triang_mode, triang_right, (simulations, time_horizon))  # Треугольное распределение для доходов
            exp_factors = np.random.triangular(triang_left, triang_mode, triang_right, (simulations, time_horizon)) # Треугольное распределение для расходов
        else:
            inc_factors = np.random.uniform(1 - deviation, 1 + deviation, (simulations, time_horizon)) # Равномерное распределение для доходов
            exp_factors = np.random.uniform(1 - deviation, 1 + deviation, (simulations, time_horizon)) # Равномерное распределение для расходов

        incomes = base_income * inc_growth * inc_factors # Симуляция доходов
        expenses = base_expenses * exp_growth * exp_factors # Симуляция расходов
        profits = incomes - expenses # Расчет прибыли

        return pd.DataFrame(
            {
                "Месяц": months,  # Месяц
                "Средний Доход": incomes.mean(axis=0), # Средний доход
                "Средний Расход": expenses.mean(axis=0),  # Средний расход
                "Средняя Прибыль": profits.mean(axis=0),  # Средняя прибыль
            }
        )
    except Exception as e:
        logging.error(f"Ошибка при симуляции Монте-Карло: {e}")
        return pd.DataFrame()


@st.cache_data
def min_loan_amount_for_bep(params: WarehouseParams, fin: dict):
    """
    Рассчитывает минимальную сумму займа на одну вещь для покрытия расходов (BEP).

    Args:
        params (WarehouseParams): Объект с параметрами склада.
        fin (dict): Словарь с финансовыми показателями, как результат работы функции calculate_financials.

    Returns:
        float: Минимальная сумма займа на одну вещь. Возвращает 0.0, если `loan_items` <= 0
    """
    try:
        total_exp = float(fin["total_expenses"])
        if params.time_horizon > 0:
            total_exp += float(params.one_time_expenses) / float(params.time_horizon)

        if fin["loan_items"] <= 0:
            return 0.0

        daily_rate = max(params.loan_interest_rate / 100.0, 0.0001)
        value = (total_exp / fin["loan_items"]) / (daily_rate * params.loan_term_days)
        return max(value, 0.0)
    except Exception as e:
        logging.error(f"Ошибка при расчёте min_loan_amount_for_bep: {e}")
        return 0.0


@st.cache_data
def calculate_multidimensional_sensitivity(params: WarehouseParams, param_keys: list, param_ranges: dict, disable_extended: bool):
    """
    Проводит многомерный анализ чувствительности.

    Args:
        params (WarehouseParams): Объект с параметрами склада.
        param_keys (list): Список параметров для анализа чувствительности.
        param_ranges (dict): Словарь с диапазонами значений для параметров.
        disable_extended (bool): Если True, то не используются расширенные параметры.

    Returns:
        pd.DataFrame: DataFrame с результатами анализа чувствительности, где "Параметры" - значения параметров, а "Прибыль (руб.)" - прибыль для этих параметров.
    """
    try:
        results = []
        original_values = {key: getattr(params, key) for key in param_keys}
    
        def recursive_sensitivity(current_params, index, current_combination):
            if index == len(param_keys):
                fin = calculate_financials(current_params, disable_extended)
                results.append({"Параметры": current_combination.copy(), "Прибыль (руб.)": fin["profit"]})
                return

            param_key = param_keys[index]
            for value in param_ranges[param_key]:
                setattr(current_params, param_key, value)
                current_combination[param_key] = value
                recursive_sensitivity(current_params, index + 1, current_combination)

        recursive_sensitivity(params, 0, {})

        for key, value in original_values.items():
            setattr(params, key, value)
        
        df = pd.DataFrame(results)
        df["Параметры"] = df["Параметры"].apply(lambda x: ", ".join([f"{k}={v:.2f}" for k, v in x.items()]))
        for param_key in param_keys:
            df[param_key] = df["Параметры"].apply(
                lambda x: float(x.split(f"{param_key}=")[1].split(",")[0]) if f"{param_key}=" in x else np.nan
            )
        return df
    except Exception as e:
        logging.error(f"Ошибка при расчёте многомерного анализа чувствительности: {e}")
        return pd.DataFrame()


@st.cache_data
def calculate_monthly_projection(params: WarehouseParams, base_financials: dict):
    """
    Создает помесячный прогноз доходов, расходов и прибыли на заданный горизонт.

    Args:
        params (WarehouseParams): Объект с параметрами склада.
        base_financials (dict): Словарь с базовыми финансовыми показателями.

    Returns:
        pd.DataFrame: DataFrame с помесячными доходами, расходами и прибылью.
    """
    try:
        months = np.arange(1, params.time_horizon + 1)
        start_income = base_financials["total_income"] # Базовый доход

        rent = (
            params.total_area
            * params.rental_cost_per_m2
            * (1 + params.monthly_rent_growth) ** (months - 1)
        )
        salary = (
            params.salary_expense
            * (1 + params.monthly_salary_growth) ** (months - 1)
        )
        other_exp = (
            params.miscellaneous_expenses
            * (1 + params.monthly_other_expenses_growth) ** (months - 1)
        )

        marketing = np.full(params.time_horizon, params.marketing_expenses) # Постоянные расходы
        insurance = np.full(params.time_horizon, params.insurance_expenses) # Постоянные расходы
        taxes = np.full(params.time_horizon, params.taxes) # Постоянные расходы
        utilities = np.full(params.time_horizon, params.utilities_expenses)  # Постоянные расходы
        maintenance = np.full(params.time_horizon, params.maintenance_expenses) # Постоянные расходы
        depreciation = np.full(params.time_horizon, params.depreciation_expense) # Постоянные расходы

        electricity = params.total_area * params.electricity_cost_per_m2 # Переменные расходы
        packaging = params.total_area * params.packaging_cost_per_m2 # Переменные расходы

        monthly_expenses = (
            rent
            + salary
            + other_exp
            + marketing
            + insurance
            + taxes
            + utilities
            + maintenance
            + depreciation
            + electricity
            + packaging
        ) # Общие расходы

        if params.time_horizon > 0:
            monthly_expenses += params.one_time_expenses / params.time_horizon # Добавление единовременных расходов (если есть горизонт)

        monthly_incomes = start_income * (1 + params.monthly_income_growth) ** (months - 1) # Прогнозируемые доходы
        monthly_profit = monthly_incomes - monthly_expenses # Прогнозируемая прибыль

        return pd.DataFrame(
            {
                "Месяц": months, # Месяц
                "Доход": monthly_incomes, # Доход
                "Расход": monthly_expenses, # Расход
                "Прибыль": monthly_profit, # Прибыль
            }
        )
    except Exception as e:
        logging.error(f"Ошибка в calculate_monthly_projection: {e}")
        return pd.DataFrame()