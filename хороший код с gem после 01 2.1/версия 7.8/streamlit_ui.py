# streamlit_ui.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from utils import generate_download_link, generate_excel_download
from calculations import (
    calculate_additional_metrics,
    calculate_roi,
    calculate_irr,
    calculate_total_bep,
    monte_carlo_simulation,
    calculate_financials,
    min_loan_amount_for_bep,
    calculate_monthly_bep,
    calculate_npv
)
from ml_models import predict_with_model


class MetricDisplay:
    def __init__(self, label):
        self.label = label

    def display(self, col, value):
        col.metric(self.label, f"{value:,.2f}")


class ChartDisplay:
    def __init__(self, title, x_title="", y_title="Рубли", color_map=None):
        self.title = title
        self.x_title = x_title
        self.y_title = y_title
        self.color_map = color_map

    def display_bar(self, df, x, y, **kwargs):
        fig = px.bar(
            df, x=x, y=y, title=self.title, text=y, color=x,
            color_discrete_map=self.color_map, **kwargs
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis_title=self.y_title, xaxis_title=self.x_title)
        st.plotly_chart(fig, use_container_width=True)

    def display_line(self, df, x, y, markers=True, color=None, y_range=None, **kwargs):
        fig = px.line(
            df, x=x, y=y, title=self.title, markers=markers, color=color, **kwargs
        )
        if y_range:
            fig.update_layout(yaxis={"range": y_range})
        fig.update_layout(
            xaxis_title=self.x_title,
            yaxis_title=self.y_title
        )
        st.plotly_chart(fig, use_container_width=True)

    def display_interactive_line(self, df, x, y, color=None, **kwargs):
        """Вывод интерактивного графика."""
        fig = px.line(
            df, x=x, y=y, title=self.title, color=color, **kwargs
        )
        fig.update_layout(xaxis_title=self.x_title, yaxis_title=self.y_title)
        st.plotly_chart(fig, use_container_width=True)

    def display_heatmap(self, df, x_title="", y_title="", **kwargs):
        """Вывод хитмапа."""
        fig = px.imshow(
            df,
            title=self.title,
            color_continuous_scale="viridis",
            **kwargs
        )
        fig.update_layout(xaxis_title=x_title, yaxis_title=y_title)
        st.plotly_chart(fig, use_container_width=True)


class TableDisplay:
    def display(self, df):
        st.dataframe(df)


def display_tab1_header(tab, main_color="#007bff"):
    with tab:
        st.markdown(f"""
            <style>
                .main-header {{
                color: {main_color};
                }}
            </style>
            """, unsafe_allow_html=True)
        st.markdown('<h1 class="main-header">📊 Общие результаты</h1>', unsafe_allow_html=True)
        st.write("Ключевые финансовые показатели текущей конфигурации склада.")
        st.info(
            "Здесь вы видите доходы, расходы, прибыль, ROI, IRR и др. "
            "Используйте эти показатели, чтобы оценить эффективность хранения. "
            "Например, если IRR и ROI высокие, склад может быть привлекательным для инвестиций."
        )


def display_tab1_metrics(tab, base_financials, profit_margin, profitability, roi, irr, npv):
    with tab:
        col1, col2, col3 = st.columns(3)
        MetricDisplay("Общий доход (руб.)").display(col1, base_financials["total_income"])
        MetricDisplay("Общие расходы (руб.)").display(col2, base_financials["total_expenses"])
        MetricDisplay("Прибыль (руб.)").display(col3, base_financials["profit"])

        col4, col5 = st.columns(2)
        MetricDisplay("Маржа прибыли (%)").display(col4, profit_margin)
        MetricDisplay("Рентабельность (%)").display(col5, profitability)

        col6, col7, col8 = st.columns(3)
        MetricDisplay("ROI (%)").display(col6, roi if roi is not None else 0)
        col7.metric("IRR (%)", f"{irr:.2f}%")
        MetricDisplay("NPV (руб.)").display(col8, npv)


def display_tab1_bep(tab, params, base_financials):
    with tab:
        st.write("---")
        st.subheader("Мин. сумма займа для BEP (займы)")
        min_loan = min_loan_amount_for_bep(params, base_financials)
        if np.isinf(min_loan):
            st.write("**Бесконечность** — невозможно покрыть расходы.")
        else:
            st.write(f"**{min_loan:,.2f} руб.** — минимальная сумма займа для точки безубыточности.")


def display_tab1_chart(tab, base_financials):
    with tab:
        df_plot = pd.DataFrame({
            "Категория": ["Доход", "Расход"],
            "Значение": [
                base_financials["total_income"],
                base_financials["total_expenses"]
            ]
        })
        chart_display = ChartDisplay(
            "Доходы и расходы",
            color_map={"Доход": "green", "Расход": "red"}
        )
        chart_display.display_bar(df_plot, "Категория", "Значение")


