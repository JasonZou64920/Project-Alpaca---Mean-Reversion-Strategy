# alpaca clients and a retry helper - paper trading only
import os
import time

from dotenv import load_dotenv
from alpaca.common.exceptions import APIError
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.trading.client import TradingClient

from data.logs import get_logger

log = get_logger("data")
load_dotenv()


def get_keys():
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in .env "
                           "(copy config/.env.example to .env and fill it in).")
    return key, secret


def stock_client():
    key, secret = get_keys()
    return StockHistoricalDataClient(key, secret)


def crypto_client():
    key, secret = get_keys()
    return CryptoHistoricalDataClient(key, secret)


def trading_client():
    # paper=True: orders only ever hit the paper account, never real money
    key, secret = get_keys()
    return TradingClient(key, secret, paper=True)


def retry(fn, tries=3, base_delay=2.0, what="api call"):
    """Run fn, retrying network errors with exponential backoff.

    APIError is not retried - that is Alpaca answering "no" (bad symbol,
    rejected order, bad parameters) and asking again will not change it.
    Everything else (timeouts, connection drops) gets tries with 2s, 4s waits.
    """
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except APIError:
            raise
        except Exception as e:
            if attempt == tries:
                log.error(f"{what} failed after {tries} tries: {e}")
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning(f"{what} failed ({e}) - retry {attempt}/{tries - 1} in {delay:.0f}s")
            time.sleep(delay)
