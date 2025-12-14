from typing import Dict, List, Tuple

from .config import ComputationConfig
from .data_structures import (
    LiquidationLevel,
    MarketState,
    OpenInterestCluster,
)


def compute_distance_percent(price: float, target: float) -> float:
    return ((target - price) / price) * 100


def classify_cluster_strength(size: float, leverage: float) -> str:
    score = size * (1 + leverage / 50)
    if score > 40:
        return "very_high"
    if score > 25:
        return "high"
    if score > 15:
        return "medium"
    return "low"


def estimate_leverage_bucket(leverage: float) -> str:
    if leverage < 5:
        return "1-5x"
    if leverage < 10:
        return "5-10x"
    if leverage < 20:
        return "10-20x"
    if leverage < 30:
        return "20-30x"
    if leverage < 40:
        return "30-40x"
    return "40x+"


def score_cluster(
    cluster: OpenInterestCluster, market: MarketState, config: ComputationConfig
) -> Tuple[float, float, LiquidationLevel]:
    distance_percent = compute_distance_percent(market.price, cluster.price)
    volatility_penalty = 1 - min(0.4, abs(distance_percent) / (market.volatility.atr + 1e-9))
    liquidity_penalty = 1 - min(0.3, sum(market.orderbook.liquidity_gaps))
    funding_bias = market.funding.bias if cluster.side == "long" else -market.funding.bias
    funding_boost = 1 + funding_bias * 0.1
    oi_delta_bias = 1 + market.oi_delta
    cvd_bias = 1 + (market.cvd * 0.05)

    historical_factor = market.historical_liquidations.get(cluster.side, 0.2)
    lever_score = min(cluster.estimated_leverage / config.leverage_buckets[1], 1)
    base_intensity = cluster.size / 25

    intensity = base_intensity * volatility_penalty * liquidity_penalty * funding_boost
    intensity *= max(0.6, historical_factor) * (1 + lever_score * 0.3)
    intensity *= max(0.7, oi_delta_bias) * max(0.7, cvd_bias)
    intensity = max(0.01, min(1.0, intensity))

    cascade_probability = calculate_cascade_probability(cluster, market, abs(distance_percent))
    time_factor = min(1.0, config.time_horizon_minutes / 120)
    probability = intensity * (0.6 + cascade_probability * 0.4) * time_factor
    probability = max(0.01, min(1.0, probability))

    level = LiquidationLevel(
        price=round(cluster.price, 2),
        intensity=round(intensity, 3),
        probability=round(probability, 3),
        side=cluster.side,
        cluster_strength=classify_cluster_strength(cluster.size, cluster.estimated_leverage),
        estimated_leverage=estimate_leverage_bucket(cluster.estimated_leverage),
        distance_percent=round(distance_percent, 3),
    )
    return intensity, probability, level


def calculate_cascade_probability(cluster: OpenInterestCluster, market: MarketState, distance_percent: float) -> float:
    volatility_factor = min(1.0, market.volatility.realized * 10)
    funding_factor = abs(market.funding.rate) * 150
    leverage_factor = min(1.0, cluster.estimated_leverage / 50)
    distance_factor = max(0.2, 1 - distance_percent / 10)
    imbalance_factor = 1 + (0.05 * (1 if cluster.side == "long" else -1) * market.cvd)
    cascade_base = max(
        0.05,
        min(1.0, volatility_factor * 0.4 + funding_factor * 0.2 + leverage_factor * 0.3 + distance_factor * 0.1),
    )
    return max(0.01, min(1.0, cascade_base * imbalance_factor))


def filter_levels(levels: List[LiquidationLevel], config: ComputationConfig, side: str) -> List[LiquidationLevel]:
    filtered = [
        lvl
        for lvl in levels
        if lvl.intensity >= config.intensity_threshold and lvl.probability >= config.probability_threshold
    ]
    filtered.sort(key=lambda l: l.intensity * 0.6 + l.probability * 0.4, reverse=True)
    trimmed = filtered[: config.max_levels]
    if side == "long":
        trimmed.sort(key=lambda l: l.price)
    else:
        trimmed.sort(key=lambda l: l.price, reverse=True)
    return trimmed


def build_levels(market: MarketState, config: ComputationConfig) -> Dict[str, List[LiquidationLevel]]:
    long_levels: List[LiquidationLevel] = []
    short_levels: List[LiquidationLevel] = []
    for cluster in market.oi_clusters:
        intensity, probability, level = score_cluster(cluster, market, config)
        if cluster.side == "long":
            long_levels.append(level)
        else:
            short_levels.append(level)

    long_levels = filter_levels(long_levels, config, side="long")
    short_levels = filter_levels(short_levels, config, side="short")
    return {"long_liquidations": long_levels, "short_liquidations": short_levels}


def determine_nearest(levels: Dict[str, List[LiquidationLevel]], price: float) -> Dict[str, LiquidationLevel]:
    def nearest(levels_list: List[LiquidationLevel]) -> LiquidationLevel:
        if not levels_list:
            return None
        return min(levels_list, key=lambda l: abs(l.price - price))

    return {
        "nearest_long_liq": nearest(levels["long_liquidations"]),
        "nearest_short_liq": nearest(levels["short_liquidations"]),
    }


def derive_signals(levels: Dict[str, List[LiquidationLevel]], price: float) -> Dict[str, object]:
    long_level = levels["long_liquidations"][0] if levels["long_liquidations"] else None
    short_level = levels["short_liquidations"][0] if levels["short_liquidations"] else None

    market_bias = "neutral"
    liquidity_gravity = "flat"
    confidence = 0.5

    if long_level and short_level:
        if abs(long_level.distance_percent) < abs(short_level.distance_percent):
            market_bias = "bearish"
            liquidity_gravity = "down"
        else:
            market_bias = "bullish"
            liquidity_gravity = "up"
        confidence = (long_level.intensity + short_level.intensity) / 2
    elif long_level:
        market_bias = "bearish"
        liquidity_gravity = "down"
        confidence = long_level.intensity
    elif short_level:
        market_bias = "bullish"
        liquidity_gravity = "up"
        confidence = short_level.intensity

    return {
        "long_danger_zone": long_level.price if long_level else None,
        "short_danger_zone": short_level.price if short_level else None,
        "market_bias": market_bias,
        "liquidity_gravity": liquidity_gravity,
        "confidence": round(confidence, 3),
    }
