"""
Polymarket API wrapper — fetches markets, prices, and places trades.
Falls back to Manifold Markets if Polymarket is unavailable.
"""
import requests
import time
from datetime import datetime, timedelta

POLYMARKET_CLOB_URL = "https://clob.polymarket.com"
POLYMARKET_GAMMA_URL = "https://gamma-api.polymarket.com"
MANIFOLD_API_URL = "https://api.manifold.markets/v0"


def fetch_polymarket_markets(
    min_liquidity: float = 10000,
    min_volume: float = 1000,
    min_hours: int = 1,
    max_days: int = 7,
) -> list:
    """Fetch active markets from Polymarket Gamma API."""
    markets = []
    try:
        # Fetch events with active markets
        resp = requests.get(
            f"{POLYMARKET_GAMMA_URL}/markets",
            params={
                "closed": "false",
                "limit": 100,
                "order": "volume24hr",
                "ascending": "false",
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw_markets = resp.json()

        now = datetime.utcnow()
        for m in raw_markets:
            try:
                liquidity = float(m.get("liquidityNum", 0) or 0)
                volume_24h = float(m.get("volume24hr", 0) or 0)
                end_date_str = m.get("endDate") or m.get("end_date_iso", "")

                # Parse end date
                end_date = None
                if end_date_str:
                    try:
                        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                # Time to resolution filter
                if end_date:
                    time_to_end = end_date - now
                    hours_to_end = time_to_end.total_seconds() / 3600
                    if hours_to_end < min_hours or hours_to_end > max_days * 24:
                        continue

                # Liquidity & volume filter
                if liquidity < min_liquidity or volume_24h < min_volume:
                    continue

                # Extract prices
                price_yes = float(m.get("outcomePrices", "[0.5]").strip("[]").split(",")[0]) if isinstance(m.get("outcomePrices"), str) else 0.5
                price_no = 1.0 - price_yes
                spread = abs(price_yes - price_no)

                # Determine flag reasons
                flags = []
                price_change = float(m.get("volumeNum", 0) or 0)  # Approximation
                if spread > 0.03:
                    flags.append(f"Wide spread ({spread:.1%})")
                if volume_24h > min_volume * 5:
                    flags.append(f"High volume (${volume_24h:,.0f})")

                markets.append({
                    "id": str(m.get("id", m.get("conditionId", ""))),
                    "question": m.get("question", ""),
                    "slug": m.get("slug", ""),
                    "liquidity": liquidity,
                    "volume_24h": volume_24h,
                    "price_yes": price_yes,
                    "price_no": price_no,
                    "spread": spread,
                    "end_date": end_date_str,
                    "category": m.get("groupItemTitle", m.get("category", "")),
                    "flagged_reason": " | ".join(flags),
                    "price_change_1h": 0,
                    "status": "active",
                    "source": "polymarket",
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[Polymarket] Error: {e}")
        # Fallback to Manifold
        markets = fetch_manifold_markets(min_liquidity, min_volume, min_hours, max_days)

    return markets


def fetch_manifold_markets(
    min_liquidity: float = 10000,
    min_volume: float = 1000,
    min_hours: int = 1,
    max_days: int = 7,
) -> list:
    """Fallback: Fetch from Manifold Markets API."""
    markets = []
    try:
        resp = requests.get(
            f"{MANIFOLD_API_URL}/markets",
            params={"limit": 200, "sort": "liquidity"},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()

        now = datetime.utcnow()
        for m in raw:
            if m.get("isResolved") or not m.get("closeTime"):
                continue

            liquidity = float(m.get("totalLiquidity", 0))
            volume = float(m.get("volume", 0))
            close_time = datetime.fromtimestamp(m["closeTime"] / 1000)
            hours_to_end = (close_time - now).total_seconds() / 3600

            if hours_to_end < min_hours or hours_to_end > max_days * 24:
                continue
            if liquidity < min_liquidity * 0.1 or volume < min_volume * 0.1:
                continue

            prob = float(m.get("probability", 0.5))
            flags = []
            if volume > min_volume:
                flags.append("High volume")

            markets.append({
                "id": m.get("id", ""),
                "question": m.get("question", ""),
                "slug": m.get("slug", ""),
                "liquidity": liquidity,
                "volume_24h": volume,
                "price_yes": prob,
                "price_no": 1 - prob,
                "spread": 0,
                "end_date": close_time.isoformat(),
                "category": m.get("groupSlugs", [""])[0] if m.get("groupSlugs") else "",
                "flagged_reason": " | ".join(flags),
                "price_change_1h": 0,
                "status": "active",
                "source": "manifold",
            })
    except Exception as e:
        print(f"[Manifold] Error: {e}")

    return markets


def get_market_price(market_id: str, source: str = "polymarket") -> dict:
    """Get current price for a market."""
    try:
        if source == "polymarket":
            resp = requests.get(f"{POLYMARKET_GAMMA_URL}/markets/{market_id}", timeout=15)
            resp.raise_for_status()
            m = resp.json()
            price_yes = float(m.get("outcomePrices", "[0.5]").strip("[]").split(",")[0]) if isinstance(m.get("outcomePrices"), str) else 0.5
            return {"price_yes": price_yes, "price_no": 1 - price_yes}
        else:
            resp = requests.get(f"{MANIFOLD_API_URL}/market/{market_id}", timeout=15)
            resp.raise_for_status()
            m = resp.json()
            prob = float(m.get("probability", 0.5))
            return {"price_yes": prob, "price_no": 1 - prob}
    except Exception:
        return {"price_yes": 0.5, "price_no": 0.5}
