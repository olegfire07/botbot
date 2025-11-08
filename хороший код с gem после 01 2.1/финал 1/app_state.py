# app_state.py
import streamlit as st
import yaml

class AppState:
    """
    Класс для управления состоянием приложения, оборачивающий st.session_state.
    """
    def __init__(self):
        if "initialized" not in st.session_state:
            self.load_default_state()
            st.session_state["initialized"] = True

    def load_default_state(self):
        """Загружает состояние по умолчанию из config.yaml."""
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
        return st.session_state.shares

    def update_share(self, key, value):
        st.session_state.shares[key] = value

    def get(self, key):
        return st.session_state.get(key)

    def set(self, key, value):
        st.session_state[key] = value