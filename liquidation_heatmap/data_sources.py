import asyncio
import random
import time
from typing import Dict, List

from .config import DataSourceConfig
from .data_structures import (
    FundingData,
    MarketState,
    OpenInterestCluster,
    OrderBookSnapshot,
    VolatilityMetrics,
    VolumeProfile,
)


class ExchangeClient:
    def __init__(self, name: str) -> None:
        self.name = name

    async def fetch_orderbook(self, symbol: str) -> OrderBookSnapshot:
        await asyncio.sleep(0)
        bids = [random.uniform(0.8, 1.0) for _ in range(10)]
        asks = [random.uniform(0.8, 1.0) for _ in range(10)]
        liquidity_gaps = [random.uniform(0, 0.2) for _ in range(3)]
        return OrderBookSnapshot(bids=bids, asks=asks, liquidity_gaps=liquidity_gaps)

    async def fetch_funding(self, symbol: str) -> FundingData:
        await asyncio.sleep(0)
        rate = random.uniform(-0.0005, 0.0005)
        bias = random.uniform(-1, 1)
        return FundingData(rate=rate, bias=bias)

    async def fetch_oi_clusters(self, symbol: str) -> List[OpenInterestCluster]:
        await asyncio.sleep(0)
        clusters: List[OpenInterestCluster] = []
        base_price = 100000
        for _ in range(6):
            offset = random.uniform(-0.08, 0.08) * base_price
            size = random.uniform(5, 20)
            side = random.choice(["long", "short"])
            leverage = random.uniform(3, 40)
            clusters.append(
                OpenInterestCluster(
                    price=base_price + offset,
                    size=size,
                    side=side,
                    estimated_leverage=leverage,
                )
            )
        return clusters

    async def fetch_volatility(self, symbol: str) -> VolatilityMetrics:
        await asyncio.sleep(0)
        realized = random.uniform(0.02, 0.09)
        implied_proxy = realized * random.uniform(0.9, 1.2)
        atr = realized * random.uniform(0.8, 1.4) * 1000
        return VolatilityMetrics(realized=realized, implied_proxy=implied_proxy, atr=atr)

    async def fetch_volume_profile(self, symbol: str) -> List[VolumeProfile]:
        await asyncio.sleep(0)
        nodes: List[VolumeProfile] = []
        base_price = 100000
        for _ in range(8):
            offset = random.uniform(-0.05, 0.05) * base_price
            volume = random.uniform(50, 200)
            imbalance = random.uniform(-1, 1)
            nodes.append(VolumeProfile(node_price=base_price + offset, volume=volume, imbalance=imbalance))
        return nodes


async def collect_market_state(config: DataSourceConfig) -> MarketState:
    clients = [ExchangeClient(name) for name in config.exchanges]
    tasks = []
    for client in clients:
        tasks.extend(
            [
                client.fetch_orderbook(config.symbol),
                client.fetch_funding(config.symbol),
                client.fetch_oi_clusters(config.symbol),
                client.fetch_volatility(config.symbol),
                client.fetch_volume_profile(config.symbol),
            ]
        )

    results = await asyncio.gather(*tasks)
    orderbooks: List[OrderBookSnapshot] = []
    fundings: List[FundingData] = []
    oi_clusters: List[OpenInterestCluster] = []
    vols: List[VolatilityMetrics] = []
    volume_nodes: List[VolumeProfile] = []

    for idx in range(0, len(results), 5):
        orderbooks.append(results[idx])
        fundings.append(results[idx + 1])
        oi_clusters.extend(results[idx + 2])
        vols.append(results[idx + 3])
        volume_nodes.extend(results[idx + 4])

    price = 100000 + random.uniform(-500, 500)
    avg_funding = sum(f.rate for f in fundings) / len(fundings)
    funding_bias = sum(f.bias for f in fundings) / len(fundings)
    oi_delta = random.uniform(-0.03, 0.03)
    cvd = random.uniform(-1, 1)
    historical_liqs: Dict[str, float] = {
        "long": random.uniform(0.1, 0.6),
        "short": random.uniform(0.1, 0.6),
    }

    aggregated_orderbook = aggregate_orderbooks(orderbooks)
    volatility = aggregate_volatility(vols)

    return MarketState(
        symbol=config.symbol,
        price=price,
        orderbook=aggregated_orderbook,
        funding=FundingData(rate=avg_funding, bias=funding_bias),
        oi_clusters=oi_clusters,
        volatility=volatility,
        volume_profile=volume_nodes,
        oi_delta=oi_delta,
        cvd=cvd,
        historical_liquidations=historical_liqs,
        timestamp=time.time(),
    )


def aggregate_orderbooks(orderbooks: List[OrderBookSnapshot]) -> OrderBookSnapshot:
    bids = [sum(level) / len(orderbooks) for level in zip(*[ob.bids for ob in orderbooks])]
    asks = [sum(level) / len(orderbooks) for level in zip(*[ob.asks for ob in orderbooks])]
    liquidity_gaps: List[float] = []
    for ob in orderbooks:
        liquidity_gaps.extend(ob.liquidity_gaps)
    avg_gap = sum(liquidity_gaps) / len(liquidity_gaps)
    return OrderBookSnapshot(bids=bids, asks=asks, liquidity_gaps=[avg_gap])


def aggregate_volatility(vols: List[VolatilityMetrics]) -> VolatilityMetrics:
    realized = sum(v.realized for v in vols) / len(vols)
    implied_proxy = sum(v.implied_proxy for v in vols) / len(vols)
    atr = sum(v.atr for v in vols) / len(vols)
    return VolatilityMetrics(realized=realized, implied_proxy=implied_proxy, atr=atr)
