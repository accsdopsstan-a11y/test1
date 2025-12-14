import asyncio
import math
import time
from functools import lru_cache
from typing import Dict, List, Optional

import aiohttp

from .config import DataSourceConfig
from .data_structures import (
    FundingData,
    MarketState,
    OpenInterestCluster,
    OrderBookSnapshot,
    VolatilityMetrics,
    VolumeProfile,
)


async def safe_fetch(url: str, session: aiohttp.ClientSession) -> Optional[dict]:
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                return await response.json()
            return None
    except Exception as e:  # pragma: no cover - network dependent
        print(f"Error fetching {url}: {e}")
        return None


class BinanceClient:
    BASE_URL = "https://fapi.binance.com"

    def __init__(self) -> None:
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def get_price(self, symbol: str) -> float:
        url = f"{self.BASE_URL}/fapi/v1/ticker/price?symbol={symbol}"
        session = await self._get_session()
        data = await safe_fetch(url, session)
        if not data:
            raise RuntimeError("Failed to fetch price")
        return float(data.get("price", 0.0))

    async def get_orderbook(self, symbol: str, limit: int = 100) -> OrderBookSnapshot:
        url = f"{self.BASE_URL}/fapi/v1/depth?symbol={symbol}&limit={limit}"
        session = await self._get_session()
        data = await safe_fetch(url, session)
        if not data:
            raise RuntimeError("Failed to fetch orderbook")

        bids_raw = data.get("bids", [])
        asks_raw = data.get("asks", [])

        bids_volumes = [float(entry[1]) for entry in bids_raw[:10]]
        asks_volumes = [float(entry[1]) for entry in asks_raw[:10]]

        def normalize(values: List[float]) -> List[float]:
            if not values:
                return []
            max_val = max(values)
            if max_val == 0:
                return [0.0 for _ in values]
            return [v / max_val for v in values]

        bids = normalize(bids_volumes)
        asks = normalize(asks_volumes)

        def compute_gaps(levels: List[List[str]]) -> List[float]:
            if len(levels) < 2:
                return [0.0]
            prices = [float(level[0]) for level in levels[:10]]
            prices_sorted = sorted(prices)
            gaps = []
            for prev, curr in zip(prices_sorted, prices_sorted[1:]):
                gap = abs(curr - prev) / prices_sorted[0] if prices_sorted[0] else 0.0
                gaps.append(gap)
            return gaps or [0.0]

        liquidity_gaps = compute_gaps(bids_raw) + compute_gaps(asks_raw)

        return OrderBookSnapshot(bids=bids, asks=asks, liquidity_gaps=liquidity_gaps)

    async def get_funding_rate(self, symbol: str) -> FundingData:
        url = f"{self.BASE_URL}/fapi/v1/fundingRate?symbol={symbol}&limit=1"
        session = await self._get_session()
        data = await safe_fetch(url, session)
        if not data:
            raise RuntimeError("Failed to fetch funding rate")
        entry = data[0]
        rate = float(entry.get("fundingRate", 0.0))
        bias = max(-1.0, min(1.0, rate * 100))
        return FundingData(rate=rate, bias=bias)

    async def get_open_interest(self, symbol: str) -> float:
        url = f"{self.BASE_URL}/fapi/v1/openInterest?symbol={symbol}"
        session = await self._get_session()
        data = await safe_fetch(url, session)
        if not data:
            raise RuntimeError("Failed to fetch open interest")
        return float(data.get("openInterest", 0.0))

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 50) -> List:
        url = f"{self.BASE_URL}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
        session = await self._get_session()
        data = await safe_fetch(url, session)
        if not data:
            raise RuntimeError("Failed to fetch klines")
        return data

    async def get_long_short_ratio(self, symbol: str) -> float:
        url = f"{self.BASE_URL}/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=1h&limit=1"
        session = await self._get_session()
        data = await safe_fetch(url, session)
        if not data:
            raise RuntimeError("Failed to fetch long/short ratio")
        entry = data[0]
        return float(entry.get("longShortRatio", 1.0))