def display_tab1_analysis(tab, base_financials, profit_margin, profitability, roi, irr):
    with tab:
        st.write("---")
        st.subheader("Анализ результатов")
        profit = base_financials["profit"]

        if profit > 0:
            st.success("✅ Конфигурация прибыльна.")
        elif profit < 0:
            st.error("❌ Конфигурация убыточна.")
        else:
            st.info("⚠️ Прибыль = 0 (точка безубыточности).")

        if profit_margin > 10:
            st.success(f"✅ Маржа прибыли высокая ({profit_margin:.2f}%).")
        elif profit_margin < 0:
            st.error(f"❌ Маржа прибыли отрицательная ({profit_margin:.2f}%).")
        else:
            st.info(f"⚠️ Маржа прибыли: {profit_margin:.2f}%.")

        if profitability > 15:
            st.success(f"✅ Высокая рентабельность ({profitability:.2f}%).")
        elif profitability < 0:
            st.error(f"❌ Рентабельность отрицательная ({profitability:.2f}%).")
        else:
            st.info(f"⚠️ Рентабельность: {profitability:.2f}%.")

        if roi is None:
            st.warning("⚠️ Невозможно вычислить ROI, т.к. расходы = 0.")
        elif roi > 10:
            st.success(f"✅ ROI высокий ({roi:.2f}%).")
        elif roi < 0:
            st.error(f"❌ ROI отрицательный ({roi:.2f}%).")
        else:
            st.info(f"⚠️ ROI: {roi:.2f}%.")

        if irr > 10:
            st.success(f"✅ IRR высокий ({irr:.2f}%).")
        elif irr < 0:
            st.error(f"❌ IRR отрицательный ({irr:.2f}%).")
        else:
            st.info(f"⚠️ IRR: {irr:.2f}%.")


def display_tab1(
    tab,
    base_financials,
    pm,
    pr,
    roi_val,
    irr_val,
    params,
    selected_param=None,
    main_color="#007bff",
    npv=0.0
):
    display_tab1_header(tab, main_color)
    display_tab1_metrics(tab, base_financials, pm, pr, roi_val, irr_val, npv)
    display_tab1_bep(tab, params, base_financials)
    display_tab1_chart(tab, base_financials)
    display_tab1_analysis(tab, base_financials, pm, pr, roi_val, irr_val)
    with tab:
        st.markdown("""
        <b>Основные термины:</b><br/>
        <ul>
          <li><b>Прибыль</b>: доходы - расходы</li>
          <li><b>Маржа прибыли</b>: (прибыль / доходы)*100</li>
          <li><b>Рентабельность</b>: (прибыль / расходы)*100</li>
          <li><b>ROI</b>: ((доходы - расходы)/расходы)*100, показывает возврат на инвестиции</li>
          <li><b>IRR</b>: внутренняя норма доходности (показывает доходность проекта с учётом дисконтирования)</li>
           <li><b>NPV</b>: чистая приведенная стоимость (показывает текущую стоимость будущих денежных потоков)</li>
        </ul>
        """, unsafe_allow_html=True)

        if selected_param:
            st.write("---")
            st.subheader("Сравнение сохранённых параметров")
            compare_params(tab, params, selected_param)

        st.write("---")
        st.subheader("Документация")
        with open("help.md", "r") as f:
            help_text = f.read()
            st.markdown(help_text)


def display_tab2_header(tab):
    with tab:
        st.header("📈 Прогнозирование")


def display_tab2_basic_forecast(tab, base_financials, params):
    with tab:
        st.subheader("Базовый прогноз (линейная динамика)")
        df_projection = pd.DataFrame({
            "Месяц": range(1, params.time_horizon + 1),
            "Доходы": np.linspace(
                base_financials["total_income"],
                base_financials["total_income"] * (1 + params.monthly_income_growth * params.time_horizon),
                params.time_horizon,
            ),
            "Расходы": np.linspace(
                base_financials["total_expenses"],
                base_financials["total_expenses"] * (1 + params.monthly_expenses_growth * params.time_horizon),
                params.time_horizon,
            ),
        })
        df_projection["Прибыль"] = df_projection["Доходы"] - df_projection["Расходы"]
        df_projection["Прибыль (%)"] = (df_projection["Прибыль"] / df_projection["Расходы"] * 100)
        df_long = df_projection.melt(
            id_vars="Месяц",
            value_vars=["Доходы", "Расходы", "Прибыль", "Прибыль (%)"],
            var_name="Показатель",
            value_name="Значение"
        )
        chart = ChartDisplay("Прогноз (базовый)")
        chart.display_line(df_long, "Месяц", "Значение", color="Показатель")


