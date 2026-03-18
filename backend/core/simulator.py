"""
Market price simulation engine — Geometric Brownian Motion (GBM).

Architecture
------------
- In-memory dict (_cache) holds the live float price for every tracked symbol.
- A background daemon thread ticks every TICK_INTERVAL seconds and applies
  one GBM step to each symbol.
- After each tick, updated prices are written to the MarketPrice DB table so
  prices survive server restarts.
- On cold start, prices are loaded from MarketPrice (DB) → SEED_PRICES →
  hash-based deterministic fallback, in that order.

GBM formula (one discrete step)
--------------------------------
  S(t + dt) = S(t) * exp( (μ - ½σ²)·dt  +  σ·√dt·Z )

  where:
    μ   = annual drift (expected return)
    σ   = annual volatility
    dt  = TICK_INTERVAL / TRADING_SECONDS_PER_DAY  (~0.000128)
    Z   ~ N(0, 1)  standard normal

  exp() guarantees S is always positive regardless of Z.

Thread safety
-------------
  _lock (threading.RLock) protects all reads/writes to _cache.
  DB writes happen outside the lock to avoid blocking request handlers.

Integration points
------------------
  get_current_price(symbol)         → float | None   (used by market_data.py)
  ensure_tracked(symbol)            → float          (initialises on first trade)
  get_all_prices()                  → dict[str, float]
  start_scheduler() / stop_scheduler()
"""

import hashlib
import logging
import math
import random
import threading
import time
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

# ── Simulation constants ───────────────────────────────────────────────────────

# How often the simulator ticks (seconds)
TICK_INTERVAL: int = 3

# Trading day length used to convert annual vol/drift to per-tick units.
# 6.5 hours × 3600 s/h = 23 400 seconds per trading day.
_TRADING_SECONDS: float = 23_400.0

# dt = fraction of a trading day per tick
_DT: float = TICK_INTERVAL / _TRADING_SECONDS   # ≈ 0.0001282

# Bid-ask half-spread applied at order execution.
# BUY pays mid × (1 + spread); SELL receives mid × (1 – spread).
BID_ASK_HALF_SPREAD: Decimal = Decimal("0.0005")   # 0.05%

# ── Realistic seed prices (USD) ───────────────────────────────────────────────
# Used when the symbol has no persisted MarketPrice row yet.
# These are plausible reference levels, NOT live data.

SEED_PRICES: dict[str, float] = {
    "AAPL":  191.00,
    "MSFT":  415.00,
    "NVDA":  870.00,
    "TSLA":  180.00,
    "AMZN":  186.00,
    "GOOGL": 165.00,
    "META":  500.00,
    "AMD":   155.00,
    "INTC":   30.00,
    "SPY":   530.00,
    "QQQ":   460.00,
    "IWM":   200.00,
    "VTI":   235.00,
    "VOO":   485.00,
    "DIA":   395.00,
    "GLD":   228.00,
    "TLT":    95.00,
    "ARKK":   45.00,
    "KO":     63.00,
}

# ── Per-symbol GBM parameters (annual drift μ, annual volatility σ) ───────────
# Unlisted symbols fall back to _DEFAULT_PARAMS.
# Volatility tiers:
#   High  σ ≥ 0.45   → visible, rapid moves (TSLA, NVDA)
#   Med   σ 0.20–0.35 → moderate moves (AAPL, MSFT, AMZN)
#   Low   σ ≤ 0.18   → slow, stable moves (KO, GLD, SPY)

_DEFAULT_PARAMS: tuple[float, float] = (0.08, 0.30)

