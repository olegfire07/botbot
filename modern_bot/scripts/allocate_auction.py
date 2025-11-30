#!/usr/bin/env python3
from __future__ import annotations

"""
Распределяет лоты из реестра аукциона по подразделениям с учетом продаж и текущих остатков.

Логика:
1. Скорость продаж (шт./неделя) берется из файла таблицы продаж, где есть колонка подразделения.
2. Покрытие = остаток / скорость. Чем меньше покрытие, тем привлекательнее подразделение для отгрузки.
3. Для каждого артикула из реестра аукциона лоты разносятся по подразделениям с минимальным покрытием,
   при равенстве — по большей скорости продаж. При каждой выдаче покрытие пересчитывается.
4. Если по артикулу нет ни остатков, ни продаж — отправляем в подразделения с максимальной общей скоростью продаж.
"""

import argparse
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

# Настройка логирования в файл
BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

def setup_logging():
    """Настраивает детальное логирование в файл и консоль."""
    # Создаем уникальное имя файла с timestamp
    log_file = LOG_DIR / f"allocation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # Создаем форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Очищаем старые handlers чтобы избежать дублирования
    logger.handlers.clear()
    
    # Настраиваем logger
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"📝 Логирование настроено. Файл: {log_file}")
    return log_file


def normalize_sku(value: object, pad_to: int = 11) -> Optional[str]:
    """Возвращает артикул как строку с сохранением ведущих нулей."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None

    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return digits.zfill(pad_to)
    return text


def normalize_name(value: object) -> str:
    """Нормализует названия подразделений/регионов: lowercase + убирает лишние пробелы."""
    if pd.isna(value):
        return ""
    text = str(value).strip().lower()
    # Заменяем множественные пробелы на один
    text = re.sub(r'\s+', ' ', text)
    return text


def load_sales_table(path: Path) -> pd.DataFrame:
    """
    Загружает файл "Табличная_часть_Продажи_распродажа_0109_311225.xlsx".
    Нужные колонки по позициям (0-базовая нумерация):
        0: Регион для экономистов
        4: Подразделение
        7: Дата
        11: Залоговый билет; Скупочная квитанция (артикул)
        12: Регистратор.Номер (используется для дедупликации)
        18: Количество
    """
    df = pd.read_excel(
        path,
        header=None,
        usecols=[0, 4, 7, 8, 11, 12, 18, 19, 20],
        skiprows=10,  # пропускаем служебные строки и заголовки
    )
    df.columns = [
        "region",
        "department",
        "sale_date",
        "category",
        "sku",
        "doc_number",
        "qty",
        "sale_amount",
        "loan_amount",
    ]

    df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce", dayfirst=True)
    df["sku"] = df["sku"].apply(normalize_sku)
    df = df.dropna(subset=["sale_date", "sku"])

    df["department"] = df["department"].apply(normalize_name)
    df["region"] = df["region"].apply(normalize_name)
    df["category"] = df["category"].astype(str).str.strip().replace({"nan": None, "None": None})
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(1).astype(float)
    df["sale_amount"] = pd.to_numeric(df["sale_amount"], errors="coerce").fillna(0.0)
    df["loan_amount"] = pd.to_numeric(df["loan_amount"], errors="coerce").fillna(0.0)

    # В исходнике каждая продажа часто продублирована (строка с телефоном и без).
    df = df.drop_duplicates(subset=["department", "sku", "sale_date", "doc_number"])
    return df


def compute_velocity(sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Возвращает (скорость по SKU+подразделение, скорость по подразделению, длительность окна в неделях)."""
    if sales.empty:
        empty_sku = pd.DataFrame(columns=["sku", "department", "region", "weekly_velocity"])
        empty_dep = pd.DataFrame(columns=["department", "region", "weekly_velocity"])
        return empty_sku, empty_dep, 1

    date_span_days = (sales["sale_date"].max() - sales["sale_date"].min()).days
    
    # Валидация минимального временного окна
    MIN_WINDOW_DAYS = 7
    if date_span_days < MIN_WINDOW_DAYS:
        logger.warning(
            f"⚠️ Данные продаж охватывают только {date_span_days} дней (меньше {MIN_WINDOW_DAYS}). "
            "Скорость продаж может быть неточной. Рекомендуется использовать данные минимум за неделю."
        )
    
    weeks_span = max(1, math.ceil(date_span_days / 7))

    sku_velocity = (
        sales.groupby(["sku", "department", "region"])["qty"].sum() / weeks_span
    ).reset_index()
    sku_velocity = sku_velocity.rename(columns={"qty": "weekly_velocity"})

    dept_velocity = (
        sales.groupby(["department", "region"])["qty"].sum() / weeks_span
    ).reset_index()
    dept_velocity = dept_velocity.rename(columns={"qty": "weekly_velocity"})

    return sku_velocity, dept_velocity, weeks_span


