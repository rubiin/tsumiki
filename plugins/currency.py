"""Launcher slash command: /currency — convert between world currencies.

Rates are fetched from Frankfurter (keyless) into a per-day local cache,
so the API is hit at most once per day.
"""

import os
import threading
import time
from datetime import date
from typing import ClassVar

from utils.constants import FX_RATES_CACHE_FILE
from utils.functions import ensure_directory, read_json_file, write_json_file
from utils.plugin_manager import (
    LauncherPlugin,
    PluginCancelledError,
    PluginResult,
    copy_to_clipboard,
    http_request,
)

#: Returns all EUR-based rates as a list of {date, base, quote, rate} rows.
_FRANKFURTER_RATES_URL = "https://api.frankfurter.dev/v2/rates"

# Retry transient failures; client errors (4xx) are never retried.
_RETRY_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 0.5

# A payload below this many rates is treated as malformed (never cached).
_MIN_RATES_COUNT = 10

# Serializes cache read/refresh so concurrent worker threads don't download
# the daily file twice.
_RATES_LOCK = threading.Lock()

#: Common names/symbols → ISO 4217 codes, so "dollar", "$" and "euro" work.
_COMMON_CURRENCIES = {
    "$": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "buck": "USD",
    "bucks": "USD",
    "€": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "quid": "GBP",
    "¥": "JPY",
    "yen": "JPY",
    "yuan": "CNY",
    "renminbi": "CNY",
    "rmb": "CNY",
    "rupee": "INR",
    "rupees": "INR",
    "₽": "RUB",
    "ruble": "RUB",
    "rubles": "RUB",
    "franc": "CHF",
    "francs": "CHF",
    "won": "KRW",
    "real": "BRL",
    "reais": "BRL",
    "peso": "MXN",
    "pesos": "MXN",
    "lira": "TRY",
    "krone": "DKK",
    "krona": "SEK",
    "zloty": "PLN",
    "koruna": "CZK",
    "forint": "HUF",
    "rand": "ZAR",
    "baht": "THB",
    "ringgit": "MYR",
    "shekel": "ILS",
    "dirham": "AED",
    "riyal": "SAR",
    "hryvnia": "UAH",
}


def _today() -> str:
    """Return today's date as ISO 8601 (yyyy-mm-dd)."""
    return date.today().isoformat()


def normalize_rows(rows: list) -> tuple[str, dict[str, float]]:
    """Turn the API's row list into (date, {quote: rate})."""
    rates: dict[str, float] = {}
    latest_date = ""
    for row in rows:
        if not isinstance(row, dict) or "quote" not in row or "rate" not in row:
            continue
        rates[str(row["quote"])] = float(row["rate"])
        row_date = str(row.get("date", ""))
        if row_date > latest_date:
            latest_date = row_date
    # Rates are EUR-based; EUR is always 1:1 with itself.
    rates["EUR"] = 1.0
    return latest_date or _today(), rates


class _DownloadCancelledError(RuntimeError):
    """Raised when a superseded query aborts a rates download mid-retry."""


def _download_rates(cancelled=None) -> tuple[str, dict[str, float]]:
    """Download the latest EUR-based rates; returns (date, {quote: rate})."""
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            response = http_request(cancelled, "GET", _FRANKFURTER_RATES_URL)
            response.raise_for_status()
            fx_date, rates = normalize_rows(response.json())
            # Guard against malformed/empty payloads: a nearly-empty table
            # would poison the daily cache, so treat it as a failed download
            # and let the stale-cache fallback take over.
            if len(rates) < _MIN_RATES_COUNT:
                raise ValueError(
                    f"Frankfurter returned only {len(rates)} currency rate(s)"
                )
            return fx_date, rates
        except PluginCancelledError:
            raise _DownloadCancelledError()
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            is_client_error = status is not None and 400 <= status < 500
            if is_client_error or attempt >= _RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_RETRY_DELAY_SECONDS)
    raise RuntimeError("unreachable")  # pragma: no cover - loop returns or raises


def _read_cache() -> dict | None:
    """Return the cached {date, fetched, rates} payload, or None."""
    if not os.path.exists(FX_RATES_CACHE_FILE):
        return None

    payload = read_json_file(FX_RATES_CACHE_FILE)
    if not isinstance(payload, dict):
        return None

    rates = payload.get("rates")
    if (
        not isinstance(rates, dict)
        or not rates
        or not payload.get("date")
        or not payload.get("fetched")
    ):
        return None
    return payload


def _write_cache(payload: dict) -> None:
    """Persist the daily rates snapshot (best-effort)."""
    try:
        # Both calls must complete before returning: load_rates() reads this
        # file back on the next call, and the plugin already runs on a worker
        # thread, so off-thread writes would race it.
        ensure_directory(os.path.dirname(FX_RATES_CACHE_FILE), sync=True)
        write_json_file(FX_RATES_CACHE_FILE, payload, sync=True)
    except OSError:
        pass  # caching is best-effort; conversions still work this session


