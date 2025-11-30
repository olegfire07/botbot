#!/usr/bin/env python3
from __future__ import annotations

"""
Streamlit UI для распределения лотов аукциона.
Запуск:
    streamlit run modern_bot/scripts/allocate_streamlit.py --server.port 8501
После старта открыть http://localhost:8501
"""

import io
import sys
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# Добавляем корень репозитория в sys.path, чтобы импортировать modern_bot как пакет.
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from modern_bot.scripts.allocate_auction import BASE_DIR, run_allocation

DEFAULT_SALES = BASE_DIR / "Табличная_часть_Продажи_распродажа_0109_311225.xlsx"
DEFAULT_STOCK = BASE_DIR / "остатки на 301125.xlsx"
DEFAULT_AUCTION = BASE_DIR / "Реестр аукциона 15.11 Санкт-Петербург.xlsx"


def run_calc(
    uploaded_file: Optional[st.runtime.uploaded_file_manager.UploadedFile],
    cfg_overrides: dict,
):
    """Выполняет расчет распределения. Возвращает (alloc_df, summary_df, excel_bytes)."""
    if uploaded_file is not None:
        suffix = Path(uploaded_file.name).suffix or ".xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getbuffer())
            auction_path = Path(tmp.name)
    else:
        auction_path = DEFAULT_AUCTION

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_out:
        out_path = Path(tmp_out.name)

    _, alloc_df, summary_df = run_allocation(
        DEFAULT_SALES,
        DEFAULT_STOCK,
        auction_path,
        out_path,
        None,
        True,
        cfg_overrides,
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        alloc_df.to_excel(writer, sheet_name="Распределение", index=False)
        summary_df.to_excel(writer, sheet_name="Итог по подразделениям", index=False)
    buffer.seek(0)
    return alloc_df, summary_df, buffer


def main():
    st.set_page_config(page_title="Распределение аукциона", layout="wide")
    st.title("Распределение лотов аукциона")
    st.markdown(
        """
        **🚀 Стратегия:** Максимизация скорости продаж + контроль ассортимента  
        Товары идут в подразделения с высокой скоростью продаж, но алгоритм следит за балансом категорий.
        """
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded = st.file_uploader("📄 Реестр аукциона (.xlsx)", type=["xlsx"])
    with col2:
        st.caption(f"📊 Продажи: `{DEFAULT_SALES.name}`")
        st.caption(f"📦 Остатки: `{DEFAULT_STOCK.name}`")
        st.caption("ℹ️ Если файл не загрузить, используется реестр по умолчанию.")

    with st.expander("⚙️ Основные параметры стратегии", expanded=True):
        st.markdown("#### 🏃 Приоритет скорости продаж")
        velocity_weight = st.slider(
            "Вес скорости продаж (чем выше, тем важнее скорость)",
            0.0, 20.0, 10.0, 0.5,
            help="Основной параметр: чем выше, тем больше товаров идет в быстропродающие подразделения"
        )
        
        st.markdown("#### 🎨 Контроль ассортимента")
        category_congestion_penalty = st.slider(
            "Штраф за скопление категории (за каждую штуку)",
            0.0, 50.0, 15.0, 1.0,
            help="Чем выше, тем сильнее избегаем скопления одинаковых товаров"
        )
        empty_category_bonus = st.slider(
            "Бонус за новую категорию",
            0.0, 200.0, 80.0, 10.0,
            help="Бонус за расширение ассортимента (если категории нет в подразделении)"
        )
        category_threshold = st.slider(
            "Порог перегрузки категории (штук)",
            3, 20, 10, 1,
            help="После этого количества штраф за категорию усиливается"
        )
        category_overload_multiplier = st.slider(
            "Множитель штрафа при перегрузе",
            1.0, 5.0, 2.5, 0.5,
            help="Во сколько раз усилить штраф после превышения порога"
        )
        
        st.markdown("#### ⚖️ Баланс и прочее")
        coverage_weight = st.slider(
            "Вес покрытия/дефицита",
            0.0, 2.0, 0.2, 0.1,
            help="Учет текущих остатков (небольшой вес)"
        )
        fairness_penalty = st.slider(
            "Штраф за перегрузку подразделения",
            0.0, 2.0, 0.05, 0.05,
            help="Минимальный штраф - не стремимся к равномерности"
        )
        margin_weight = st.slider(
            "Вес маржинальности",
            0.0, 1.0, 0.15, 0.05,
            help="Учет потенциальной прибыли от товара"
        )

    with st.expander("🔧 Дополнительные настройки"):
        target_cov = st.slider("Целевое покрытие (недель)", 1.0, 12.0, 4.0, 0.5)
        prob_days = st.slider("Горизонт прогноза продаж (дней)", 7, 90, 30, 1)
        gashek_dampener = st.slider(
            "Демпфер для Гашека (коэфф. скорости)",
            0.1, 1.0, 0.3, 0.05,
            help="Занижение скорости для подразделения Гашека из-за перекупов"
        )

    cfg = {
        "target_coverage_weeks": target_cov,
        "coverage_weight": coverage_weight,
        "velocity_weight": velocity_weight,
        "fairness_penalty": fairness_penalty,
        "margin_weight": margin_weight,
        "category_congestion_penalty": category_congestion_penalty,
        "empty_category_bonus": empty_category_bonus,
        "category_threshold": int(category_threshold),
        "category_overload_multiplier": category_overload_multiplier,
        "gashek_dampener": gashek_dampener,
        "prob_target_days": int(prob_days),
        "max_department_percentage": None,  # убрали жесткий лимит
    }

    if st.button("Рассчитать распределение", type="primary"):
        with st.spinner("Считаем..."):
            alloc_df, summary_df, buffer = run_calc(uploaded, cfg)

        st.success("Готово! Ниже предпросмотр и скачивание.")
        st.download_button(
            "Скачать XLSX",
            data=buffer.getvalue(),
            file_name="распределение_аукцион.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.subheader("Итог по подразделениям (топ 50)")
        st.dataframe(summary_df.head(50), use_container_width=True)

        st.subheader("Распределение (первые 100 строк)")
        st.dataframe(
            alloc_df[
                [
                    "Артикул",
                    "Подразделение",
                    "Регион",
                    "Отправить, шт",
                    "Скорость, шт/нед",
                    "Покрытие, недель",
                    f"Вероятность продажи ≤{cfg['prob_target_days']}д, %",
                    "Скор",
                    "Комментарий",
                ]
            ].head(100),
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