def load_stock(path: Path) -> pd.DataFrame:
    """
    Загружает файл остатков.
    Нужные колонки (0-базовая нумерация):
        0: Регион
        2: Подразделение
        5: Залоговый билет (артикул)
        9: Количество, шт
    """
    df = pd.read_excel(path, header=None, usecols=[0, 2, 5, 7, 9], skiprows=10)
    df.columns = ["region", "department", "sku", "category", "stock_qty"]

    df["sku"] = df["sku"].apply(normalize_sku)
    df = df.dropna(subset=["sku"])

    df["department"] = df["department"].apply(normalize_name)
    df["region"] = df["region"].apply(normalize_name)
    df["category"] = df["category"].astype(str).str.strip().replace({"nan": None, "None": None})
    df["stock_qty"] = pd.to_numeric(df["stock_qty"], errors="coerce").fillna(0)

    # Суммируем, если артикул повторяется в одном подразделении.
    df = df.groupby(["sku", "department", "region", "category"], as_index=False)["stock_qty"].sum()
    return df


def load_auction(path: Path, sku_column: Optional[str] = None) -> tuple[Dict[str, int], Dict[str, Dict[str, object]]]:
    """Возвращает (счетчик SKU, метаданные по SKU)."""
    df = pd.read_excel(path)
    candidates = [
        sku_column,
        "3.Залоговый билет (заполняется сотрудником отдела НЮЗ)",
        "Артикул",
    ]
    sku_col = next((c for c in candidates if c and c in df.columns), None)
    if sku_col is None:
        raise ValueError("Не нашел колонку с артикулом в реестре аукциона")

    df["sku"] = df[sku_col].apply(normalize_sku)
    df["category"] = df.get("4.Вид предмета (заполняется сотрудником отдела НЮЗ)", pd.Series(dtype=object))
    df["description"] = df.get("5.Описание (заполняется сотрудником отдела НЮЗ)", pd.Series(dtype=object))
    df["loan"] = pd.to_numeric(df.get("6.Ссуда (заполняется сотрудником отдела НЮЗ)", pd.Series(dtype=object)), errors="coerce")
    df["retail_price"] = pd.to_numeric(df.get("7.Розничная цена (заполняется сотрудником отдела НЮЗ)", pd.Series(dtype=object)), errors="coerce")
    df["recommended_price"] = pd.to_numeric(df.get("11.Рекомендуемая розничная цена (запоняется старшим товароведом-приемщиком)", pd.Series(dtype=object)), errors="coerce")

    df["category"] = df["category"].astype(str).str.strip()
    df["description"] = df["description"].astype(str).str.strip()

    counts = df["sku"].dropna().value_counts().to_dict()
    if not counts:
        raise ValueError("В реестре аукциона нет артикулов для распределения")

    meta: Dict[str, Dict[str, object]] = {}
    for _, row in df.dropna(subset=["sku"]).iterrows():
        sku = row["sku"]
        if sku not in meta:
            meta[sku] = {
                "category": row.get("category"),
                "description": row.get("description"),  # НОВОЕ
                "loan": row.get("loan"),
                "retail_price": row.get("retail_price"),
                "recommended_price": row.get("recommended_price"),
            }
    return counts, meta