def load_rates(cancelled=None) -> dict:
    """Return the daily rates payload, downloading at most once a day.

    Falls back to the last snapshot on failure. *cancelled* aborts a
    superseded download.
    """
    with _RATES_LOCK:
        cached = _read_cache()
        if cached and cached.get("fetched") == _today():
            return cached
        try:
            fx_date, rates = _download_rates(cancelled=cancelled)
        except _DownloadCancelledError:
            raise  # superseded — propagate so handle() bails out
        except Exception:
            if cached:  # network hiccup — use the last snapshot
                return cached
            raise
        payload = {"date": fx_date, "fetched": _today(), "rates": rates}
        _write_cache(payload)
        return payload


def fetch_rate(from_code: str, to_code: str, cancelled=None) -> tuple[float, str]:
    """Return the (rate, date) converting *from_code* to *to_code*."""
    if from_code == to_code:
        return 1.0, _today()
    payload = load_rates(cancelled=cancelled)
    rates = payload["rates"]
    if from_code not in rates or to_code not in rates:
        raise ValueError(f"Unknown currency codes '{from_code}' / '{to_code}'")
    # All rates are EUR-based: X -> Y = (EUR -> Y) / (EUR -> X).
    return rates[to_code] / rates[from_code], str(payload.get("date", ""))


def normalize_code(token: str) -> str:
    """Return the ISO 4217 code for *token*, mapping common names/symbols."""
    token = token.strip().casefold()
    if token in _COMMON_CURRENCIES:
        return _COMMON_CURRENCIES[token]
    return token.upper()


def parse_query(args: str) -> tuple[float, str, str] | None:
    """Parse ``<amount> <from> [to] <to>`` into (amount, from_code, to_code).

    Returns None for an empty query; raises ValueError with a user-facing
    message when the expression can't be parsed.
    """
    tokens = args.strip().split()
    if not tokens:
        return None
    tokens = [token for token in tokens if token.casefold() != "to"]

    if len(tokens) == 2:
        # Two tokens: either "from to" (amount defaults to 1) or a numeric
        # amount with a missing target currency.
        try:
            amount = float(tokens[0].replace(",", ""))
        except ValueError:
            amount, from_cur, to_cur = 1.0, tokens[0], tokens[1]
        else:
            raise ValueError(
                f"Missing target currency: /currency {tokens[0]} {tokens[1]} <to>"
            )
    elif len(tokens) == 3:
        try:
            amount = float(tokens[0].replace(",", ""))
        except ValueError:
            raise ValueError(f"'{tokens[0]}' is not a valid amount")
        from_cur, to_cur = tokens[1], tokens[2]
    else:
        raise ValueError(
            "Expected: /currency <amount> <from> <to>  e.g. /currency 100 usd to eur"
        )

    from_code = normalize_code(from_cur)
    to_code = normalize_code(to_cur)
    if from_code == to_code:
        raise ValueError(f"'{from_code}' and '{to_code}' are the same currency")
    if (
        not from_code.isalpha()
        or not to_code.isalpha()
        or len(from_code) != 3
        or len(to_code) != 3
    ):
        raise ValueError(f"Unknown currency codes '{from_cur}' / '{to_cur}'")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    return amount, from_code, to_code


def format_money(value: float) -> str:
    """Format a monetary value compactly (up to 6 decimals, no trailing zeros)."""
    return f"{value:,.6f}".rstrip("0").rstrip(".")


class CurrencyPlugin(LauncherPlugin):
    """Slash command: /currency — convert amounts between currencies."""

    name = "currency"
    description = "Convert between currencies (daily rates, cached locally)"
    icon = "💱"
    aliases: ClassVar[list[str]] = ["fx", "money", "exchange"]
    # The first query of the day downloads the rates file, so give the user a
    # moment to finish typing before that happens.
    debounce_ms = 400

    def handle(self, args: str) -> list[PluginResult]:
        parsed = parse_query(args)
        if parsed is None:
            return [
                PluginResult(
                    "Usage: /currency <amount> <from> <to>",
                    subtitle=("e.g. /currency 100 usd to eur  or  /currency usd eur"),
                    icon=self.icon,
                )
            ]
        amount, from_code, to_code = parsed
        try:
            rate, date = fetch_rate(from_code, to_code, cancelled=self.is_cancelled)
        except _DownloadCancelledError:
            return []
        except Exception as exc:
            return [
                PluginResult(
                    "Conversion failed",
                    subtitle=f"{exc}",
                    icon="network-error-symbolic",
                )
            ]
        converted = amount * rate
        date_text = f" · {date}" if date else ""
        return [
            PluginResult(
                f"{format_money(amount)} {from_code} = "
                f"{format_money(converted)} {to_code}",
                subtitle=(
                    f"Rate {format_money(rate)} {from_code}→{to_code}"
                    f"{date_text} · Press Enter to copy"
                ),
                icon=self.icon,
                data=f"{format_money(converted)} {to_code}",
            )
        ]

    def execute(self, result: PluginResult | None = None) -> bool:
        if result is not None and result.data:
            copy_to_clipboard(str(result.data))
        return False  # close the launcher after copying