def _extracted_from_display_tab2_ml_forecast_39(df_for_ml, ml_model, params, base_financials):
    from ml_models import prepare_ml_data
    df_prepared = prepare_ml_data(df_for_ml, target_column="Доходы")
    predictions, intervals = predict_with_model(
        ml_model,
        df_prepared,
        list(range(1, params.time_horizon + 1)),
        features=params.features,
        auto_feature_selection=params.auto_feature_selection
    )
    df_ml = pd.DataFrame({"Месяц": range(1, params.time_horizon + 1), "Прогноз Доходы": predictions})
    if intervals is not None:
        df_ml["Нижняя граница"] = intervals[:, 0]
        df_ml["Верхняя граница"] = intervals[:, 1]
        ChartDisplay("Прогноз доходов (ML)", y_title="Рубли").display_line(
            df_ml, "Месяц", ["Прогноз Доходы", "Нижняя граница", "Верхняя граница"], color="Прогноз Доходы"
        )
    else:
        ChartDisplay("Прогноз доходов (ML)", y_title="Рубли").display_line(
            df_ml, "Месяц", "Прогноз Доходы", color="Прогноз Доходы"
        )
    st.dataframe(df_ml.style.format({"Прогноз Доходы": "{:,.2f} руб."}))

    # Прогноз прибыли
    start_income = base_financials["total_income"]
    start_expenses = base_financials["total_expenses"]
    future_months = list(range(1, params.time_horizon + 1))
    monthly_incomes = start_income * (1 + params.monthly_income_growth) ** (np.array(future_months) - 1)
    monthly_expenses = np.linspace(
        start_expenses,
        start_expenses * (1 + params.monthly_expenses_growth * params.time_horizon),
        params.time_horizon,
    )
    df_profit_ml = pd.DataFrame({"Месяц": future_months,
                                 "Прогноз Прибыль": predictions - monthly_expenses[:len(predictions)]})
    ChartDisplay("Прогноз прибыли (ML)").display_line(
        df_profit_ml, "Месяц", "Прогноз Прибыль", color="Прогноз Прибыль"
    )

    from ml_models import calculate_metrics
    try:
        # Проверка auto_feature_selection
        if params.auto_feature_selection and params.features is not None and len(params.features) > 1:
            from sklearn.feature_selection import SelectKBest, f_regression
            selector = SelectKBest(score_func=f_regression, k=min(3, len(params.features)))
            X = df_prepared[params.features].values
            selector.fit(X, df_prepared["Доходы"].values)
            selected_features = [params.features[i] for i in selector.get_support(indices=True)]
            y_pred = ml_model.predict(df_prepared[selected_features].values)
        else:
            X = df_prepared[params.features].values
            y_pred = ml_model.predict(X)

        y_true = df_prepared["Доходы"].values
        rmse, r2, mae = calculate_metrics(y_true, y_pred)
        st.write(f"**RMSE:** {rmse:.2f}, **R2:** {r2:.2f}, **MAE:** {mae:.2f}")
    except Exception as e:
        st.warning(f"Ошибка при расчёте RMSE:{e}")


def display_tab2_ml_forecast(
    tab,
    enable_ml_settings,
    selected_forecast_method,
    ml_model,
    df_for_ml,
    params,
    base_financials
):
    with tab:
        if enable_ml_settings:
            st.subheader("ML-прогноз (машинное обучение)")
            st.write("Данный метод использует исторические данные для прогнозирования доходов.")

            # Если ещё не обучали модель — кнопка "Обучить модель" (уже в main.py тоже)
            import ml_models
            if st.button("Обучить модель", key="train_model_btn"):
                if df_for_ml is not None:
                    try:
                        new_model = ml_models.train_ml_model(
                            df_for_ml,
                            target_column="Доходы",
                            model_type=params.forecast_method,
                            poly_degree=params.poly_degree,
                            n_estimators=params.n_estimators,
                            features=params.features,
                            param_search_method=params.param_search_method,
                            auto_feature_selection=params.auto_feature_selection
                        )
                        st.session_state["ml_model"] = new_model
                        st.success("Модель обучена! Теперь прогноз отобразится ниже.")
                    except Exception as e:
                        st.error(f"Ошибка при обучении модели: {e}")
                else:
                    st.warning("Нет данных для обучения (файл CSV/Excel не загружен).")

            if ml_model is not None and df_for_ml is not None:
                with st.spinner("Выполняется прогноз..."):
                    _extracted_from_display_tab2_ml_forecast_39(
                        df_for_ml, ml_model, params, base_financials
                    )
            else:
                st.info("ML-модель не обучена или нет данных для обучения.")
        else:
            st.warning("Расширенный ML-прогноз отключён.")


def _extracted_from_display_tab2_monte_carlo_55(num_simulations, arg1, months, arg3):
    """Для оптимизации фрагментации DataFrame собираем сразу в dict, потом один вызов DataFrame()."""
    data = {f"Симуляция {i + 1}": arg1[i] for i in range(num_simulations)}
    data["Месяц"] = months
    data["Среднее"] = arg3.flatten()
    return pd.DataFrame(data)


