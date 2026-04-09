"""
Base Strategy — Tüm stratejilerin miras aldığı temel sınıf
"""
import pandas as pd


class Signal:
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class BaseStrategy:
    def __init__(self, name: str = "BaseStrategy"):
        self.name = name

    def generate_signal(self, df: pd.DataFrame) -> str:
        return Signal.HOLD

    def generate(self, df: pd.DataFrame, **kwargs):
        raise NotImplementedError