SYMBOL_PARAMS: dict[str, tuple[float, float]] = {
    # ── High volatility ────────────────────────────────────────────────────────
    "TSLA":  (0.12, 0.65),
    "NVDA":  (0.18, 0.60),
    "ARKK":  (0.04, 0.55),
    "AMD":   (0.10, 0.50),
    # ── Medium-high ────────────────────────────────────────────────────────────
    "META":  (0.14, 0.35),
    "INTC":  (0.01, 0.35),
    "AMZN":  (0.11, 0.30),
    # ── Medium ─────────────────────────────────────────────────────────────────
    "AAPL":  (0.09, 0.25),
    "MSFT":  (0.11, 0.25),
    "GOOGL": (0.10, 0.28),
    # ── Low-medium (indices / broad market) ───────────────────────────────────
    "QQQ":   (0.09, 0.20),
    "IWM":   (0.07, 0.20),
    "SPY":   (0.08, 0.16),
    "VTI":   (0.08, 0.16),
    "VOO":   (0.08, 0.16),
    "DIA":   (0.07, 0.15),
    # ── Low ────────────────────────────────────────────────────────────────────
    "GLD":   (0.04, 0.15),
    "TLT":   (0.02, 0.12),
    "KO":    (0.05, 0.12),
}

# ── In-memory price cache ──────────────────────────────────────────────────────

# symbol (upper) → current price (float).
# float used internally for GBM speed; converted to Decimal at API boundaries.
_cache: dict[str, float] = {}
_lock = threading.RLock()

# ── Scheduler state ───────────────────────────────────────────────────────────

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()
_tick_count: int = 0


# ── GBM core ──────────────────────────────────────────────────────────────────

def _gbm_step(price: float, mu: float, sigma: float) -> float:
    """
    Apply one discrete GBM step.

        S(t+dt) = S(t) * exp( (μ - ½σ²)·dt + σ·√dt·Z )

    Z ~ N(0, 1).  exp() guarantees result is always positive.
    """
    z = random.gauss(0.0, 1.0)
    exponent = (mu - 0.5 * sigma ** 2) * _DT + sigma * math.sqrt(_DT) * z
    return price * math.exp(exponent)


# ── Seed price ────────────────────────────────────────────────────────────────

def _seed_price(symbol: str) -> float:
    """
    Realistic starting price for any symbol.

    Known symbols → SEED_PRICES dict.
    Unknown symbols → deterministic hash in [$18, $500] so the same symbol
    always starts at the same price and the range is financially plausible.
    """
    if symbol in SEED_PRICES:
        return SEED_PRICES[symbol]
    digest = hashlib.sha256(symbol.upper().encode()).hexdigest()
    seed = int(digest[:8], 16)
    ratio = seed / 0xFFFF_FFFF
    return round(18.0 + ratio * 482.0, 2)


# ── Public cache accessors ─────────────────────────────────────────────────────

def get_current_price(symbol: str) -> float | None:
    """
    Return the current simulated price for a symbol, or None if not tracked.
    Thread-safe O(1) read.
    """
    with _lock:
        return _cache.get(symbol.upper())


def get_all_prices() -> dict[str, float]:
    """Return a snapshot copy of all tracked symbol prices."""
    with _lock:
        return dict(_cache)


def ensure_tracked(symbol: str) -> float:
    """
    Guarantee the symbol has an entry in the cache, initialising it if needed.
    Initialisation order: DB (persisted) → SEED_PRICES → hash fallback.
    Returns the current price.
    """
    symbol = symbol.upper()

    with _lock:
        if symbol in _cache:
            return _cache[symbol]

    # Not yet in cache — load from DB or seed
    price = _load_from_db(symbol)
    if price is None:
        price = _seed_price(symbol)
        logger.info("[SIMULATOR] Seeding new symbol %s at %.4f", symbol, price)

    with _lock:
        _cache[symbol] = price

    _persist_to_db(symbol, price, is_new=True)
    return price


# ── DB persistence ─────────────────────────────────────────────────────────────

def _load_from_db(symbol: str) -> float | None:
    """Read a persisted price from MarketPrice. Returns None if no row exists."""
    try:
        from .models import MarketPrice
        row = MarketPrice.objects.filter(symbol=symbol).first()
        if row:
            return float(row.price)
    except Exception as exc:
        logger.debug("[SIMULATOR] DB load failed for %s: %s", symbol, exc)
    return None


def _persist_to_db(symbol: str, price: float, *, is_new: bool = False) -> None:
    """Upsert a single price row into MarketPrice."""
    try:
        from .models import MarketPrice
        price_dec = Decimal(str(round(price, 6)))
        if is_new:
            MarketPrice.objects.update_or_create(
                symbol=symbol,
                defaults={"price": price_dec, "open_price": price_dec},
            )
        else:
            MarketPrice.objects.filter(symbol=symbol).update(price=price_dec)
    except Exception as exc:
        logger.debug("[SIMULATOR] DB persist failed for %s: %s", symbol, exc)