def display_tab2_monte_carlo(tab, base_financials, params):
    with tab:
        st.subheader("Симуляция Монте-Карло")
        st.write(
            "Метод Монте-Карло позволяет учесть неопределённость в доходах и расходах. "
            "Мы случайно варьируем значения вокруг среднего и получаем распределение результатов."
        )
        df_mc = monte_carlo_simulation(
            base_financials["total_income"],
            base_financials["total_expenses"],
            params.time_horizon,
            min(params.monte_carlo_simulations, 100),
            params.monte_carlo_deviation,
            params.monte_carlo_seed,
            params.monthly_income_growth,
            params.monthly_expenses_growth,
            params.monte_carlo_distribution,
            params.monte_carlo_normal_mean,
            params.monte_carlo_normal_std,
            params.monte_carlo_triang_left,
            params.monte_carlo_triang_mode,
            params.monte_carlo_triang_right
        )
        st.dataframe(df_mc.style.format("{:,.2f}"))

        months = df_mc["Месяц"].values
        incomes = df_mc[["Средний Доход"]].values
        expenses = df_mc[["Средний Расход"]].values
        profits = df_mc[["Средняя Прибыль"]].values
        num_simulations = min(params.monte_carlo_simulations, 100)

        # Генерируем факторы отклонения
        if params.monte_carlo_distribution == "Равномерное":
            inc_factors = np.random.uniform(
                1 - params.monte_carlo_deviation, 1 + params.monte_carlo_deviation,
                (num_simulations, params.time_horizon)
            )
            exp_factors = np.random.uniform(
                1 - params.monte_carlo_deviation, 1 + params.monte_carlo_deviation,
                (num_simulations, params.time_horizon)
            )
        elif params.monte_carlo_distribution == "Нормальное":
            inc_factors = np.random.normal(
                params.monte_carlo_normal_mean, params.monte_carlo_normal_std,
                (num_simulations, params.time_horizon)
            )
            exp_factors = np.random.normal(
                params.monte_carlo_normal_mean, params.monte_carlo_normal_std,
                (num_simulations, params.time_horizon)
            )
        elif params.monte_carlo_distribution == "Треугольное":
            inc_factors = np.random.triangular(
                params.monte_carlo_triang_left, params.monte_carlo_triang_mode, params.monte_carlo_triang_right,
                (num_simulations, params.time_horizon)
            )
            exp_factors = np.random.triangular(
                params.monte_carlo_triang_left, params.monte_carlo_triang_mode, params.monte_carlo_triang_right,
                (num_simulations, params.time_horizon)
            )

        base_income = base_financials["total_income"]
        base_expenses = base_financials["total_expenses"]
        inc_growth = (1 + params.monthly_income_growth) ** (months - 1)
        exp_growth = (1 + params.monthly_expenses_growth) ** (months - 1)

        simulated_incomes = base_income * inc_growth * inc_factors
        simulated_expenses = base_expenses * exp_growth * exp_factors
        simulated_profits = simulated_incomes - simulated_expenses

        df_plot_income = _extracted_from_display_tab2_monte_carlo_55(
            num_simulations, simulated_incomes, months, incomes
        )
        df_plot_expenses = _extracted_from_display_tab2_monte_carlo_55(
            num_simulations, simulated_expenses, months, expenses
        )
        df_plot_profit = _extracted_from_display_tab2_monte_carlo_55(
            num_simulations, simulated_profits, months, profits
        )

        df_long = df_plot_income.melt(id_vars=["Месяц"], var_name="Симуляция", value_name="Доход")
        ChartDisplay("Доходы (Монте-Карло)").display_line(
            df_long, "Месяц", "Доход", color="Симуляция", markers=False
        )

        df_long_exp = df_plot_expenses.melt(id_vars=["Месяц"], var_name="Симуляция", value_name="Расход")
        ChartDisplay("Расходы (Монте-Карло)").display_line(
            df_long_exp, "Месяц", "Расход", color="Симуляция", markers=False
        )

        df_long_profit = df_plot_profit.melt(id_vars=["Месяц"], var_name="Симуляция", value_name="Прибыль")
        ChartDisplay("Прибыль (Монте-Карло)").display_line(
            df_long_profit, "Месяц", "Прибыль", color="Симуляция", markers=False
        )

        st.info(
            "Чем больше симуляций, тем точнее оценка. Отклонение (deviation) задаёт случайный разброс "
            "вокруг средней динамики доходов/расходов. Каждая линия на графике — это результат одной симуляции."
        )


def display_tab3_header(tab):
    with tab:
        st.header("🔍 Точка безубыточности (BEP)")
        st.info(
            "Точка безубыточности (BEP) — это уровень дохода, при котором общие доходы равны общим расходам, "
            "и ваш бизнес не приносит ни прибыли, ни убытков.  BEP показывает, сколько вам нужно продать или заработать "
            "для покрытия всех затрат.  Понимание точки безубыточности помогает устанавливать цели продаж и оценивать "
            "ценовую политику. "
        )


def display_tab3_bep_info(tab, base_financials, params):
    with tab:
        bep_income = calculate_total_bep(base_financials, params)
        current_income = base_financials["total_income"]
        min_loan = min_loan_amount_for_bep(params, base_financials)
        if bep_income == float("inf"):
            st.write("**Бесконечность** — доход не покрывает расходы (при нынешних условиях).")
        else:
            st.write(f"**Необходимый доход для BEP:** {bep_income:,.2f} руб.")
            if current_income >= bep_income:
                st.success("Доход покрывает расходы (BEP достигнут).")
            else:
                deficit = bep_income - current_income
                st.error(f"Не хватает {deficit:,.2f} руб. до BEP.")

        if min_loan > 0:
            st.write(f"**Мин. оценка товара в займах для BEP:** {min_loan:,.2f} руб/вещь.")

        if current_income > 0 and bep_income != float("inf"):
            progress_value = min(1.0, current_income / bep_income)
            st.progress(progress_value, text=f"Выполнение плана для BEP: {progress_value * 100:.2f}%")


def display_tab3_monthly_bep(tab, base_financials, params):
    with tab:
        st.write("---")
        st.subheader("Помесячный анализ BEP")
        st.write(
            "Здесь показываем, как со временем (по месяцам) меняется уровень дохода, "
            "необходимый для покрытия расходов (учитывая рост аренды, зарплат и т.д.)."
        )
        monthly_bep_df = calculate_monthly_bep(base_financials, params)
        st.dataframe(monthly_bep_df.style.format({"Необходимый доход для BEP": "{:,.2f}"}))
        ChartDisplay("Помесячная BEP").display_line(
            monthly_bep_df, "Месяц", "Необходимый доход для BEP",
            color="Необходимый доход для BEP", markers=True
        )
        st.info("По графику видно, как растёт необходимый доход для BEP. Это нужно учитывать при планировании.")


