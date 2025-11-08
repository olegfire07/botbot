# utils.py

import streamlit as st
import pandas as pd
import base64
import io
import yaml
import json
from calculations import calculate_financials, calculate_irr


def generate_download_link(df: pd.DataFrame, filename="results.csv", link_text="Скачать CSV", return_raw=False):
    """Создаёт либо ссылку, либо возвращает CSV-строку/bytes (если return_raw=True)."""
    csv_data = df.to_csv(index=False)
    if return_raw:
        return csv_data.encode("utf-8")  # Возвращаем bytes
    # Иначе прежнее поведение:
    import base64
    b64 = base64.b64encode(csv_data.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{link_text}</a>'
    return href

def generate_excel_download(df: pd.DataFrame, filename="results.xlsx", link_text="Скачать Excel", return_raw=False):
    """Создаёт либо ссылку, либо возвращает Excel-данные (bytes)."""
    import io
    import base64
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
    excel_data = output.getvalue()
    if return_raw:
        return excel_data
    # Иначе прежнее поведение:
    b64 = base64.b64encode(excel_data).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="{filename}">{link_text}</a>'
    return href



def normalize_shares(changed_share_key, new_value, old_shares=None):
    """Нормализует доли хранения, чтобы их сумма оставалась корректной."""
    if old_shares is None:
        old_shares = st.session_state.shares.copy()
    st.session_state.shares[changed_share_key] = new_value
    other_keys = [k for k in st.session_state.shares if k != changed_share_key]
    total_other = sum(old_shares[k] for k in other_keys)
    if total_other > 0:
        for k in other_keys:
            st.session_state.shares[k] = max(
                0, old_shares[k] - (1 - new_value) * old_shares[k] / total_other
            )


def perform_sensitivity_analysis(params, param_key, param_values, disable_extended):
    """Проводит анализ чувствительности по заданному параметру."""
    base_val = getattr(params, param_key)
    results = []
    for val in param_values:
        setattr(params, param_key, val)
        fin = calculate_financials(params, disable_extended)
        results.append({"Параметр": val, "Прибыль (руб.)": fin["profit"]})
    setattr(params, param_key, base_val)
    return pd.DataFrame(results)


def safe_display_irr(irr_value):
    """Безопасное отображение IRR в интерфейсе."""
    if irr_value is None:
        st.metric("IRR (%)", "Невозможно рассчитать")
    else:
        st.metric("IRR (%)", f"{irr_value:.2f}%")

def load_css(file_path):
    """Загружает CSS из файла."""
    with open(file_path, "r") as f:
        css = f"<style>{f.read()}</style>"
        st.markdown(css, unsafe_allow_html=True)

def load_params_from_file(file_path):
    """Загружает параметры из YAML или JSON."""
    try:
        with open(file_path, "r") as file:
            if file_path.endswith((".yaml", ".yml")):
                return yaml.safe_load(file)
            elif file_path.endswith(".json"):
                return json.load(file)
            else:
                raise ValueError("Неподдерживаемый формат файла")
    except Exception as e:
        st.error(f"Ошибка при загрузке параметров: {e}")
        return None


def save_params_to_file(params, filename, file_format):
    """Сохраняет параметры в файл (JSON или YAML)."""
    try:
        if file_format == "json":
            return json.dumps(params, indent=4, ensure_ascii=False).encode("utf-8")
        elif file_format == "yaml":
            return yaml.dump(params, indent=4, sort_keys=False, allow_unicode=True).encode("utf-8")
        else:
            raise ValueError("Неподдерживаемый формат файла")
    except Exception as e:
        st.error(f"Ошибка при сохранении параметров: {e}")
        return None