def calculate_atr(klines: List, period: int = 14) -> float:
    if len(klines) < period + 1:
        return 0.0
    trs: List[float] = []
    prev_close = float(klines[0][4])
    for kline in klines[1:]:
        high = float(kline[2])
        low = float(kline[3])
        close = float(kline[4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
        prev_close = close
    relevant_trs = trs[-period:]
    return sum(relevant_trs) / len(relevant_trs) if relevant_trs else 0.0


def calculate_realized_volatility(closes: List[float], period: int = 30) -> float:
    if len(closes) < period + 1:
        return 0.0
    returns: List[float] = []
    for prev, curr in zip(closes[-(period + 1) : -1], closes[-period:]):
        if prev == 0:
            continue
        returns.append(math.log(curr / prev))
    if not returns:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / max(len(returns) - 1, 1)
    return math.sqrt(variance) * math.sqrt(252)


def build_volume_profile(klines: List, bins: int = 20) -> List[VolumeProfile]:
    if not klines:
        return []
    lows = [float(k[3]) for k in klines]
    highs = [float(k[2]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    opens = [float(k[1]) for k in klines]
    closes = [float(k[4]) for k in klines]

    min_price = min(lows)
    max_price = max(highs)
    if max_price == min_price:
        max_price += 1
    bin_width = (max_price - min_price) / bins

    profile: List[VolumeProfile] = []
    volume_bins = [0.0 for _ in range(bins)]
    imbalance_bins = [0.0 for _ in range(bins)]

    for o, h, l, c, v in zip(opens, highs, lows, closes, volumes):
        typical_price = (h + l + c) / 3
        bin_index = int((typical_price - min_price) / bin_width)
        bin_index = min(bin_index, bins - 1)
        volume_bins[bin_index] += v
        direction = 1 if c >= o else -1
        imbalance_bins[bin_index] += direction * v

    for idx, total_volume in enumerate(volume_bins):
        center_price = min_price + bin_width * idx + bin_width / 2
        imbalance = imbalance_bins[idx] / total_volume if total_volume else 0.0
        profile.append(
            VolumeProfile(
                node_price=center_price,
                volume=total_volume,
                imbalance=max(-1.0, min(1.0, imbalance)),
            )
        )
    return profile


def estimate_liquidation_levels(
    price: float,
    total_oi: float,
    long_short_ratio: float,
    key_levels: List[VolumeProfile],
    leverages: List[int] = [5, 10, 20, 50, 100],
) -> List[OpenInterestCluster]:
    if total_oi <= 0:
        return []

    long_share = long_short_ratio / (1 + long_short_ratio) if long_short_ratio > 0 else 0.5
    short_share = 1 - long_share

    levels_sorted = sorted(key_levels, key=lambda n: n.volume, reverse=True) if key_levels else []
    if not levels_sorted:
        levels_sorted = [VolumeProfile(node_price=price, volume=1.0, imbalance=0.0)]

    top_levels = levels_sorted[: max(3, len(levels_sorted))]
    total_volume = sum(level.volume for level in top_levels) or 1.0

    clusters: List[OpenInterestCluster] = []
    for level in top_levels:
        level_weight = level.volume / total_volume
        for lev in leverages:
            long_liq_price = level.node_price * (1 - 1 / lev)
            short_liq_price = level.node_price * (1 + 1 / lev)
            base_size = total_oi * level_weight / len(leverages)
            long_size = base_size * long_share * (1 + max(0.0, level.imbalance))
            short_size = base_size * short_share * (1 + max(0.0, -level.imbalance))
            clusters.append(
                OpenInterestCluster(
                    price=long_liq_price,
                    size=long_size,
                    side="long",
                    estimated_leverage=float(lev),
                )
            )
            clusters.append(
                OpenInterestCluster(
                    price=short_liq_price,
                    size=short_size,
                    side="short",
                    estimated_leverage=float(lev),
                )
            )
    return clusters


def calculate_volatility_metrics(klines: List, atr_window: int = 14, volatility_window: int = 30) -> VolatilityMetrics:
    closes = [float(k[4]) for k in klines]
    realized = calculate_realized_volatility(closes, period=volatility_window)
    atr = calculate_atr(klines, period=atr_window)
    implied_proxy = realized
    return VolatilityMetrics(realized=realized, implied_proxy=implied_proxy, atr=atr)


@lru_cache(maxsize=32)
def _cached_levels(symbol: str) -> Dict[str, float]:
    return {"timestamp": time.time()}


def _cache_valid(cache_entry: Dict[str, float], ttl: int = 5) -> bool:
    return cache_entry and (time.time() - cache_entry.get("timestamp", 0) < ttl)


async def collect_market_state(config: DataSourceConfig) -> MarketState:
    client = BinanceClient()
    try:
        cache_entry = _cached_levels(config.symbol)
        if not _cache_valid(cache_entry):
            _cached_levels.cache_clear()
            _cached_levels(config.symbol)

        price, orderbook, funding, oi, klines, lsr = await asyncio.gather(
            client.get_price(config.symbol),
            client.get_orderbook(config.symbol),
            client.get_funding_rate(config.symbol),
            client.get_open_interest(config.symbol),
            client.get_klines(config.symbol, "1h", 50),
            client.get_long_short_ratio(config.symbol),
        )

        volatility = calculate_volatility_metrics(klines)
        volume_profile = build_volume_profile(klines)
        oi_clusters = estimate_liquidation_levels(price, oi, lsr, volume_profile)

        return MarketState(
            symbol=config.symbol,
            price=price,
            orderbook=orderbook,
            funding=funding,
            oi_clusters=oi_clusters,
            volatility=volatility,
            volume_profile=volume_profile,
            oi_delta=0.0,
            cvd=0.0,
            historical_liquidations={"long": 0.3, "short": 0.3},
            timestamp=time.time(),
        )
    finally:
        await client.close()
