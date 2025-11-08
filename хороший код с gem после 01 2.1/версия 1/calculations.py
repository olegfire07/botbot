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
    """
    try:
        irr = npf.irr(cash_flows)
        if irr is not None and not np.isnan(irr):
            return irr * 100
        else:
            return 0.0
    except Exception as e:
        logging.error(f"Ошибка при расчёте IRR: {e}")
        return 0.0


@st.cache_data
def calculate_areas(params: WarehouseParams):
    """
    Распределение площадей.
    Если сумма ручных площадей превышает usable_area, пропорционально уменьшаем.
    Если area=0 -> это значит не приносим дохода и не несём расходов в этом типе.
    """
    try:
        usable_area = params.total_area * params.useful_area_ratio
        
        if params.mode == "Ручной":
            total_manual = (
                params.storage_area_manual
                + params.loan_area_manual
                + params.vip_area_manual
                + params.short_term_area_manual
            )

            if total_manual > usable_area and usable_area > 0:
                factor = usable_area / total_manual
                storage_area = params.storage_area_manual * factor
                loan_area = params.loan_area_manual * factor
                vip_area = params.vip_area_manual * factor
                short_term_area = params.short_term_area_manual * factor
            else:
                storage_area = params.storage_area_manual
                loan_area = params.loan_area_manual
                vip_area = params.vip_area_manual
                short_term_area = params.short_term_area_manual
        else:  # automatic
            storage_area = usable_area * params.storage_share
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
    Считает количество вещей:
      area (м²) * shelves (полок/м²) * density (вещей/полку) * fill_rate
    Если area=0, результат будет 0.
    """
    try:
        return area * shelves * density * fill_rate
    except Exception as e:
        logging.error(f"Ошибка при расчёте количества вещей: {e}")
        return 0