def build_coverage(stock: pd.DataFrame, velocity: pd.DataFrame) -> pd.DataFrame:
    """
    Создает таблицу покрытия по каждому (sku, подразделение):
    - stock_qty: текущий остаток
    - weekly_velocity: продажи в неделю
    - coverage_weeks: недель покрытия на текущем стоке
    """
    coverage = pd.merge(
        stock,
        velocity,
        on=["sku", "department"],
        how="outer",
        suffixes=("_stock", "_velocity"),
    )

    coverage["region"] = coverage["region_stock"].fillna(coverage["region_velocity"])
    coverage["category"] = coverage["category"]
    coverage["stock_qty"] = coverage["stock_qty"].fillna(0)
    coverage["weekly_velocity"] = coverage["weekly_velocity"].fillna(0)

    coverage["coverage_weeks"] = coverage.apply(
        lambda row: math.inf
        if row["weekly_velocity"] <= 0
        else row["stock_qty"] / row["weekly_velocity"],
        axis=1,
    )
    coverage["stock_qty"] = coverage["stock_qty"].astype(float)
    coverage["weekly_velocity"] = coverage["weekly_velocity"].astype(float)
    coverage["coverage_weeks"] = coverage["coverage_weeks"].astype(float)

    return coverage[["sku", "department", "region", "category", "stock_qty", "weekly_velocity", "coverage_weeks"]]


@dataclass
class AllocationConfig:
    """Настройки алгоритма распределения."""

    target_coverage_weeks: float = 4.0  # целевое покрытие по запасам
    coverage_weight: float = 0.2  # небольшой вес дефицита (учитываем, но не приоритет)
    velocity_weight: float = 10.0  # 🚀 ГЛАВНЫЙ ПРИОРИТЕТ: максимизируем скорость продаж!
    fairness_penalty: float = 0.05  # ⚖️ Минимальный штраф (не стремимся к равномерности)
    max_department_percentage: float = None  # ❌ УБРАЛИ жесткий лимит на подразделение
    max_add_per_department: Optional[int] = None  # нет лимита выдачи по одному SKU
    prob_target_days: int = 30  # горизонт прогноза для вероятности продажи
    velocity_prior: float = 0.2  # сглаживание скорости для редких SKU
    alpha_cat_velocity: float = 0.8  # вес категории
    alpha_dept_velocity: float = 0.2  # вес общей скорости подразделения
    category_diversity_bonus: float = 1.0  # бонус за новую категорию
    
    # 🆕 УСИЛЕННЫЙ КОНТРОЛЬ АССОРТИМЕНТА (избегаем скопления одинаковых товаров)
    category_congestion_penalty: float = 15.0  # 🔥 СИЛЬНЫЙ штраф за скопление одной категории
    empty_category_bonus: float = 80.0  # 🌟 ОГРОМНЫЙ бонус за расширение ассортимента
    category_threshold: int = 10  # порог: если категории больше N штук, усиливаем штраф
    category_overload_multiplier: float = 2.5  # множитель штрафа после превышения порога
    gashek_dampener: float = 0.3  # Коэффициент для Гашека (умножаем скорость на 0.3)
    
    min_categories_per_department: int = 5  # целевое количество категорий
    margin_weight: float = 0.15  # вес ожидаемой маржи (чуть усилен)
    min_candidates: int = 5  # минимум кандидатов для распределения


def predict_sell_probability(weekly_velocity: float, target_days: int, velocity_prior: float) -> float:
    """
    Оценивает вероятность продажи за target_days при экспоненциальном спросе.
    weekly_velocity — скорость (шт./неделя). Добавляем prior, чтобы не было нулей.
    """
    lam = max(weekly_velocity + velocity_prior, 0.0) / 7  # интенсивность в день
    if lam <= 0:
        return 0.0
    prob = 1 - math.exp(-lam * target_days)
    return max(0.0, min(1.0, prob))