def display_tab3_sensitivity(tab, params, disable_extended=False):
    with tab:
        st.write("---")
        st.subheader("Графики чувствительности")
        st.write(
            "Анализ чувствительности показывает, как изменение ключевых параметров (например, тариф хранения) "
            "влияет на прибыль и точку безубыточности."
        )
        st.info(
            "Например, если тариф хранения растёт, доход может увеличиться, но и отток клиентов (churn) "
            "может скорректировать реальные показатели."
        )

        def build_bep_df(p, param_key, base_val, min_val, max_val):
            from calculations import calculate_financials, calculate_total_bep
            vals = np.linspace(min_val, max_val, 50)
            profits = []
            beps = []
            orig_val = getattr(p, param_key)
            for v in vals:
                setattr(p, param_key, v)
                fin = calculate_financials(p, disable_extended)
                beps.append(calculate_total_bep(fin, p))
                profits.append(fin["profit"])
            setattr(p, param_key, orig_val)
            return pd.DataFrame({
                param_key: vals,
                "Прибыль": profits,
                "BEP": beps
            })

        param_display_map = {
            "storage_fee": "Тариф хранения (руб./м²)",
            "vip_extra_fee": "Наценка VIP (руб./м²)",
            "short_term_daily_rate": "Тариф краткосрочного (руб./день/м²)",
            "loan_interest_rate": "Ставка займов (% в день)",
        }

        reverse_map = {v: k for k, v in param_display_map.items()}
        ru_options = list(param_display_map.values())

        selected_ru_params = st.multiselect(
            "Выберите параметры для анализа чувствительности",
            ru_options,
            max_selections=3,
            help="Укажите до 3 параметров для анализа чувствительности."
        )
        selected_keys = [reverse_map[ru] for ru in selected_ru_params]

        for key in selected_keys:
            base_val = getattr(params, key)
            ru_label = param_display_map[key]

            col1, col2 = st.columns(2)
            with col1:
                min_val = st.number_input(
                    f"Мин. значение для {ru_label}",
                    value=base_val * 0.5 if base_val > 0 else 0.0,
                    help="Мин. значение для варьирования параметра",
                    format="%.2f",
                    key=f"min_{key}"
                )
            with col2:
                max_val = st.number_input(
                    f"Макс. значение для {ru_label}",
                    value=base_val * 1.5 if base_val > 0 else 1.0,
                    help="Макс. значение для варьирования параметра",
                    format="%.2f",
                    key=f"max_{key}"
                )

            df_sens = build_bep_df(params, key, base_val, min_val, max_val)

            # Обратите внимание: в .display_interactive_line():
            #   x  -> столбец DataFrame
            #   x_title -> подпись оси (ru_label)
            # В нашем df_sens столбец называется exactly `key` (напр. "storage_fee"),
            #   а user-friendly название: ru_label (напр. "Тариф хранения (руб./м²)")
            chart = ChartDisplay(f"{ru_label}: чувствительность", x_title=ru_label)
            chart.display_interactive_line(
                df_sens,
                x=key,                  # столбец df_sens
                y=["Прибыль", "BEP"],  # тоже столбцы df_sens
                markers=True
            )
            st.info(
                f"На графике видно, как изменения параметра '{ru_label}' "
                f"влияют на прибыль и точку безубыточности."
            )

        st.write("---")
        st.subheader("Многомерный анализ чувствительности")
        st.info("Здесь вы можете увидеть, как влияет одновременное изменение нескольких параметров.")

        selected_ru_params_multidim = st.multiselect(
            "Выберите параметры для многомерного анализа",
            ru_options,
            max_selections=2,
            help="Укажите до 2 параметров для анализа.",
            key="multidim_sens_select"
        )
        selected_keys_multidim = [reverse_map[ru] for ru in selected_ru_params_multidim]

        def parse_and_translate_params(row_str, pdmap):
            if not row_str:
                return row_str
            parts = row_str.split(", ")
            translated_parts = []
            for part in parts:
                if "=" in part:
                    k, v = part.split("=")
                    k = k.strip()
                    v = v.strip()
                    ru_k = pdmap.get(k, k)
                    translated_parts.append(f"{ru_k}={float(v):.2f}")
                else:
                    translated_parts.append(part)
            return ", ".join(translated_parts)

        if selected_keys_multidim:
            param_ranges = {}
            for key in selected_keys_multidim:
                base_val = getattr(params, key)
                ru_label = param_display_map[key]

                col1, col2 = st.columns(2)
                with col1:
                    min_val = st.number_input(
                        f"Мин. для {ru_label}",
                        value=base_val * 0.8 if base_val > 0 else 0.0,
                        help="Мин. значение",
                        format="%.2f",
                        key=f"multidim_min_{key}"
                    )
                with col2:
                    max_val = st.number_input(
                        f"Макс. для {ru_label}",
                        value=base_val * 1.2 if base_val > 0 else 1.0,
                        help="Макс. значение",
                        format="%.2f",
                        key=f"multidim_max_{key}"
                    )
                param_ranges[key] = np.linspace(min_val, max_val, 3)

            scenario_options = ["Базовый", "Оптимистичный", "Пессимистичный"]
            selected_scenario = st.selectbox(
                "Выберите сценарий",
                scenario_options,
                help="Выберите предустановленный сценарий",
                key="scenario_select"
            )

            if st.button("Выполнить многомерный анализ", key="multidim_analyze_btn"):
                from calculations import calculate_multidimensional_sensitivity
                original_values = {}
                temp_params = params

                # Меняем параметры под сценарий
                if selected_scenario != "Базовый":
                    for param_key in selected_keys_multidim:
                        original_values[param_key] = getattr(temp_params, param_key)
                        if selected_scenario == "Оптимистичный":
                            if original_values[param_key] > 0:
                                setattr(temp_params, param_key, original_values[param_key] * 1.2)
                        elif selected_scenario == "Пессимистичный":
                            if original_values[param_key] > 0:
                                setattr(temp_params, param_key, original_values[param_key] * 0.8)

                df_multi = calculate_multidimensional_sensitivity(
                    temp_params,
                    selected_keys_multidim,
                    param_ranges,
                    disable_extended
                )

                # Возвращаем параметры
                if selected_scenario != "Базовый":
                    for param_key, old_val in original_values.items():
                        setattr(temp_params, param_key, old_val)

                # Переводим eng -> ru для колонки "Параметры"
                reverse_eng_ru_map = {eng: ru for eng, ru in param_display_map.items()}

                df_multi["Параметры"] = df_multi["Параметры"].apply(
                    lambda x: parse_and_translate_params(x, reverse_eng_ru_map)
                )

                TableDisplay().display(df_multi.copy())

                if len(selected_keys_multidim) == 2:
                    key1 = selected_keys_multidim[0]
                    key2 = selected_keys_multidim[1]
                    # Создаём сводную таблицу pivot
                    df_multi_pivot = df_multi.pivot(
                        index=key1,
                        columns=key2,
                        values="Прибыль (руб.)"
                    )
                    if not df_multi_pivot.empty:
                        # Заменим индексы/колонки на красивые метки
                        df_multi_pivot_copy = df_multi_pivot.copy()
                        df_multi_pivot_copy.index = [
                            f"{param_display_map[key1]} = {val:.2f}"
                            for val in df_multi_pivot.index
                        ]
                        df_multi_pivot_copy.columns = [
                            f"{param_display_map[key2]} = {val:.2f}"
                            for val in df_multi_pivot.columns
                        ]
                        ChartDisplay(
                            f"Прибыль: {param_display_map[key1]} vs {param_display_map[key2]}",
                            x_title=param_display_map[key2],
                            y_title=param_display_map[key1]
                        ).display_heatmap(df_multi_pivot_copy)
                    else:
                        st.warning("Нет данных для отображения. Попробуйте изменить диапазон.")
                else:
                    ChartDisplay("Прибыль (многомерный анализ)").display_bar(
                        df_multi, x="Параметры", y="Прибыль (руб.)"
                    )

            st.info(
                "В этой таблице (и на графике) вы видите, как влияет комбинация нескольких параметров "
                "на прибыль."
            )


