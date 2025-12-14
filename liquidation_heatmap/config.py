from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class DataSourceConfig:
    symbol: str
    exchanges: List[str] = None

    def __post_init__(self) -> None:
        if self.exchanges is None:
            self.exchanges = ["binance", "bybit", "okx", "deribit"]


@dataclass
class ComputationConfig:
    intensity_threshold: float = 0.1
    probability_threshold: float = 0.1
    max_levels: int = 5
    atr_window: int = 14
    volatility_window: int = 30
    leverage_buckets: Tuple[int, int] = (5, 50)
    time_horizon_minutes: int = 60
    sensitivity: float = 1.0

    def adjust_thresholds(self, multiplier: float) -> None:
        self.intensity_threshold = max(0.05, min(0.95, self.intensity_threshold * multiplier))
        self.probability_threshold = max(0.05, min(0.95, self.probability_threshold * multiplier))