def _persist_batch(prices: dict[str, float]) -> None:
    """
    Bulk-update MarketPrice rows for all symbols in the dict.
    Uses individual UPDATEs (N queries) — acceptable for ≤ ~50 symbols.
    """
    try:
        from .models import MarketPrice
        for symbol, price in prices.items():
            MarketPrice.objects.filter(symbol=symbol).update(
                price=Decimal(str(round(price, 6)))
            )
    except Exception as exc:
        logger.debug("[SIMULATOR] Batch DB persist failed: %s", exc)


# ── Scheduler ─────────────────────────────────────────────────────────────────

def _tick() -> None:
    """
    Apply one GBM step to every tracked symbol.

    1. Read all current prices (under lock).
    2. Compute new prices (outside lock — pure computation).
    3. Write new prices back to cache (under lock).
    4. Persist to DB (outside lock — I/O).
    5. Log per-symbol: old price, new price, volatility used.
    """
    global _tick_count

    with _lock:
        if not _cache:
            return
        snapshot: dict[str, float] = dict(_cache)

    new_prices: dict[str, float] = {}

    for symbol, old_price in snapshot.items():
        mu, sigma = SYMBOL_PARAMS.get(symbol, _DEFAULT_PARAMS)
        new_price = _gbm_step(old_price, mu, sigma)
        new_prices[symbol] = new_price

        logger.debug(
            "[SIMULATOR] %-8s  before=%.4f  after=%.4f  vol=%.2f  drift=%.3f",
            symbol, old_price, new_price, sigma, mu,
        )

    with _lock:
        _cache.update(new_prices)

    _tick_count += 1

    # Print a summary line every 10 ticks (every 30 s) for easy dev visibility
    if _tick_count % 10 == 0:
        sample = sorted(new_prices.items())[:5]
        sample_str = "  ".join(f"{s}=${p:.2f}" for s, p in sample)
        print(f"[SIMULATOR] tick #{_tick_count}  {len(new_prices)} symbols  {sample_str} ...")

    # Persist outside lock so I/O doesn't stall request handlers
    _persist_batch(new_prices)


def _warm_up() -> None:
    """
    Pre-load all SEED_PRICES symbols into the cache at scheduler start.
    This ensures /market/prices/ returns data immediately and every known
    symbol's price is fluctuating from the first request.
    """
    for symbol in SEED_PRICES:
        ensure_tracked(symbol)
    logger.info("[SIMULATOR] Warm-up complete — %d symbols tracked", len(SEED_PRICES))
    print(f"[SIMULATOR] Warm-up: {len(SEED_PRICES)} symbols initialised")


def _run_loop() -> None:
    """Main scheduler loop. Runs in the daemon thread."""
    logger.info(
        "[SIMULATOR] Loop started — tick every %ds, dt=%.6f",
        TICK_INTERVAL, _DT,
    )
    print(f"[SIMULATOR] Price simulator running (tick={TICK_INTERVAL}s)")

    _warm_up()

    while not _stop_event.is_set():
        try:
            _tick()
        except Exception as exc:
            logger.exception("[SIMULATOR] Unexpected error in tick: %s", exc)
        _stop_event.wait(timeout=TICK_INTERVAL)

    logger.info("[SIMULATOR] Loop stopped")
    print("[SIMULATOR] Price simulator stopped")


def start_scheduler() -> None:
    """
    Launch the background price simulation thread.
    Idempotent — safe to call multiple times.
    """
    global _scheduler_thread

    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.debug("[SIMULATOR] Scheduler already running — skipping start")
        return

    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_run_loop,
        name="price-simulator",
        daemon=True,   # Won't block Python from exiting
    )
    _scheduler_thread.start()
    logger.info("[SIMULATOR] Thread started: %s", _scheduler_thread.name)


def stop_scheduler() -> None:
    """Stop the scheduler gracefully and wait for the thread to finish."""
    _stop_event.set()
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=TICK_INTERVAL + 2)
    logger.info("[SIMULATOR] Stopped")