def display_tab4_header(tab):
    with tab:
        st.header("📋 Детализация")
        st.write("Более подробные данные о площадях, доходах, расходах и итогах.")


def display_tab4_area_metrics(tab, params):
    with tab:
        col1, col2, col3, col4 = st.columns(4)
        MetricDisplay("Стандартное (м²)").display(col1, params.storage_area)
        MetricDisplay("VIP (м²)").display(col2, params.vip_area)
        MetricDisplay("Краткосрочное (м²)").display(col3, params.short_term_area)
        MetricDisplay("Займы (м²)").display(col4, params.loan_area)


def display_tab4_storage_table(tab, params, base_financials):
    with tab:
        st.write("---")
        df_storage = pd.DataFrame({
            "Тип хранения": ["Стандартное", "VIP", "Краткосрочное", "Займы"],
            "Площадь (м²)": [
                params.storage_area,
                params.vip_area,
                params.short_term_area,
                params.loan_area
            ],
            "Доход (руб.)": [
                base_financials["storage_income"],
                base_financials["vip_income"],
                base_financials["short_term_income"],
                base_financials["loan_income_after_realization"],
            ],
        })
        TableDisplay().display(
            df_storage.style.format({
                "Площадь (м²)": "{:,.2f}",
                "Доход (руб.)": "{:,.2f}"
            })
        )


def display_tab4_profit_table(tab, params, base_financials):
    with tab:
        st.write("---")
        df_profit = pd.DataFrame({
            "Тип хранения": ["Стандартное", "VIP", "Краткосрочное", "Займы", "Реализация"],
            "Доход (руб.)": [
                base_financials["storage_income"],
                base_financials["vip_income"],
                base_financials["short_term_income"],
                base_financials["loan_income"],
                base_financials["realization_income"],
            ],
            "Доход (хранение)": [
                base_financials["storage_income"],
                base_financials["vip_income"],
                base_financials["short_term_income"],
                0,
                0,
            ],
            "Доход (займы)": [
                0,
                0,
                0,
                base_financials["loan_income_after_realization"],
                0
            ],
            "Доход (реализация)": [
                0,
                0,
                0,
                0,
                base_financials["realization_income"]
            ],
            "Ежемесячные расходы (руб.)": [
                params.storage_area * params.rental_cost_per_m2,
                params.vip_area * params.rental_cost_per_m2,
                params.short_term_area * params.rental_cost_per_m2,
                params.loan_area * params.rental_cost_per_m2,
                0,
            ],
            "Прибыль (руб.)": [
                base_financials["storage_income"] - (params.storage_area * params.rental_cost_per_m2),
                base_financials["vip_income"] - (params.vip_area * params.rental_cost_per_m2),
                base_financials["short_term_income"] - (params.short_term_area * params.rental_cost_per_m2),
                base_financials["loan_income_after_realization"] - (params.loan_area * params.rental_cost_per_m2),
                base_financials["realization_income"],
            ],
        })

        def highlight_negative(s):
            return ["background-color: #ffcccc" if v < 0 else "" for v in s]

        TableDisplay().display(
            df_profit.style
            .apply(highlight_negative, subset=["Прибыль (руб.)"])
            .format({
                col: "{:,.2f}" for col in [
                    "Доход (руб.)",
                    "Ежемесячные расходы (руб.)",
                    "Прибыль (руб.)",
                    "Доход (хранение)",
                    "Доход (займы)",
                    "Доход (реализация)",
                ]
            })
        )


