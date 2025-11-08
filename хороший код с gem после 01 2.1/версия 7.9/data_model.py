# data_model.py
from dataclasses import dataclass, field
from typing import Optional, Tuple
import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@dataclass
class WarehouseParams:
    """
    Класс для хранения параметров склада.
    """

    total_area: float
    rental_cost_per_m2: float
    useful_area_ratio: float
    mode: str
    storage_share: float
    loan_share: float
    vip_share: float
    short_term_share: float
    storage_area_manual: float
    loan_area_manual: float
    vip_area_manual: float
    short_term_area_manual: float
    storage_fee: float
    shelves_per_m2: float
    short_term_daily_rate: float
    vip_extra_fee: float
    item_evaluation: float
    item_realization_markup: float
    average_item_value: float
    loan_interest_rate: float
    loan_term_days: int
    realization_share_storage: float
    realization_share_loan: float
    realization_share_vip: float
    realization_share_short_term: float
    storage_items_density: float
    loan_items_density: float
    vip_items_density: float
    short_term_items_density: float
    storage_fill_rate: float
    loan_fill_rate: float
    vip_fill_rate: float
    short_term_fill_rate: float
    storage_monthly_churn: float
    loan_monthly_churn: float
    vip_monthly_churn: float
    short_term_monthly_churn: float
    salary_expense: float
    miscellaneous_expenses: float
    depreciation_expense: float
    marketing_expenses: float
    insurance_expenses: float
    taxes: float
    utilities_expenses: float
    maintenance_expenses: float
    one_time_setup_cost: float
    one_time_equipment_cost: float
    one_time_other_costs: float
    one_time_legal_cost: float
    one_time_logistics_cost: float
    time_horizon: int
    monthly_rent_growth: float
    default_probability: float
    liquidity_factor: float
    safety_factor: float
    loan_grace_period: int
    monthly_income_growth: float
    monthly_expenses_growth: float
    forecast_method: str
    monte_carlo_simulations: int
    monte_carlo_deviation: float
    monte_carlo_seed: int
    enable_ml_settings: bool
    electricity_cost_per_m2: float
    monthly_inflation_rate: float
    monthly_salary_growth: float
    monthly_other_expenses_growth: float
    packaging_cost_per_m2: float = 10.0

    one_time_expenses: float = 0.0
    usable_area: float = 0.0
    storage_area: float = 0.0
    loan_area: float = 0.0
    vip_area: float = 0.0
    short_term_area: float = 0.0
    payback_period: float = 0.0
    poly_degree: int = 2
    n_estimators: int = 100
    features: list = field(default_factory=lambda: ["Месяц", "Lag_1", "Lag_2", "Rolling_Mean_3", "Rolling_Mean_5"])
    monte_carlo_distribution: str = "Равномерное"
    monte_carlo_normal_mean: float = 0.0
    monte_carlo_normal_std: float = 0.1
    monte_carlo_triang_left: float = 0.0
    monte_carlo_triang_mode: float = 1.0
    monte_carlo_triang_right: float = 2.0
    auto_feature_selection: bool = False
    param_search_method: str = "Нет"


def validate_inputs(params: WarehouseParams) -> Tuple[bool, str]:
    """
    Проверяет корректность введённых данных.
    """
    if not isinstance(params.total_area, (int, float)) or params.total_area <= 0:
        return False, "Общая площадь должна быть числом больше нуля."
    if not (0 < params.useful_area_ratio <= 1):
        return False, "Доля полезной площади должна быть между 0 и 1."

    total_manual_area = (
        params.storage_area_manual
        + params.loan_area_manual
        + params.vip_area_manual
        + params.short_term_area_manual
    )
    usable_area = params.total_area * params.useful_area_ratio
    if total_manual_area <= 0 and params.mode == "Ручной":
        return False, "Сумма вручную введённых площадей должна быть > 0."
    if total_manual_area > usable_area and params.mode == "Ручной":
        return (
            False,
            f"Сумма вручную введённых площадей ({total_manual_area:.2f} м²) "
            f"превышает полезную площадь ({usable_area:.2f} м²).",
        )

    if not isinstance(params.loan_term_days, int) or params.loan_term_days <= 0:
        return False, "Срок займа должен быть целым числом больше 0."

    fill_rates = [
        params.storage_fill_rate,
        params.loan_fill_rate,
        params.vip_fill_rate,
        params.short_term_fill_rate,
    ]
    if any(r < 0 or r > 1 for r in fill_rates):
        return False, "Процент заполненности должен быть [0..1]."

    churns = [
        params.storage_monthly_churn,
        params.loan_monthly_churn,
        params.vip_monthly_churn,
        params.short_term_monthly_churn,
    ]
    if any(c < 0 or c > 1 for c in churns):
        return False, "Процент оттока должен быть [0..1]."

    if not (1 <= params.poly_degree <= 5):
        return False, "Степень полинома должна быть целым числом от 1 до 5."

    shares_sum = (
        params.storage_share
        + params.loan_share
        + params.vip_share
        + params.short_term_share
    )
    if not np.isclose(shares_sum, 1.0):
        return False, f"Сумма долей должна быть равна 1.0 (сейчас: {shares_sum:.2f})"

    return True, ""