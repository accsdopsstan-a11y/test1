import asyncio
import json
from typing import Dict

from .analytics import build_levels, determine_nearest, derive_signals
from .config import ComputationConfig, DataSourceConfig
from .data_structures import HeatmapResult
from .data_sources import collect_market_state


async def build_liquidation_heatmap(symbol: str, config: ComputationConfig | None = None) -> Dict[str, object]:
    computation_config = config or ComputationConfig()
    data_config = DataSourceConfig(symbol=symbol)
    computation_config.adjust_thresholds(computation_config.sensitivity)

    market_state = await collect_market_state(data_config)
    levels = build_levels(market_state, computation_config)
    nearest = determine_nearest(levels, market_state.price)
    signals = derive_signals(levels, market_state.price)

    result = HeatmapResult(
        symbol=symbol,
        timestamp=market_state.timestamp,
        current_price=round(market_state.price, 2),
        liquidation_levels=levels,
        nearest_levels=nearest,
        trading_signals=signals,
    )
    return result.to_dict()


def run_sync(symbol: str, config: ComputationConfig | None = None) -> Dict[str, object]:
    return asyncio.run(build_liquidation_heatmap(symbol, config))


def pretty_print(result: Dict[str, object]) -> None:
    print(json.dumps(result, indent=2))