def display_tab4_results(tab, base_financials, params, irr_val):
    from calculations import calculate_additional_metrics, calculate_roi, calculate_total_bep, calculate_npv

    with tab:
        st.write("---")
        pm, pr = calculate_additional_metrics(
            base_financials["total_income"],
            base_financials["total_expenses"],
            base_financials["profit"]
        )
        roi_val = calculate_roi(base_financials["total_income"], base_financials["total_expenses"])
        bep_income = calculate_total_bep(base_financials, params)

        cash_flows = [-params.one_time_expenses] + [base_financials["profit"]] * params.time_horizon
        npv_val = calculate_npv(cash_flows, 0.05)  # Ставка дисконтирования 5%

        df_results = pd.DataFrame({
            "Показатель": [
                "Общий доход", "Общие расходы", "Прибыль",
                "Маржа прибыли (%)", "Рентабельность (%)", "ROI (%)",
                "IRR (%)", "Мин. сумма займа (руб.)",
                "Единовременные расходы (руб.)", "Необходимый доход для BEP",
                "Текущий доход (руб.)", "NPV (руб.)"
            ],
            "Значение": [
                base_financials["total_income"],
                base_financials["total_expenses"],
                base_financials["profit"],
                pm,
                pr,
                roi_val,
                irr_val,
                min_loan_amount_for_bep(params, base_financials),
                params.one_time_expenses,
                bep_income,
                base_financials["total_income"],
                npv_val
            ],
        })
        TableDisplay().display(df_results)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="Скачать CSV",
                data=generate_download_link(df_results, return_raw=True),
                file_name="results.csv",
                mime="text/csv",
            )
        with col2:
            st.download_button(
                label="Скачать Excel",
                data=generate_excel_download(df_results, return_raw=True),
                file_name="results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        st.info(
            "Скачайте расширенный отчёт для детального анализа. "
            "Здесь вы видите дополнительные метрики: ROI, IRR, NPV, "
            "а также затраты на упаковку, электричество и т. д."
        )