def allocate_sku(
    sku: str,
    qty: int,
    coverage: pd.DataFrame,
    dept_velocity: pd.DataFrame,
    cat_velocity: Dict[tuple, float],
    dept_velocity_map: Dict[str, float],
    auction_meta: Dict[str, Dict[str, object]],
    allocations: List[Dict],  # НОВОЕ: передаем список для заполнения
    dept_cat_qty_map: Dict[str, Dict[str, int]], # НОВОЕ: карта количеств
    cfg: AllocationConfig,
    stock: pd.DataFrame = None,  # НОВОЕ: для учета общих остатков
    global_dept_load: Dict[str, int] = None, # НОВОЕ
    max_per_dept_global: int = None # НОВОЕ
) -> List[Dict[str, object]]:
    """
    Распределяет qty штук артикула sku по подразделениям.
    Возвращает список строк для итоговой таблицы.
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"🎯 Начинаем распределение SKU: {sku}, количество: {qty} шт")
    
    pool = coverage[coverage["sku"] == sku].copy()

    if pool.empty:
        logger.debug(f"  ⚠️ Нет истории по SKU {sku}, используем категории + общие остатки")
        # Нет истории по SKU — используем комплексный подход
        
        # Получаем категорию товара
        cat = auction_meta.get(sku, {}).get("category")
        
        # Начинаем с подразделений
        pool = dept_velocity.copy()
        pool["sku"] = sku
        pool["stock_qty"] = 0
        pool["category"] = cat
        
        # Добавляем общий остаток подразделения (если доступен)
        if stock is not None and not stock.empty:
            dept_total_stock = stock.groupby("department")["stock_qty"].sum().reset_index()
            dept_total_stock.columns = ["department", "total_stock"]
            pool = pool.merge(dept_total_stock, on="department", how="left")
            pool["total_stock"] = pool["total_stock"].fillna(0)
            
            # Рассчитываем общее покрытие подразделения
            pool["dept_coverage"] = pool.apply(
                lambda row: math.inf if row["weekly_velocity"] <= 0
                else row["total_stock"] / row["weekly_velocity"],
                axis=1
            )
            logger.debug(f"  📊 Добавлены общие остатки подразделений")
        else:
            pool["total_stock"] = 0
            pool["dept_coverage"] = math.inf
        
        pool["coverage_weeks"] = pool.apply(
            lambda row: math.inf if row["weekly_velocity"] <= 0 else 0,
            axis=1,
        )

    # Если кандидатов мало, добавим топ подразделений по скорости.
    if len(pool) < cfg.min_candidates:
        logger.debug(f"  📊 Кандидатов мало ({len(pool)}), добавляем топ подразделений")
        existing_depts = set(pool["department"].tolist())
        extra = dept_velocity[~dept_velocity["department"].isin(existing_depts)].copy()
        if not extra.empty:
            extra = extra.nlargest(cfg.min_candidates, "weekly_velocity")
            extra["sku"] = sku
            extra["stock_qty"] = 0
            extra["coverage_weeks"] = extra.apply(
                lambda row: math.inf if row["weekly_velocity"] <= 0 else 0,
                axis=1,
            )
            extra["category"] = auction_meta.get(sku, {}).get("category")
            pool = pd.concat([pool, extra], ignore_index=True)

    pool["stock_qty"] = pool["stock_qty"].astype(float)
    pool["weekly_velocity"] = pool["weekly_velocity"].astype(float)
    pool["coverage_weeks"] = pool["coverage_weeks"].astype(float)
    pool["category"] = pool.get("category", pd.Series(dtype=object))

    if pool.empty:
        logger.warning(f"  ❌ Совсем нет данных для SKU {sku} — не можем распределить")
        return []

    # Используем переданный глобальный счетчик или создаем локальный (если не передан)
    if global_dept_load is None:
        global_dept_load = {}

    remaining = int(qty) # ВОССТАНОВЛЕНО
    
    logger.info(f"  📦 Доступно подразделений-кандидатов: {len(pool)}")
    logger.debug(f"  Кандидаты: {pool[['department', 'stock_qty', 'weekly_velocity', 'coverage_weeks']].to_string()}")

    iteration = 0
    for remaining_to_allocate in range(qty, 0, -1):
        if pool.empty:
            logger.warning(f"  ⚠️ Закончились кандидаты на отправку, осталось {remaining_to_allocate} шт.")
            break

        def score_row(row):
            dept = row["department"]
            
            cat = row.get("category")
            if pd.isna(cat):
                cat = str(auction_meta.get(sku, {}).get("category", ""))
            cat = str(cat).strip()

            base_vel = row["weekly_velocity"] if pd.notna(row["weekly_velocity"]) else 0.0
            
            # 📉 ДЕМПФЕР ДЛЯ ГАШЕКА (№544)
            # Если это Гашека, мы искусственно занижаем скорость, т.к. там перекупы
            if "544" in dept or "гашека" in dept.lower():
                base_vel *= cfg.gashek_dampener
                # logger.debug(f"    📉 {dept}: скорость занижена (Гашека) до {base_vel:.2f}")

            blend_vel = base_vel
            
            # Для товаров с категорией - усиленный учет категорийной скорости
            if cat:
                cat_vel = cat_velocity.get((cat, dept), 0)
                # Тоже демпфируем категорийную скорость для Гашека
                if "544" in dept or "гашека" in dept.lower():
                    cat_vel *= cfg.gashek_dampener
                
                blend_vel += cfg.alpha_cat_velocity * cat_vel
            
            blend_vel += cfg.alpha_dept_velocity * dept_velocity_map.get(dept, 0)

            # Используем только положительный gap (только дефицит учитывается)
            coverage_val = row["coverage_weeks"]
            if math.isinf(coverage_val):
                coverage_val = 1000.0
            coverage_gap = max(0, cfg.target_coverage_weeks - coverage_val)
            
            # Fairness penalty (штраф за перегрузку)
            fairness = global_dept_load.get(dept, 0) ** 2.0

            meta = auction_meta.get(sku, {})
            loan = meta.get("loan") or 0
            price = meta.get("recommended_price") or meta.get("retail_price") or 0
            margin = max(price - loan, 0) if pd.notna(loan) and pd.notna(price) else 0

            # 🆕 АССОРТИМЕНТНАЯ ЛОГИКА С ПРОГРЕССИВНЫМ ШТРАФОМ
            assortment_score = 0.0
            if cat:
                # Сколько уже есть таких предметов (остатки + то что выдали сейчас)
                current_qty = dept_cat_qty_map.get(dept, {}).get(cat, 0)
                
                if current_qty == 0:
                    # 🔥 ОГРОМНЫЙ БОНУС ЗА ПУСТУЮ КАТЕГОРИЮ (расширение ассортимента)
                    assortment_score += cfg.empty_category_bonus
                    # logger.debug(f"    ✨ {dept}: нет категории '{cat}' -> бонус +{cfg.empty_category_bonus}")
                else:
                    # ⚠️ ПРОГРЕССИВНЫЙ ШТРАФ за скученность
                    # Базовый штраф
                    penalty = current_qty * cfg.category_congestion_penalty
                    
                    # 🔥 УСИЛЕННЫЙ штраф если превышен порог (например, >10 телефонов)
                    if current_qty >= cfg.category_threshold:
                        overload = current_qty - cfg.category_threshold
                        penalty += overload * cfg.category_congestion_penalty * cfg.category_overload_multiplier
                        # logger.debug(f"    🚨 {dept}: ПЕРЕГРУЗ '{cat}' ({current_qty} шт) -> усиленный штраф -{penalty:.1f}")
                    
                    assortment_score -= penalty
                    # logger.debug(f"    ⚠️ {dept}: уже есть {current_qty} шт '{cat}' -> штраф -{penalty:.1f}")

            score = (
                cfg.coverage_weight * coverage_gap
                + cfg.velocity_weight * blend_vel
                + cfg.margin_weight * margin
                + assortment_score # Добавляем ассортиментный вклад
                - cfg.fairness_penalty * fairness
            )
            # Защита от NaN
            if not math.isfinite(score):
                logger.warning(f"    ⚠️ NaN score для {dept}: coverage_gap={coverage_gap}, blend_vel={blend_vel}, margin={margin}")
                score = blend_vel  # fallback на velocity
            
            return score

        # Применяем scoring ко всем кандидатам
        pool["score"] = pool.apply(score_row, axis=1)
        
        # Фильтруем заблокированные подразделения (score = -inf)
        pool_valid = pool[pool["score"] != float('-inf')].copy()
        
        if pool_valid.empty:
            logger.warning(f"  ⚠️ Все подразделения заблокированы (достигли лимита), осталось {remaining_to_allocate} шт.")
            break

        # Сортируем по score и выбираем победителя
        pool_valid = pool_valid.sort_values("score", ascending=False)
        
        logger.debug(f"  🏆 Топ-3 кандидатов по скору:")
        for i, (_, row) in enumerate(pool_valid.head(3).iterrows(), 1):
            logger.debug(
                f"    #{i}: {row['department']} - score={row['score']:.2f}, velocity={row['weekly_velocity']:.2f}, coverage={row['coverage_weeks']:.1f}н"
            )

        winner = pool_valid.iloc[0].copy()
        dept = winner["department"]
        cat = winner.get("category") or auction_meta.get(sku, {}).get("category")
        
        # Обновляем глобальный счетчик
        global_dept_load[dept] = global_dept_load.get(dept, 0) + 1
        
        meta = auction_meta.get(sku, {})
        loan = meta.get("loan") or 0
        price = meta.get("recommended_price") or meta.get("retail_price") or 0
        margin = max(price - loan, 0)

        cat = winner["category"] if pd.notna(winner["category"]) else auction_meta.get(sku, {}).get("category")
        cat = str(cat).strip()
        if cat and cat.lower() not in ("nan", "none", ""):
            # Обновляем количество в карте категорий
            if dept not in dept_cat_qty_map:
                dept_cat_qty_map[dept] = {}
            dept_cat_qty_map[dept][cat] = dept_cat_qty_map[dept].get(cat, 0) + 1

        base_vel = winner["weekly_velocity"]
        blend_vel = base_vel
        if cat:
            blend_vel += cfg.alpha_cat_velocity * cat_velocity.get((cat, dept), 0)
        blend_vel += cfg.alpha_dept_velocity * dept_velocity_map.get(dept, 0)

        prob_sell = predict_sell_probability(blend_vel, cfg.prob_target_days, cfg.velocity_prior)
        
        # Получаем дополнительную информацию из метаданных
        meta_info = auction_meta.get(sku, {})
        item_name = meta_info.get("category", "")  # Вид предмета = категория
        description = meta_info.get("description", "")  # Описание
        
        reason = (
            f"скор={winner['score']:.2f}, velocity={blend_vel:.2f}/нед, покрытие={winner['coverage_weeks']:.1f}н, "
            f"p≤{cfg.prob_target_days}д≈{prob_sell*100:.1f}%, маржа≈{margin:.0f}"
        )
        
        logger.info(
            f"  ✅ Штука {qty - remaining_to_allocate + 1}/{qty} → {dept}: {reason}"
        )

        allocations.append(
            {
                "sku": sku,
                "department": dept,
                "region": winner.get("region"),  # ИСПРАВЛЕНО: используем из row
                "category": cat,
                "item_name": item_name,  # НОВОЕ: Наименование товара
                "description": description,  # НОВОЕ: Описание
                "send_qty": 1,
                "stock_qty": winner.get("stock_qty", 0),
                "weekly_velocity": blend_vel,
                "coverage_weeks": winner.get("coverage_weeks", math.inf),
                "prob_sell": prob_sell,
                "score": winner.get("score", 0),
                "reason": reason,
            }
        )

        # Обновляем покрытие выбранного подразделения перед следующей итерацией.
        idx_update = pool.index[pool["department"] == dept][0]
        pool.at[idx_update, "stock_qty"] = winner["stock_qty"] + 1
        pool.at[idx_update, "coverage_weeks"] = (
            math.inf
            if winner["weekly_velocity"] <= 0
            else (winner["stock_qty"] + 1) / winner["weekly_velocity"]
        )
        remaining -= 1

    return allocations


def run_allocation(
    sales_path: Path,
    stock_path: Path,
    auction_path: Path,
    output_path: Path,
    auction_sku_column: Optional[str] = None,
    return_frames: bool = False,
    cfg: Optional[AllocationConfig | Dict[str, object]] = None,
):
    # Настраиваем логирование
    log_file = setup_logging()
    logger.info("\n" + "="*100)
    logger.info("🚀 НАЧАЛО РАСПРЕДЕЛЕНИЯ АУКЦИОНА")
    logger.info("="*100)
    
    sales = load_sales_table(sales_path)
    sku_velocity, dept_velocity, weeks_span = compute_velocity(sales)
    if not sales.empty:
        cat_velocity_series = sales.dropna(subset=["category"]).groupby(["category", "department"])["qty"].sum() / weeks_span
    else:
        cat_velocity_series = pd.Series(dtype=float)
    cat_velocity = cat_velocity_series.to_dict()
    dept_velocity_map = dept_velocity.set_index("department")["weekly_velocity"].to_dict()

    logger.info(f"Продажи загружены: {len(sales)} строк, окно {weeks_span} нед.")
    logger.info(f"Скорость по SKU/подразделению: {len(sku_velocity)} записей.")
    logger.info(f"Скорость по подразделению: {len(dept_velocity)} записей.")
    if not dept_velocity.empty:
        logger.info(f"Уникальных подразделений: {dept_velocity['department'].nunique()}")
        logger.info(f"Уникальных регионов: {dept_velocity['region'].nunique()}")
    
    print(f"Продажи загружены: {len(sales)} строк, окно {weeks_span} нед.")
    print(f"Скорость по SKU/подразделению: {len(sku_velocity)} записей.")
    print(f"Скорость по подразделению: {len(dept_velocity)} записей.")

    stock = load_stock(stock_path)
    logger.info(f"Остатки загружены: {len(stock)} SKU-позиций.")
    print(f"Остатки загружены: {len(stock)} SKU-позиций.")

    coverage = build_coverage(stock, sku_velocity)
    auction_counts, auction_meta = load_auction(auction_path, auction_sku_column)
    logger.info(f"Лотов в реестре: {sum(auction_counts.values())} (уникальных SKU: {len(auction_counts)}).")
    print(f"Лотов в реестре: {sum(auction_counts.values())} (уникальных SKU: {len(auction_counts)}).")

    if cfg is None:
        config = AllocationConfig()
    elif isinstance(cfg, dict):
        config = AllocationConfig(**cfg)
    else:
        config = cfg
    
    # 🆕 СТРОИМ КАРТУ КОЛИЧЕСТВА ПО КАТЕГОРИЯМ (для Assortment Balance)
    # dept -> category -> count
    dept_cat_qty_map: Dict[str, Dict[str, int]] = {}
    
    # 1. Заполняем из текущих остатков
    if stock is not None and not stock.empty:
        # stock должен иметь колонки department, category, stock_qty
        # Группируем, чтобы получить сумму штук по (подразделение, категория)
        stock_grp = stock.groupby(["department", "category"])["stock_qty"].sum().reset_index()
        for _, row in stock_grp.iterrows():
            d = row["department"]
            c = str(row["category"]).strip()
            q = int(row["stock_qty"])
            if d not in dept_cat_qty_map:
                dept_cat_qty_map[d] = {}
            dept_cat_qty_map[d][c] = dept_cat_qty_map[d].get(c, 0) + q

    allocations: List[Dict[str, object]] = []
    # 1. Считываем реестр
    auction_counts, auction_meta = load_auction(auction_path, auction_sku_column)
    logger.info(f"Лотов в реестре: {sum(auction_counts.values())} (уникальных SKU: {len(auction_meta)}).")
    
    # 🚨 РАСЧЕТ ОБЩЕГО ЛИМИТА
    total_items = sum(auction_counts.values())
    max_per_dept_global = int(total_items * config.max_department_percentage) if config.max_department_percentage else None
    if max_per_dept_global:
        logger.info(f"🎯 ГЛОБАЛЬНЫЙ ЛИМИТ на подразделение: {max_per_dept_global} шт ({config.max_department_percentage*100:.0f}% от {total_items})")
    
    # Общий счетчик загрузки подразделений
    global_dept_load: Dict[str, int] = {}

    
    # Сортируем SKU: сначала редкие/дорогие (по желанию), или просто идем по списку
    # Сейчас идем просто по порядку ключей
    for sku, qty in auction_counts.items():
        allocate_sku(
            sku,
            qty,
            coverage,
            dept_velocity,
            cat_velocity,
            dept_velocity_map,
            auction_meta,
            allocations, # НОВОЕ: передаем список
            dept_cat_qty_map, # НОВОЕ: карта количеств
            config,
            stock=stock,
            global_dept_load=global_dept_load,
            max_per_dept_global=max_per_dept_global
        )

    # Собираем итоговый DataFrame

    # Собираем итоговый DataFrame

    if not allocations:
        logger.error("❌ Не удалось сформировать распределение — нет данных по продажам/остаткам.")
        raise RuntimeError("Не удалось сформировать распределение — нет данных по продажам/остаткам.")

    alloc_df = pd.DataFrame(allocations)
    alloc_df = alloc_df.rename(
        columns={
            "sku": "Артикул",
            "department": "Подразделение",
            "region": "Регион",
            "category": "Категория",
            "item_name": "Вид предмета",  # НОВОЕ
            "description": "Описание",  # НОВОЕ
            "send_qty": "Отправить, шт",
            "stock_qty": "Текущий остаток, шт",
            "weekly_velocity": "Скорость, шт/нед",
            "coverage_weeks": "Покрытие, недель",
            "prob_sell": f"Вероятность продажи ≤{config.prob_target_days}д, %",
            "score": "Скор",
            "reason": "Комментарий",
        }
    )
    alloc_df[f"Вероятность продажи ≤{config.prob_target_days}д, %"] = (
        alloc_df[f"Вероятность продажи ≤{config.prob_target_days}д, %"] * 100
    )

    summary_df = (
        alloc_df.groupby(["Подразделение", "Регион"], as_index=False)["Отправить, шт"]
        .sum()
        .sort_values("Отправить, шт", ascending=False)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path) as writer:
        alloc_df.to_excel(writer, sheet_name="Распределение", index=False)
        summary_df.to_excel(writer, sheet_name="Итог по подразделениям", index=False)

    logger.info("\n" + "="*100)
    logger.info("📊 ИТОГОВАЯ СТАТИСТИКА")
    logger.info("="*100)
    logger.info(f"Всего распределено: {len(allocations)} штук")
    logger.info(f"Уникальных SKU: {alloc_df['Артикул'].nunique()}")
    logger.info(f"Подразделений задействовано: {len(summary_df)}")
    logger.info("\nТоп-5 подразделений по количеству:")
    for idx, row in summary_df.head(5).iterrows():
        pct = row['Отправить, шт'] / sum(summary_df['Отправить, шт']) * 100
        logger.info(f"  {idx+1}. {row['Подразделение']} ({row['Регион']}): {row['Отправить, шт']} шт ({pct:.1f}%)")
    logger.info(f"\n✅ Файл сохранен: {output_path}")
    logger.info(f"📝 Лог сохранен: {log_file}")
    logger.info("="*100 + "\n")
    
    print(f"Файл сохранен: {output_path}")
    print(f"📝 Лог сохранен: {log_file}")
    if return_frames:
        return output_path, alloc_df, summary_df
    return output_path


def parse_args() -> argparse.Namespace:
    default_sales = BASE_DIR / "Табличная_часть_Продажи_распродажа_0109_311225.xlsx"
    default_stock = BASE_DIR / "остатки на 301125.xlsx"
    default_auction = BASE_DIR / "Реестр аукциона 15.11 Санкт-Петербург.xlsx"
    default_output = BASE_DIR / "распределение_аукцион.xlsx"

    parser = argparse.ArgumentParser(description="Распределение лотов аукциона по подразделениям.")
    parser.add_argument("--sales", type=Path, default=default_sales, help="Путь к файлу табличной части продаж.")
    parser.add_argument("--stock", type=Path, default=default_stock, help="Путь к файлу остатков.")
    parser.add_argument("--auction", type=Path, default=default_auction, help="Путь к реестру аукциона.")
    parser.add_argument("--out", type=Path, default=default_output, help="Путь к итоговому XLSX.")
    parser.add_argument(
        "--auction-sku-column",
        type=str,
        default=None,
        help="Если имя колонки с артикулом в реестре другое, укажите его здесь.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_allocation(args.sales, args.stock, args.auction, args.out, args.auction_sku_column)
