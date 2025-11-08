# service.py
from calculations import (
    calculate_areas,
    calculate_items,
    calculate_financials,
    calculate_irr,
    calculate_monthly_bep,
    calculate_total_bep,
)

def calculate_all(params, disable_extended):
    """Выполняет полный цикл расчётов."""
    areas = calculate_areas(params)
    for k, v in areas.items():
        setattr(params, k, v)


    items_dict = {
        "stored_items": calculate_items(
            params.storage_area,
            params.shelves_per_m2,
            params.storage_items_density,
            params.storage_fill_rate,
        ),
        "total_items_loan": calculate_items(
            params.loan_area,
            params.shelves_per_m2,
            params.loan_items_density,
            params.loan_fill_rate,
        ),
        "vip_stored_items": calculate_items(
            params.vip_area,
            params.shelves_per_m2,
            params.vip_items_density,
            params.vip_fill_rate,
        ),
        "short_term_stored_items": calculate_items(
            params.short_term_area,
            params.shelves_per_m2,
            params.short_term_items_density,
            params.short_term_fill_rate,
        ),
    }

    financials = calculate_financials(params, disable_extended)
    initial_investment = -(params.one_time_setup_cost + params.one_time_equipment_cost
                           + params.one_time_other_costs)
    cash_flows = [initial_investment] + [financials["profit"]] * params.time_horizon
    irr_val = calculate_irr(cash_flows)
    bep_val = calculate_total_bep(financials, params)
    monthly_bep_values = calculate_monthly_bep(financials, params)

    return items_dict, financials, irr_val, bep_val, monthly_bep_values