def compare_params(tab, current_params, selected_param):
    if ("saved_params" not in st.session_state
        or selected_param not in st.session_state.saved_params):
        st.error("Нет сохранённых параметров для сравнения.")
        return

    saved_params = st.session_state.saved_params[selected_param]

    attributes_to_compare = [
        "total_area", "rental_cost_per_m2", "useful_area_ratio",
        "storage_area_manual", "loan_area_manual", "vip_area_manual",
        "short_term_area_manual", "storage_fee", "shelves_per_m2",
        "short_term_daily_rate", "vip_extra_fee", "item_evaluation",
        "item_realization_markup", "average_item_value", "loan_interest_rate",
        "loan_term_days", "realization_share_storage", "realization_share_loan",
        "realization_share_vip", "realization_share_short_term",
        "storage_fill_rate", "loan_fill_rate", "vip_fill_rate", "short_term_fill_rate",
        "storage_items_density", "loan_items_density", "vip_items_density",
        "short_term_items_density", "storage_monthly_churn", "loan_monthly_churn",
        "vip_monthly_churn", "short_term_monthly_churn", "salary_expense",
        "miscellaneous_expenses", "depreciation_expense", "marketing_expenses",
        "insurance_expenses", "taxes", "utilities_expenses", "maintenance_expenses",
        "one_time_setup_cost", "one_time_equipment_cost", "one_time_other_costs",
        "one_time_legal_cost", "one_time_logistics_cost",
        "electricity_cost_per_m2", "packaging_cost_per_m2",
        "monthly_inflation_rate", "monthly_rent_growth",
        "monthly_salary_growth", "monthly_other_expenses_growth", "time_horizon",
        "default_probability", "liquidity_factor", "safety_factor",
        "loan_grace_period", "monthly_income_growth", "monthly_expenses_growth",
        "forecast_method", "monte_carlo_simulations", "monte_carlo_deviation",
        "monte_carlo_seed", "enable_ml_settings", "poly_degree",
        "n_estimators", "features",
        "monte_carlo_distribution", "monte_carlo_normal_mean",
        "monte_carlo_normal_std", "monte_carlo_triang_left",
        "monte_carlo_triang_mode", "monte_carlo_triang_right"
    ]

    param_display_map = {
        "total_area": "Общая площадь (м²)",
        "rental_cost_per_m2": "Стоимость аренды (руб./м²/мес.)",
        "useful_area_ratio": "Доля полезной площади (%)",
        "storage_area_manual": "Простое (м²)",
        "loan_area_manual": "Займы (м²)",
        "vip_area_manual": "VIP (м²)",
        "short_term_area_manual": "Краткосрочное (м²)",
        "storage_fee": "Тариф простого (руб./м²/мес.)",
        "shelves_per_m2": "Полок на 1 м²",
        "short_term_daily_rate": "Тариф краткосрочного (руб./день/м²)",
        "vip_extra_fee": "Наценка VIP (руб./м²/мес.)",
        "item_evaluation": "Оценка вещи (%)",
        "item_realization_markup": "Наценка реализации (%)",
        "average_item_value": "Средняя оценка вещи (руб.)",
        "loan_interest_rate": "Ставка займов (%/день)",
        "loan_term_days": "Средний срок займа (дней)",
        "realization_share_storage": "Реализация простое (%)",
        "realization_share_loan": "Реализация займы (%)",
        "realization_share_vip": "Реализация VIP (%)",
        "realization_share_short_term": "Реализация краткосрочное (%)",
        "storage_fill_rate": "Заполнение простое (%)",
        "loan_fill_rate": "Заполнение займы (%)",
        "vip_fill_rate": "Заполнение VIP (%)",
        "short_term_fill_rate": "Заполнение краткосрочное (%)",
        "storage_items_density": "Плотность простое (вещей/м²)",
        "loan_items_density": "Плотность займы (вещей/м²)",
        "vip_items_density": "Плотность VIP (вещей/м²)",
        "short_term_items_density": "Плотность краткосрочное (вещей/м²)",
        "storage_monthly_churn": "Отток простое (%)",
        "loan_monthly_churn": "Отток займы (%)",
        "vip_monthly_churn": "Отток VIP (%)",
        "short_term_monthly_churn": "Отток краткосрочное (%)",
        "salary_expense": "Зарплата (руб./мес.)",
        "miscellaneous_expenses": "Прочие (руб./мес.)",
        "depreciation_expense": "Амортизация (руб./мес.)",
        "marketing_expenses": "Маркетинг (руб./мес.)",
        "insurance_expenses": "Страхование (руб./мес.)",
        "taxes": "Налоги (руб./мес.)",
        "utilities_expenses": "Коммуналка (руб./мес.)",
        "maintenance_expenses": "Обслуживание (руб./мес.)",
        "one_time_setup_cost": "Настройка (руб.)",
        "one_time_equipment_cost": "Оборудование (руб.)",
        "one_time_other_costs": "Другие (руб.)",
        "one_time_legal_cost": "Юридические (руб.)",
        "one_time_logistics_cost": "Логистика (руб.)",
        "electricity_cost_per_m2": "Электричество (руб./м²)",
        "packaging_cost_per_m2": "Упаковка (руб./м²)",
        "monthly_inflation_rate": "Инфляция (%/мес.)",
        "monthly_rent_growth": "Рост аренды (%/мес.)",
        "monthly_salary_growth": "Рост зарплаты (%/мес.)",
        "monthly_other_expenses_growth": "Рост прочих расходов (%/мес.)",
        "time_horizon": "Горизонт прогноза (мес.)",
        "default_probability": "Вероятность невозврата (%)",
        "liquidity_factor": "Коэффициент ликвидности",
        "safety_factor": "Коэффициент запаса",
        "loan_grace_period": "Льготный период (мес.)",
        "monthly_income_growth": "Рост доходов (%/мес.)",
        "monthly_expenses_growth": "Рост расходов (%/мес.)",
        "forecast_method": "Метод прогнозирования",
        "monte_carlo_simulations": "Симуляций Монте-Карло",
        "monte_carlo_deviation": "Отклонения (0.1 = ±10%)",
        "monte_carlo_seed": "Seed",
        "enable_ml_settings": "Включить расширенный ML-прогноз",
        "poly_degree": "Степень полинома",
        "n_estimators": "Количество деревьев",
        "features": "Признаки",
        "monte_carlo_distribution": "Распределение",
        "monte_carlo_normal_mean": "Среднее (Норм. распр.)",
        "monte_carlo_normal_std": "Ст. отклонение (Норм. распр.)",
        "monte_carlo_triang_left": "Мин. значение (Треуг. распр.)",
        "monte_carlo_triang_mode": "Мода (Треуг. распр.)",
        "monte_carlo_triang_right": "Макс. значение (Треуг. распр.)"
    }

    with tab:
        st.subheader("Сравнение сохранённых параметров")
        for attr in attributes_to_compare:
            current_value = getattr(current_params, attr, None)
            saved_value = saved_params.get(attr)
            if current_value != saved_value:
                ru_label = param_display_map.get(attr, attr)
                if isinstance(current_value, (int, float)) and isinstance(saved_value, (int, float)):
                    import pandas as pd
                    df_compare = pd.DataFrame({
                        "Значение": [float(saved_value), float(current_value)],
                        "Состояние": ["Сохранённое", "Текущее"]
                    })
                    ChartDisplay(f"Параметр: {ru_label}").display_bar(
                        df_compare, "Состояние", "Значение"
                    )
                    st.write(f"**Сохранённое:** {saved_value:,.2f} | **Текущее:** {current_value:,.2f}")
                else:
                    st.write(f"**{ru_label}:** Сохранённое: {saved_value} | Текущее: {current_value}")