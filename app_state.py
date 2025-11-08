# app_state.py
import streamlit as st
import yaml

class AppState:
    """
    Класс для управления состоянием приложения, оборачивающий st.session_state.

    Этот класс инициализирует st.session_state, загружая параметры по умолчанию
    из config.yaml при первом запуске приложения. Он также предоставляет методы
    для получения и установки значений параметров и управления долями (shares).
    """
    def __init__(self):
        """
        Инициализирует состояние приложения, загружая значения по умолчанию,
        если приложение запущено в первый раз.
        """
        if "initialized" not in st.session_state:
            self.load_default_state()
            st.session_state["initialized"] = True

    def load_default_state(self):
        """
        Загружает состояние по умолчанию из config.yaml.

        Читает значения параметров из config.yaml и устанавливает их
        в st.session_state, а также инициализирует доли (shares).
        """
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        default_params = config["default_params"]
        st.session_state.shares = {
            "storage_share": float(default_params["storage_share"]),
            "loan_share": float(default_params["loan_share"]),
            "vip_share": float(default_params["vip_share"]),
            "short_term_share": float(default_params["short_term_share"]),
        }
        for key, value in default_params.items():
            if key not in st.session_state:
                st.session_state[key] = value
        st.session_state["amortize_one_time_expenses"] = False


    @property
    def shares(self):
        """
        Возвращает словарь с долями.

        Returns:
             dict: Словарь с долями хранения (storage_share, loan_share, vip_share, short_term_share)
        """
        return st.session_state.shares

    def update_share(self, key, value):
        """
        Обновляет значение доли в st.session_state.shares

        Args:
            key (str): Ключ доли, которую нужно обновить (например, 'storage_share').
            value (float): Новое значение доли.
        """
        st.session_state.shares[key] = value

    def get(self, key):
        """
        Возвращает значение из st.session_state по ключу.

        Args:
            key (str): Ключ для получения значения из st.session_state.

        Returns:
            any: Значение параметра из st.session_state или None если ключ не найден.
        """
        return st.session_state.get(key)

    def set(self, key, value):
        """
        Устанавливает значение в st.session_state по ключу.

        Args:
            key (str): Ключ для установки значения.
            value (any): Значение, которое нужно установить.
        """
        st.session_state[key] = value