from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class OrderBookSnapshot:
    bids: List[float]
    asks: List[float]
    liquidity_gaps: List[float]


@dataclass
class FundingData:
    rate: float
    bias: float


@dataclass
class OpenInterestCluster:
    price: float
    size: float
    side: str
    estimated_leverage: float


@dataclass
class VolatilityMetrics:
    realized: float
    implied_proxy: float
    atr: float


@dataclass
class VolumeProfile:
    node_price: float
    volume: float
    imbalance: float


@dataclass
class MarketState:
    symbol: str
    price: float
    orderbook: OrderBookSnapshot
    funding: FundingData
    oi_clusters: List[OpenInterestCluster]
    volatility: VolatilityMetrics
    volume_profile: List[VolumeProfile]
    oi_delta: float
    cvd: float
    historical_liquidations: Dict[str, float]
    timestamp: float


@dataclass
class LiquidationLevel:
    price: float
    intensity: float
    probability: float
    side: str
    cluster_strength: str
    estimated_leverage: str
    distance_percent: float

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class HeatmapResult:
    symbol: str
    timestamp: float
    current_price: float
    liquidation_levels: Dict[str, List[LiquidationLevel]]
    nearest_levels: Dict[str, Optional[LiquidationLevel]]
    trading_signals: Dict[str, object]

    def to_dict(self) -> Dict[str, object]:
        serialized_levels = {
            key: [level.to_dict() for level in levels]
            for key, levels in self.liquidation_levels.items()
        }
        serialized_nearest = {
            key: value.to_dict() if value else None for key, value in self.nearest_levels.items()
        }
        result = {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "current_price": self.current_price,
            "liquidation_levels": serialized_levels,
            "nearest_levels": serialized_nearest,
            "trading_signals": self.trading_signals,
        }
        return result
