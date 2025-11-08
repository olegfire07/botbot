# test_calculations.py

import unittest
import numpy as np
import numpy_financial as npf
import pandas as pd
from calculations import (
    calculate_items,
    calculate_total_bep,
    calculate_financials,
    calculate_areas,
    calculate_irr,
    calculate_monthly_bep,
    calculate_additional_metrics,
    calculate_roi,
    monte_carlo_simulation,
    min_loan_amount_for_bep,
    calculate_monthly_projection,  # Если у вас есть новая функция
)
from data_model import WarehouseParams


class TestCalculations(unittest.TestCase):

    def test_calculate_items(self):
        """
        Проверяем базовую функцию calculate_items(area, shelves, density, fill_rate).
        """
        self.assertEqual(calculate_items(10, 3, 5, 1), 150)
        self.assertEqual(calculate_items(0, 3, 5, 1), 0)
        self.assertEqual(calculate_items(10, 0, 5, 1), 0)
        self.assertEqual(calculate_items(10, 3, 0, 1), 0)
        self.assertEqual(calculate_items(10, 3, 5, 0.5), 75)

    def test_calculate_total_bep(self):
        """
        Проверяем функцию calculate_total_bep: 
        BEP = total_expenses + (one_time_expenses / time_horizon).
        """
        params = WarehouseParams(
            total_area=100,
            rental_cost_per_m2=10,
            useful_area_ratio=0.5,
            mode="Ручной",
            storage_share=0.25,
            loan_share=0.25,
            vip_share=0.25,
            short_term_share=0.25,
            storage_area_manual=10.0,
            loan_area_manual=10.0,
            vip_area_manual=10.0,
            short_term_area_manual=10.0,
            storage_fee=15,
            shelves_per_m2=3,
            short_term_daily_rate=6,
            vip_extra_fee=10,
            item_evaluation=0.8,
            item_realization_markup=20.0,
            average_item_value=15000,
            loan_interest_rate=0.317,
            loan_term_days=30,
            realization_share_storage=0.5,
            realization_share_loan=0.5,
            realization_share_vip=0.5,
            realization_share_short_term=0.5,
            storage_items_density=5,
            loan_items_density=1,
            vip_items_density=2,
            short_term_items_density=4,
            storage_fill_rate=1.0,
            loan_fill_rate=1.0,
            vip_fill_rate=1.0,
            short_term_fill_rate=1.0,
            storage_monthly_churn=0.01,
            loan_monthly_churn=0.02,
            vip_monthly_churn=0.005,
            short_term_monthly_churn=0.03,
            salary_expense=240000,
            miscellaneous_expenses=50000,
            depreciation_expense=20000,
            marketing_expenses=30000,
            insurance_expenses=10000,
            taxes=50000,
            utilities_expenses=20000,
            maintenance_expenses=15000,
            one_time_setup_cost=100000,
            one_time_equipment_cost=200000,
            one_time_other_costs=50000,
            one_time_legal_cost=20000,
            one_time_logistics_cost=30000,
            time_horizon=6,
            monthly_rent_growth=0.01,
            default_probability=0.05,
            liquidity_factor=1.0,
            safety_factor=1.2,
            loan_grace_period=0,
            monthly_income_growth=0.0,
            monthly_expenses_growth=0.0,
            forecast_method="Базовый",
            monte_carlo_simulations=100,
            monte_carlo_deviation=0.1,
            monte_carlo_seed=42,
            enable_ml_settings=False,
            electricity_cost_per_m2=100,
            monthly_inflation_rate=0.005,
            monthly_salary_growth=0.005,
            monthly_other_expenses_growth=0.005,
            poly_degree=2,
        )
        # Считаем и устанавливаем площади
        areas = calculate_areas(params)
        for k, v in areas.items():
            setattr(params, k, v)

        financials = calculate_financials(params, disable_extended=False)
        bep = calculate_total_bep(financials, params)
        expected_bep = financials["total_expenses"] + (params.one_time_expenses / params.time_horizon)
        self.assertAlmostEqual(bep, expected_bep, places=2)

    def test_validate_inputs(self):
        """
        Проверяем валидацию входных данных validate_inputs(params).
        """
        from data_model import validate_inputs

        params = WarehouseParams(
            total_area=100,
            rental_cost_per_m2=10,
            useful_area_ratio=0.5,
            mode="Ручной",
            storage_share=0.25,
            loan_share=0.25,
            vip_share=0.25,
            short_term_share=0.25,
            storage_area_manual=10.0,
            loan_area_manual=10.0,
            vip_area_manual=10.0,
            short_term_area_manual=10.0,
            storage_fee=15,
            shelves_per_m2=3,
            short_term_daily_rate=6,
            vip_extra_fee=10,
            item_evaluation=0.8,
            item_realization_markup=20.0,
            average_item_value=15000,
            loan_interest_rate=0.317,
            loan_term_days=30,
            realization_share_storage=0.5,
            realization_share_loan=0.5,
            realization_share_vip=0.5,
            realization_share_short_term=0.5,
            storage_items_density=5,
            loan_items_density=1,
            vip_items_density=2,
            short_term_items_density=4,
            storage_fill_rate=1.0,
            loan_fill_rate=1.0,
            vip_fill_rate=1.0,
            short_term_fill_rate=1.0,
            storage_monthly_churn=0.01,
            loan_monthly_churn=0.02,
            vip_monthly_churn=0.005,
            short_term_monthly_churn=0.03,
            salary_expense=240000,
            miscellaneous_expenses=50000,
            depreciation_expense=20000,
            marketing_expenses=30000,
            insurance_expenses=10000,
            taxes=50000,
            utilities_expenses=20000,
            maintenance_expenses=15000,
            one_time_setup_cost=100000,
            one_time_equipment_cost=200000,
            one_time_other_costs=50000,
            one_time_legal_cost=20000,
            one_time_logistics_cost=30000,
            time_horizon=6,
            monthly_rent_growth=0.01,
            default_probability=0.05,
            liquidity_factor=1.0,
            safety_factor=1.2,
            loan_grace_period=0,
            monthly_income_growth=0.0,
            monthly_expenses_growth=0.0,
            forecast_method="Базовый",
            monte_carlo_simulations=100,
            monte_carlo_deviation=0.1,
            monte_carlo_seed=42,
            enable_ml_settings=False,
            electricity_cost_per_m2=100,
            monthly_inflation_rate=0.005,
            monthly_salary_growth=0.005,
            monthly_other_expenses_growth=0.005,
            poly_degree=2,
        )

        # Должно быть валидно
        is_valid, error_message = validate_inputs(params)
        self.assertTrue(is_valid)

        # Отрицательная площадь
        params.total_area = -10
        is_valid, error_message = validate_inputs(params)
        self.assertFalse(is_valid)
        self.assertEqual(error_message, "Общая площадь должна быть числом больше нуля.")

        # Нулевой срок займа
        params.total_area = 100
        params.loan_term_days = 0
        is_valid, error_message = validate_inputs(params)
        self.assertFalse(is_valid)
        self.assertEqual(error_message, "Срок займа должен быть целым числом больше 0.")

        # Проверяем полином
        params.loan_term_days = 30
        params.poly_degree = 0
        is_valid, error_message = validate_inputs(params)
        self.assertFalse(is_valid)
        self.assertEqual(error_message, "Степень полинома должна быть целым числом от 1 до 5.")

        params.poly_degree = 6
        is_valid, error_message = validate_inputs(params)
        self.assertFalse(is_valid)
        self.assertEqual(error_message, "Степень полинома должна быть целым числом от 1 до 5.")

    def test_calculate_irr(self):
        """
        Проверяем IRR — сравниваем с npf.irr.
        """
        cash_flows = [-100000, 30000, 40000, 50000]
        irr = calculate_irr(cash_flows)
        expected_irr = npf.irr(cash_flows) * 100
        self.assertAlmostEqual(irr, expected_irr, places=2)

    def test_calculate_monthly_bep(self):
        """
        Проверяем calculate_monthly_bep. 
        Обратите внимание, что функция возвращает DataFrame 
        с колонкой "Необходимый доход для BEP" (или другой, если поменяли).
        """
        params = WarehouseParams(
            total_area=100,
            rental_cost_per_m2=10,
            useful_area_ratio=0.5,
            mode="Ручной",
            storage_share=0.25,
            loan_share=0.25,
            vip_share=0.25,
            short_term_share=0.25,
            storage_area_manual=10.0,
            loan_area_manual=10.0,
            vip_area_manual=10.0,
            short_term_area_manual=10.0,
            storage_fee=15,
            shelves_per_m2=3,
            short_term_daily_rate=6,
            vip_extra_fee=10,
            item_evaluation=0.8,
            item_realization_markup=20.0,
            average_item_value=15000,
            loan_interest_rate=0.317,
            loan_term_days=30,
            realization_share_storage=0.5,
            realization_share_loan=0.5,
            realization_share_vip=0.5,
            realization_share_short_term=0.5,
            storage_items_density=5,
            loan_items_density=1,
            vip_items_density=2,
            short_term_items_density=4,
            storage_fill_rate=1.0,
            loan_fill_rate=1.0,
            vip_fill_rate=1.0,
            short_term_fill_rate=1.0,
            storage_monthly_churn=0.01,
            loan_monthly_churn=0.02,
            vip_monthly_churn=0.005,
            short_term_monthly_churn=0.03,
            salary_expense=240000,
            miscellaneous_expenses=50000,
            depreciation_expense=20000,
            marketing_expenses=30000,
            insurance_expenses=10000,
            taxes=50000,
            utilities_expenses=20000,
            maintenance_expenses=15000,
            one_time_setup_cost=100000,
            one_time_equipment_cost=200000,
            one_time_other_costs=50000,
            one_time_legal_cost=20000,
            one_time_logistics_cost=30000,
            time_horizon=6,
            monthly_rent_growth=0.01,
            default_probability=0.05,
            liquidity_factor=1.0,
            safety_factor=1.2,
            loan_grace_period=0,
            monthly_income_growth=0.0,
            monthly_expenses_growth=0.0,
            forecast_method="Базовый",
            monte_carlo_simulations=100,
            monte_carlo_deviation=0.1,
            monte_carlo_seed=42,
            enable_ml_settings=False,
            electricity_cost_per_m2=100,
            monthly_inflation_rate=0.005,
            monthly_salary_growth=0.005,
            monthly_other_expenses_growth=0.005,
            poly_degree=2,
        )
        areas = calculate_areas(params)
        for k, v in areas.items():
            setattr(params, k, v)

        financials = calculate_financials(params, disable_extended=False)
        monthly_bep_df = calculate_monthly_bep(financials, params)

        # Убедимся, что DataFrame есть и там есть столбец "Необходимый доход для BEP"
        self.assertIsInstance(monthly_bep_df, pd.DataFrame)
        self.assertIn("Месяц", monthly_bep_df.columns)
        self.assertIn("Необходимый доход для BEP", monthly_bep_df.columns)
        self.assertEqual(len(monthly_bep_df), params.time_horizon)
        self.assertTrue(all(monthly_bep_df["Необходимый доход для BEP"] >= 0))

        # Проверка без роста
        params.monthly_rent_growth = 0
        params.monthly_salary_growth = 0
        params.monthly_other_expenses_growth = 0
        areas = calculate_areas(params)
        for k, v in areas.items():
            setattr(params, k, v)
        financials_no_growth = calculate_financials(params, disable_extended=False)
        monthly_bep_df_no_growth = calculate_monthly_bep(financials_no_growth, params)

        # Теперь этот DataFrame тоже имеет "Необходимый доход для BEP".
        # Проверяем, что без роста все месяцы одинаковые
        diff_all_zeros = (monthly_bep_df_no_growth["Необходимый доход для BEP"].diff()[1:] == 0)
        self.assertTrue(all(diff_all_zeros))

    def test_calculate_areas(self):
        """
        Проверяем корректность распределения площадей.
        """
        params = WarehouseParams(
            total_area=100,
            rental_cost_per_m2=10,
            useful_area_ratio=0.7,
            mode="Ручной",
            storage_share=0.25,
            loan_share=0.25,
            vip_share=0.25,
            short_term_share=0.25,
            storage_area_manual=20.0,
            loan_area_manual=15.0,
            vip_area_manual=10.0,
            short_term_area_manual=5.0,
            storage_fee=15,
            shelves_per_m2=3,
            short_term_daily_rate=6,
            vip_extra_fee=10,
            item_evaluation=0.8,
            item_realization_markup=20.0,
            average_item_value=15000,
            loan_interest_rate=0.317,
            loan_term_days=30,
            realization_share_storage=0.5,
            realization_share_loan=0.5,
            realization_share_vip=0.5,
            realization_share_short_term=0.5,
            storage_items_density=5,
            loan_items_density=1,
            vip_items_density=2,
            short_term_items_density=4,
            storage_fill_rate=1.0,
            loan_fill_rate=1.0,
            vip_fill_rate=1.0,
            short_term_fill_rate=1.0,
            storage_monthly_churn=0.01,
            loan_monthly_churn=0.02,
            vip_monthly_churn=0.005,
            short_term_monthly_churn=0.03,
            salary_expense=240000,
            miscellaneous_expenses=50000,
            depreciation_expense=20000,
            marketing_expenses=30000,
            insurance_expenses=10000,
            taxes=50000,
            utilities_expenses=20000,
            maintenance_expenses=15000,
            one_time_setup_cost=100000,
            one_time_equipment_cost=200000,
            one_time_other_costs=50000,
            one_time_legal_cost=20000,
            one_time_logistics_cost=30000,
            time_horizon=6,
            monthly_rent_growth=0.01,
            default_probability=0.05,
            liquidity_factor=1.0,
            safety_factor=1.2,
            loan_grace_period=0,
            monthly_income_growth=0.0,
            monthly_expenses_growth=0.0,
            forecast_method="Базовый",
            monte_carlo_simulations=100,
            monte_carlo_deviation=0.1,
            monte_carlo_seed=42,
            enable_ml_settings=False,
            electricity_cost_per_m2=100,
            monthly_inflation_rate=0.005,
            monthly_salary_growth=0.005,
            monthly_other_expenses_growth=0.005,
             poly_degree=2,
        )
        areas = calculate_areas(params)
        self.assertAlmostEqual(areas["storage_area"], 20.0)
        self.assertAlmostEqual(areas["loan_area"], 15.0)
        self.assertAlmostEqual(areas["vip_area"], 10.0)
        self.assertAlmostEqual(areas["short_term_area"], 5.0)
        self.assertAlmostEqual(areas["usable_area"], params.total_area * params.useful_area_ratio)

    def test_calculate_financials(self):
        """
        Проверяем общий расчёт calculate_financials за 1 месяц (доходы, расходы, прибыль).
        """
        params = WarehouseParams(
            total_area=100,
            rental_cost_per_m2=100,
            useful_area_ratio=0.7,
            mode="Ручной",
            storage_share=0.25,
            loan_share=0.25,
            vip_share=0.25,
            short_term_share=0.25,
            storage_area_manual=20.0,
            loan_area_manual=15.0,
            vip_area_manual=10.0,
            short_term_area_manual=5.0,
            storage_fee=1500,
            shelves_per_m2=3,
            short_term_daily_rate=60,
            vip_extra_fee=1000,
            item_evaluation=0.8,
            item_realization_markup=20.0,
            average_item_value=15000,
            loan_interest_rate=0.317,
            loan_term_days=30,
            realization_share_storage=0.5,
            realization_share_loan=0.5,
            realization_share_vip=0.5,
            realization_share_short_term=0.5,
            storage_items_density=5,
            loan_items_density=1,
            vip_items_density=2,
            short_term_items_density=4,
            storage_fill_rate=1.0,
            loan_fill_rate=1.0,
            vip_fill_rate=1.0,
            short_term_fill_rate=1.0,
            storage_monthly_churn=0.01,
            loan_monthly_churn=0.02,
            vip_monthly_churn=0.005,
            short_term_monthly_churn=0.03,
            salary_expense=240000,
            miscellaneous_expenses=50000,
            depreciation_expense=20000,
            marketing_expenses=30000,
            insurance_expenses=10000,
            taxes=50000,
            utilities_expenses=20000,
            maintenance_expenses=15000,
            one_time_setup_cost=100000,
            one_time_equipment_cost=200000,
            one_time_other_costs=50000,
            one_time_legal_cost=20000,
            one_time_logistics_cost=30000,
            time_horizon=6,
            monthly_rent_growth=0.01,
            default_probability=0.05,
            liquidity_factor=1.0,
            safety_factor=1.2,
            loan_grace_period=0,
            monthly_income_growth=0.0,
            monthly_expenses_growth=0.0,
            forecast_method="Базовый",
            monte_carlo_simulations=100,
            monte_carlo_deviation=0.1,
            monte_carlo_seed=42,
            enable_ml_settings=False,
            electricity_cost_per_m2=100,
            monthly_inflation_rate=0.005,
            monthly_salary_growth=0.005,
            monthly_other_expenses_growth=0.005,
            poly_degree=2,
        )
        areas = calculate_areas(params)
        for k, v in areas.items():
            setattr(params, k, v)

        fin = calculate_financials(params, disable_extended=False)

        # Доход (хранение)
        expected_storage_income = params.storage_area * params.storage_fee
        expected_vip_income = params.vip_area * (params.storage_fee + params.vip_extra_fee)
        expected_short_term_income = params.short_term_area * params.short_term_daily_rate * 30

        # Займы 
        from calculations import calculate_items
        loan_items = calculate_items(
            params.loan_area,
            params.shelves_per_m2,
            params.loan_items_density,
            params.loan_fill_rate
        )
        loan_evaluated_value = (
            params.average_item_value
            * params.item_evaluation
            * loan_items
        )
        daily_loan_rate = max(params.loan_interest_rate / 100.0, 0)
        # Если реализация_доля = 0.5, тогда половина вещей идет на проценты, половина — на реализацию
        interest_part = loan_items * (1 - params.realization_share_loan)
        real_part = loan_items * params.realization_share_loan
        
        loan_evaluated_interest = interest_part * params.average_item_value * params.item_evaluation
        expected_loan_interest = (
            loan_evaluated_interest
            * daily_loan_rate
            * params.loan_term_days
            * (1 - params.default_probability)
        )
        loan_evaluated_real = real_part * params.average_item_value * params.item_evaluation
        expected_loan_real = loan_evaluated_real * (params.item_realization_markup / 100.0)
        expected_loan_income = expected_loan_interest + expected_loan_real

        # Реализация storage / vip / short_term
        def calc_real(items):
            return (
                params.average_item_value
                * params.item_evaluation
                * items
                * (params.item_realization_markup / 100)
            )
        storage_items = calculate_items(
            params.storage_area, params.shelves_per_m2, params.storage_items_density, params.storage_fill_rate
        )
        vip_items = calculate_items(
            params.vip_area, params.shelves_per_m2, params.vip_items_density, params.vip_fill_rate
        )
        short_term_items = calculate_items(
            params.short_term_area, params.shelves_per_m2, params.short_term_items_density, params.short_term_fill_rate
        )
        expected_storage_real = calc_real(storage_items * params.realization_share_storage)
        expected_vip_real = calc_real(vip_items * params.realization_share_vip)
        expected_short_real = calc_real(short_term_items * params.realization_share_short_term)

        expected_realization_income = (
            expected_storage_real
            + expected_vip_real
            + expected_short_real
        )

        # Итого доход
        expected_total_income = (
            expected_storage_income
            + expected_vip_income
            + expected_short_term_income
            + expected_loan_income
            + expected_realization_income
        )

        # Расходы
        monthly_rent = params.total_area * params.rental_cost_per_m2
        electricity_cost = params.total_area * params.electricity_cost_per_m2
        packaging_cost = params.total_area * params.packaging_cost_per_m2
        expected_total_monthly_expenses = (
            monthly_rent
            + params.salary_expense
            + packaging_cost
            + params.miscellaneous_expenses
            + params.depreciation_expense
            + params.marketing_expenses
            + params.insurance_expenses
            + params.taxes
            + params.utilities_expenses
            + params.maintenance_expenses
            + electricity_cost
        )

        # Сравниваем фактические результаты с ожидаемыми
        self.assertAlmostEqual(fin["storage_income"], expected_storage_income, places=2)
        self.assertAlmostEqual(fin["vip_income"], expected_vip_income, places=2)
        self.assertAlmostEqual(fin["short_term_income"], expected_short_term_income, places=2)

        # Основная разница может быть в loan_income, т.к. разделили (проценты + реализация)
        self.assertAlmostEqual(fin["loan_income"], expected_loan_income, places=2)

        self.assertAlmostEqual(fin["realization_income"], expected_realization_income, places=2)
        self.assertAlmostEqual(fin["total_income"], expected_total_income, places=2)

        self.assertAlmostEqual(fin["total_expenses"], expected_total_monthly_expenses, places=2)

        # Проверяем единовременные
        params.one_time_setup_cost = 100000
        params.time_horizon = 6
        areas = calculate_areas(params)
        for k, v in areas.items():
            setattr(params, k, v)
        fin_onetime = calculate_financials(params, disable_extended=False)
        # profit = total_income - total_monthly_expenses - (one_time_expenses / horizon)
        expected_profit = (
            expected_total_income
            - expected_total_monthly_expenses
            - params.one_time_expenses / params.time_horizon
        )
        self.assertAlmostEqual(fin_onetime["profit"], expected_profit, places=2)

        # Зануляем единовременные 
        params.one_time_setup_cost = 0
        params.one_time_equipment_cost = 0
        params.one_time_other_costs = 0
        params.one_time_legal_cost = 0
        params.one_time_logistics_cost = 0
        areas = calculate_areas(params)
        for k, v in areas.items():
            setattr(params, k, v)
        fin_zero_onetime = calculate_financials(params, disable_extended=False)
        expected_profit_no_onetime = (
            expected_total_income
            - expected_total_monthly_expenses
        )
        self.assertAlmostEqual(fin_zero_onetime["profit"], expected_profit_no_onetime, places=2)

    def test_calculate_additional_metrics(self):
        """
        Проверяем calculate_additional_metrics (маржа, рентабельность).
        """
        pm, pr = calculate_additional_metrics(100000, 80000, 20000)
        # pm = (profit / total_income) * 100 => (20000 / 100000)*100 = 20
        # pr = (profit / total_expenses)*100 => (20000 / 80000)*100 = 25
        self.assertAlmostEqual(pm, 20.0)
        self.assertAlmostEqual(pr, 25.0)

    def test_calculate_roi(self):
        """
        Проверяем ROI.
        """
        self.assertAlmostEqual(calculate_roi(100000, 80000), 25.0)
        self.assertIsNone(calculate_roi(100000, 0))

    def test_monte_carlo_simulation(self):
        """
        Проверяем монте-карло симуляцию доходов/расходов.
        """
        base_income = 100000
        base_expenses = 80000
        time_horizon = 6
        simulations = 100
        deviation = 0.1
        seed = 42
        monthly_income_growth = 0.01
        monthly_expenses_growth = 0.01

        df_mc = monte_carlo_simulation(
            base_income,
            base_expenses,
            time_horizon,
            simulations,
            deviation,
            seed,
            monthly_income_growth,
            monthly_expenses_growth,
        )
        self.assertIsInstance(df_mc, pd.DataFrame)
        self.assertEqual(len(df_mc), time_horizon)
        self.assertIn("Месяц", df_mc.columns)
        self.assertIn("Средний Доход", df_mc.columns)
        self.assertIn("Средний Расход", df_mc.columns)
        self.assertIn("Средняя Прибыль", df_mc.columns)

        # Простейшие проверки на диапазон значений
        self.assertTrue(all(df_mc["Средний Доход"] > base_income * 0.9))
        self.assertTrue(
            all(
                df_mc["Средний Доход"]
                < base_income
                * (1 + monthly_income_growth * time_horizon)
                * (1 + deviation)
            )
        )

    def test_min_loan_amount_for_bep(self):
        """
        Проверяем min_loan_amount_for_bep: 
        сколько нужно на одну вещь, чтобы покрыть расходы?
        """
        params = WarehouseParams(
            total_area=100,
            rental_cost_per_m2=10,
            useful_area_ratio=0.5,
            mode="Ручной",
            storage_share=0.25,
            loan_share=0.25,
            vip_share=0.25,
            short_term_share=0.25,
            storage_area_manual=10.0,
            loan_area_manual=10.0,
            vip_area_manual=10.0,
            short_term_area_manual=10.0,
            storage_fee=15,
            shelves_per_m2=3,
            short_term_daily_rate=6,
            vip_extra_fee=10,
            item_evaluation=0.8,
            item_realization_markup=20.0,
            average_item_value=15000,
            loan_interest_rate=0.317,
            loan_term_days=30,
            realization_share_storage=0.5,
            realization_share_loan=0.5,
            realization_share_vip=0.5,
            realization_share_short_term=0.5,
            storage_items_density=5,
            loan_items_density=1,
            vip_items_density=2,
            short_term_items_density=4,
            storage_fill_rate=1.0,
            loan_fill_rate=1.0,
            vip_fill_rate=1.0,
            short_term_fill_rate=1.0,
            storage_monthly_churn=0.01,
            loan_monthly_churn=0.02,
            vip_monthly_churn=0.005,
            short_term_monthly_churn=0.03,
            salary_expense=240000,
            miscellaneous_expenses=50000,
            depreciation_expense=20000,
            marketing_expenses=30000,
            insurance_expenses=10000,
            taxes=50000,
            utilities_expenses=20000,
            maintenance_expenses=15000,
            one_time_setup_cost=100000,
            one_time_equipment_cost=200000,
            one_time_other_costs=50000,
            one_time_legal_cost=20000,
            one_time_logistics_cost=30000,
            time_horizon=6,
            monthly_rent_growth=0.01,
            default_probability=0.05,
            liquidity_factor=1.0,
            safety_factor=1.2,
            loan_grace_period=0,
            monthly_income_growth=0.0,
            monthly_expenses_growth=0.0,
            forecast_method="Базовый",
            monte_carlo_simulations=100,
            monte_carlo_deviation=0.1,
            monte_carlo_seed=42,
            enable_ml_settings=False,
            electricity_cost_per_m2=100,
            monthly_inflation_rate=0.005,
            monthly_salary_growth=0.005,
            monthly_other_expenses_growth=0.005,
             poly_degree=2,
        )
        areas = calculate_areas(params)
        for k, v in areas.items():
            setattr(params, k, v)
        financials = calculate_financials(params, disable_extended=False)
        minimum_loan = min_loan_amount_for_bep(params, financials)
        # Просто проверяем, что значение >= 0
        self.assertGreaterEqual(minimum_loan, 0)

    # ----------------------------------------
    # Дополнительные тесты для большего покрытия
    # ----------------------------------------
    def test_calculate_monthly_projection(self):
        """
        Если у вас есть функция calculate_monthly_projection 
        (помесячный расчёт доходов/расходов), проверяем её.
        """
        # Проверим, что функция не падает и даёт DataFrame
        try:
            from calculations import calculate_monthly_projection
        except ImportError:
            self.skipTest("calculate_monthly_projection отсутствует в calculations.py")

        params = WarehouseParams(
            total_area=120,
            rental_cost_per_m2=50,
            useful_area_ratio=0.8,
            mode="Ручной",
            storage_share=0.25,
            loan_share=0.25,
            vip_share=0.25,
            short_term_share=0.25,
            storage_area_manual=20.0,
            loan_area_manual=20.0,
            vip_area_manual=20.0,
            short_term_area_manual=20.0,
            storage_fee=200,
            shelves_per_m2=2,
            short_term_daily_rate=20,
            vip_extra_fee=100,
            item_evaluation=0.7,
            item_realization_markup=15.0,
            average_item_value=10000,
            loan_interest_rate=0.2,
            loan_term_days=15,
            realization_share_storage=0.2,
            realization_share_loan=0.3,
            realization_share_vip=0.1,
            realization_share_short_term=0.05,
            storage_items_density=3,
            loan_items_density=2,
            vip_items_density=2,
            short_term_items_density=4,
            storage_fill_rate=1.0,
            loan_fill_rate=1.0,
            vip_fill_rate=1.0,
            short_term_fill_rate=1.0,
            storage_monthly_churn=0.05,
            loan_monthly_churn=0.06,
            vip_monthly_churn=0.03,
            short_term_monthly_churn=0.04,
            salary_expense=100000,
            miscellaneous_expenses=20000,
            depreciation_expense=15000,
            marketing_expenses=10000,
            insurance_expenses=5000,
            taxes=20000,
            utilities_expenses=10000,
            maintenance_expenses=8000,
            one_time_setup_cost=50000,
            one_time_equipment_cost=80000,
            one_time_other_costs=20000,
            one_time_legal_cost=10000,
            one_time_logistics_cost=15000,
            time_horizon=6,
            monthly_rent_growth=0.02,
            default_probability=0.05,
            liquidity_factor=1.0,
            safety_factor=1.2,
            loan_grace_period=0,
            monthly_income_growth=0.01,
            monthly_expenses_growth=0.01,
            forecast_method="Базовый",
            monte_carlo_simulations=100,
            monte_carlo_deviation=0.1,
            monte_carlo_seed=42,
            enable_ml_settings=False,
            electricity_cost_per_m2=50,
            monthly_inflation_rate=0.005,
            monthly_salary_growth=0.005,
            monthly_other_expenses_growth=0.005,
             poly_degree=2,
        )
        # Считаем "статичную" базу
        areas = calculate_areas(params)
        for k, v in areas.items():
            setattr(params, k, v)
        base_fin = calculate_financials(params, disable_extended=False)

        try:
            self._extracted_from_test_calculate_monthly_projection_89(
                calculate_monthly_projection, params, base_fin
            )
        except Exception as e:
            self.fail(f"calculate_monthly_projection вызвало исключение: {e}")

    # TODO Rename this here and in `test_calculate_monthly_projection`
    def _extracted_from_test_calculate_monthly_projection_89(self, calculate_monthly_projection, params, base_fin):
        df_proj = calculate_monthly_projection(params, base_fin)
        self.assertIsInstance(df_proj, pd.DataFrame)
        self.assertIn("Месяц", df_proj.columns)
        self.assertIn("Доход", df_proj.columns)
        self.assertIn("Расход", df_proj.columns)
        self.assertIn("Прибыль", df_proj.columns)
        self.assertEqual(len(df_proj), params.time_horizon)


if __name__ == "__main__":
    unittest.main()