@st.cache_data
def calculate_financials(params: WarehouseParams, disable_extended: bool):
    """
    Ежемесячный расчёт (доходы, расходы, прибыль):
      - Доход (хранение, займы, реализация)
      - Расходы (аренда, зарплата, упаковка, электричество и пр.)
      - Прибыль (за 1 месяц)
    """
    try:
        # Количество вещей
        storage_items = calculate_items(
            params.storage_area, params.shelves_per_m2,
            params.storage_items_density, params.storage_fill_rate
        )
        loan_items = calculate_items(
            params.loan_area, params.shelves_per_m2,
            params.loan_items_density, params.loan_fill_rate
        )
        vip_items = calculate_items(
            params.vip_area, params.shelves_per_m2,
            params.vip_items_density, params.vip_fill_rate
        )
        short_term_items = calculate_items(
            params.short_term_area, params.shelves_per_m2,
            params.short_term_items_density, params.short_term_fill_rate
        )

        # Доход от хранения
        storage_income = params.storage_area * params.storage_fee
        vip_income = params.vip_area * (params.storage_fee + params.vip_extra_fee)
        short_term_income = params.short_term_area * params.short_term_daily_rate * 30

        # Займы
        loan_items_interest = loan_items * (1 - params.realization_share_loan)
        loan_items_realized = loan_items * params.realization_share_loan

        loan_evaluated_interest = (
            params.average_item_value
            * params.item_evaluation
            * loan_items_interest
        )
        daily_loan_rate = max(params.loan_interest_rate / 100.0, 0)
        loan_interest_income = (
            loan_evaluated_interest
            * daily_loan_rate
            * params.loan_term_days
            * (1 - params.default_probability)
        )

        loan_evaluated_real = (
            params.average_item_value
            * params.item_evaluation
            * loan_items_realized
        )
        loan_realization = loan_evaluated_real * (params.item_realization_markup / 100.0)

        loan_income = loan_interest_income + loan_realization

        # Реализация storage/vip/short_term
        def calc_realization(items, markup):
            return (
                params.average_item_value
                * params.item_evaluation
                * items
                * (markup / 100.0)
            )

        storage_realization = calc_realization(
            storage_items * params.realization_share_storage,
            params.item_realization_markup
        )
        vip_realization = calc_realization(
            vip_items * params.realization_share_vip,
            params.item_realization_markup
        )
        short_term_realization = calc_realization(
            short_term_items * params.realization_share_short_term,
            params.item_realization_markup
        )
        realization_income = (
            storage_realization
            + vip_realization
            + short_term_realization
        )

        total_income = (
            storage_income
            + vip_income
            + short_term_income
            + loan_income
            + realization_income
        )

        # Расходы
        monthly_rent = params.total_area * params.rental_cost_per_m2
        electricity_cost = params.total_area * params.electricity_cost_per_m2
        packaging_cost = params.total_area * params.packaging_cost_per_m2

        total_monthly_expenses = (
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

        params.one_time_expenses = (
            params.one_time_setup_cost
            + params.one_time_equipment_cost
            + params.one_time_other_costs
            + params.one_time_legal_cost
            + params.one_time_logistics_cost
        )

        if params.time_horizon > 0:
            profit = (
                total_income
                - total_monthly_expenses
                - (params.one_time_expenses / params.time_horizon)
            )
        else:
            profit = total_income - total_monthly_expenses

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
    Общая точка безубыточности (BEP).
    Если total_income=0 => float('inf').
    """
    try:
        total_expenses = float(financials["total_expenses"])
        if params.time_horizon > 0:
            total_expenses += float(params.one_time_expenses) / float(params.time_horizon)
        if financials["total_income"] == 0:
            return float("inf")
        return total_expenses
    except Exception as e:
        logging.error(f"Ошибка при расчёте BEP: {e}")
        return float("inf")


@st.cache_data
def calculate_monthly_bep(financials: dict, params: WarehouseParams):
    """
    Помесячная точка безубыточности.
    Возвращает DataFrame: ["Месяц", "Необходимый доход для BEP"].
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

        df_bep = pd.DataFrame({
            "Месяц": months,
            "Необходимый доход для BEP": total_exp
        })
        return df_bep
    except Exception as e:
        logging.error(f"Ошибка при расчёте помесячного BEP: {e}")
        return pd.DataFrame()


def calculate_additional_metrics(total_income, total_expenses, profit):
    """
    Возвращает (profit_margin, profitability).
    profit_margin = (profit / total_income)*100
    profitability = (profit / total_expenses)*100
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
    ROI = ((total_income - total_expenses)/total_expenses)*100, если total_expenses>0, иначе None.
    """
    try:
        if total_expenses == 0:
            return None
        return (total_income - total_expenses) / total_expenses * 100
    except Exception as e:
        logging.error(f"Ошибка при расчёте ROI: {e}")
        return None


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
):
    """
    Простейшая симуляция Монте-Карло для доходов и расходов.
    Возвращает DataFrame с ['Месяц','Средний Доход','Средний Расход','Средняя Прибыль'].
    """
    try:
        np.random.seed(seed)
        months = np.arange(1, time_horizon + 1)

        inc_growth = (1 + monthly_income_growth) ** months
        exp_growth = (1 + monthly_expenses_growth) ** months

        inc_factors = np.random.uniform(1 - deviation, 1 + deviation, (simulations, time_horizon))
        exp_factors = np.random.uniform(1 - deviation, 1 + deviation, (simulations, time_horizon))

        incomes = base_income * inc_growth * inc_factors
        expenses = base_expenses * exp_growth * exp_factors
        profits = incomes - expenses

        df_mc = pd.DataFrame({
            "Месяц": months,
            "Средний Доход": incomes.mean(axis=0),
            "Средний Расход": expenses.mean(axis=0),
            "Средняя Прибыль": profits.mean(axis=0),
        })
        return df_mc
    except Exception as e:
        logging.error(f"Ошибка при симуляции Монте-Карло: {e}")
        return pd.DataFrame()


@st.cache_data
def min_loan_amount_for_bep(params: WarehouseParams, fin: dict):
    """
    Минимальная сумма займа для покрытия расходов (BEP).
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
def calculate_monthly_projection(params: WarehouseParams, base_financials: dict):
    """
    Пример помесячного прогноза доходов/расходов/прибыли.
    Возвращает DataFrame("Месяц","Доход","Расход","Прибыль").
    """
    try:
        months = np.arange(1, params.time_horizon + 1)
        start_income = base_financials["total_income"]

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

        marketing = np.full(params.time_horizon, params.marketing_expenses)
        insurance = np.full(params.time_horizon, params.insurance_expenses)
        taxes = np.full(params.time_horizon, params.taxes)
        utilities = np.full(params.time_horizon, params.utilities_expenses)
        maintenance = np.full(params.time_horizon, params.maintenance_expenses)
        depreciation = np.full(params.time_horizon, params.depreciation_expense)

        electricity = params.total_area * params.electricity_cost_per_m2
        packaging = params.total_area * params.packaging_cost_per_m2

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
        )

        if params.time_horizon > 0:
            monthly_expenses += params.one_time_expenses / params.time_horizon

        monthly_incomes = start_income * (1 + params.monthly_income_growth) ** (months - 1)
        monthly_profit = monthly_incomes - monthly_expenses

        df = pd.DataFrame({
            "Месяц": months,
            "Доход": monthly_incomes,
            "Расход": monthly_expenses,
            "Прибыль": monthly_profit,
        })
        return df
    except Exception as e:
        logging.error(f"Ошибка в calculate_monthly_projection: {e}")
        return pd.DataFrame()