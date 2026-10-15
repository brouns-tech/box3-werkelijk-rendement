"""Lazy, public ECB rates and auditable EUR valuations of reconciled USD cash."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import urllib.request
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from wr.money import amount, decimal_value

CONVERSION_VERSION = 1
VALUE_FIELDS = (
    "start_balance", "end_balance", "deposits", "withdrawals",
    "interest_received", "interest_paid", "dividends_gross", "withholding_tax", "capital_gain",
)


class ConversionUnavailable(ValueError):
    pass


def fact_extra(fact) -> dict:
    raw = fact["extra"] if "extra" in fact.keys() else None
    try:
        data = json.loads(raw or "{}") if isinstance(raw, str) else raw
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _input_hash(fact, extra: dict) -> str:
    payload = {key: fact[key] for key in ("currency", "tax_year", *VALUE_FIELDS)}
    payload["fx_evidence"] = extra.get("fx_evidence")
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def eur_conversion(fact) -> dict | None:
    extra = fact_extra(fact)
    conversion = extra.get("eur_conversion")
    if (not isinstance(conversion, dict) or conversion.get("version") != CONVERSION_VERSION
            or conversion.get("input_sha256") != _input_hash(fact, extra)):
        return None
    return conversion


def eur_values(fact) -> dict | None:
    """EUR fields for aggregation without changing the original source fact."""
    if (fact["currency"] or "EUR") == "EUR":
        return dict(fact)
    conversion = eur_conversion(fact)
    return conversion["values"] if conversion else None


def _positive_rate(value: str) -> Decimal:
    try:
        rate = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ConversionUnavailable("Invalid ECB exchange rate") from exc
    if not rate.is_finite() or rate <= 0:
        raise ConversionUnavailable("Invalid ECB exchange rate")
    return rate


class RateBook:
    def __init__(self, rates: dict[str, str], source: dict):
        self.rates = {date.fromisoformat(day): _positive_rate(value) for day, value in rates.items()}
        self.days = sorted(self.rates)
        self.source = source

    def lookup(self, day: date) -> tuple[date, Decimal]:
        index = bisect_right(self.days, day) - 1
        if index < 0 or (day - self.days[index]).days > 7:
            raise ConversionUnavailable(f"No recent ECB rate for {day.isoformat()}")
        selected = self.days[index]
        return selected, self.rates[selected]


def _download_rates(year: int) -> tuple[dict[str, str], dict]:
    # Only public currency/year parameters leave the computer.
    start = date(year, 1, 1) - timedelta(days=10)
    end = date(year, 12, 31)
    if end >= date.today():
        raise ConversionUnavailable("Historical conversion requires a completed tax year")
    url = ("https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
           f"?startPeriod={start.isoformat()}&endPeriod={end.isoformat()}&format=csvdata")
    request = urllib.request.Request(url, headers={"Accept": "text/csv", "User-Agent": "WerkelijkRendement-FX/1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ConversionUnavailable("ECB response exceeds size limit")
    rates = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if (row.get("KEY") != "EXR.D.USD.EUR.SP00.A" or row.get("CURRENCY") != "USD"
                or row.get("CURRENCY_DENOM") != "EUR"):
            raise ConversionUnavailable("Unexpected ECB currency series")
        day = date.fromisoformat(row["TIME_PERIOD"])
        if not start <= day <= end or day.isoformat() in rates:
            raise ConversionUnavailable("Unexpected ECB observation date")
        rates[day.isoformat()] = str(_positive_rate(row["OBS_VALUE"]))
    source = {"provider": "ECB", "series": "EXR.D.USD.EUR.SP00.A", "url": url,
              "fetched_at": datetime.now(timezone.utc).isoformat(),
              "response_sha256": hashlib.sha256(raw).hexdigest()}
    return rates, source


def historical_rates(conn: sqlite3.Connection, year: int) -> RateBook:
    cached = conn.execute("SELECT payload FROM exchange_rate_cache WHERE currency='USD' AND tax_year=?", (year,)).fetchone()
    if cached:
        payload = json.loads(cached[0])
        return RateBook(payload["rates"], payload["source"])
    rates, source = _download_rates(year)
    book = RateBook(rates, source)
    # Reject empty/truncated histories before persisting them.
    book.lookup(date(year, 1, 1))
    book.lookup(date(year, 12, 31))
    conn.execute("INSERT INTO exchange_rate_cache(currency,tax_year,payload) VALUES ('USD',?,?)",
                 (year, json.dumps({"rates": rates, "source": source})))
    return book


def _transactions(fact, extra: dict) -> list[dict]:
    evidence = extra.get("fx_evidence")
    if not isinstance(evidence, dict) or evidence.get("reconciled") is not True:
        raise ConversionUnavailable("Dated transactions are missing or do not reconcile")
    transactions = evidence.get("transactions")
    if not isinstance(transactions, list) or any(fact[key] is None for key in ("start_balance", "end_balance", "deposits", "withdrawals", "interest_received")):
        raise ConversionUnavailable("Incomplete USD cash evidence")
    incoming, outgoing, interest = Decimal(0), Decimal(0), Decimal(0)
    last_day = date(fact["tax_year"], 1, 1)
    for item in transactions:
        day = date.fromisoformat(item["date"])
        value = decimal_value(item["amount"])
        if day.year != fact["tax_year"] or day < last_day or not value.is_finite() or value <= 0:
            raise ConversionUnavailable("Invalid dated transaction")
        last_day = day
        if item["kind"] not in {"transfer", "interest"} or item["direction"] not in {"in", "out"}:
            raise ConversionUnavailable("Unknown transaction type")
        if item["direction"] == "in":
            incoming += value
            if item["kind"] == "interest":
                interest += value
        else:
            if item["kind"] == "interest":
                raise ConversionUnavailable("Debit interest requires additional evidence")
            outgoing += value
    if (incoming - interest != decimal_value(fact["deposits"])
            or outgoing != decimal_value(fact["withdrawals"])
            or interest != decimal_value(fact["interest_received"])
            or decimal_value(fact["start_balance"]) + incoming - outgoing != decimal_value(fact["end_balance"])):
        raise ConversionUnavailable("USD transactions do not reconcile to summary")
    if any(fact[key] not in (None, 0) for key in ("interest_paid", "dividends_gross", "withholding_tax")):
        raise ConversionUnavailable("Additional income needs dated conversion evidence")
    return transactions


def _convert(fact, extra: dict, transactions: list[dict], book: RateBook | None) -> dict:
    audit = []

    def convert(value, day: date, kind: str, direction: str = "") -> Decimal:
        native = decimal_value(value)
        if native == 0:
            return Decimal(0)
        selected, rate = book.lookup(day)
        eur = native / rate
        audit.append({"kind": kind, "direction": direction, "date": day.isoformat(),
                      "native_amount": str(native), "rate_date": selected.isoformat(),
                      "usd_per_eur": str(rate), "eur_unrounded": str(eur)})
        return eur

    year = fact["tax_year"]
    opening = convert(fact["start_balance"], date(year, 1, 1), "opening_balance")
    closing = convert(fact["end_balance"], date(year, 12, 31), "closing_balance")
    deposits = withdrawals = interest = Decimal(0)
    for item in transactions:
        value = convert(item["amount"], date.fromisoformat(item["date"]), item["kind"], item["direction"])
        if item["kind"] == "interest":
            interest += value
        elif item["direction"] == "in":
            deposits += value
        else:
            withdrawals += value
    # Deposits exclude credited interest: the balance/flow result includes it once.
    effective = amount(closing - opening - deposits + withdrawals)
    interest_eur = amount(interest)
    fx_gain = amount(decimal_value(effective) - decimal_value(interest_eur))
    values = dict(zip(VALUE_FIELDS, (amount(opening), amount(closing), amount(deposits),
                  amount(withdrawals), interest_eur, 0.0, 0.0, 0.0, fx_gain)))
    return {"version": CONVERSION_VERSION, "input_sha256": _input_hash(fact, extra),
            "method": "ecb_daily_previous_published" if book else "zero_values",
            "source": book.source if book else None, "values": values,
            "effective_return": effective, "fx_gain": fx_gain, "audit": audit,
            "rounding": "Decimal arithmetic; round totals to cents, not individual credits"}


def convert_usd_facts(conn: sqlite3.Connection) -> None:
    """Called on import/recompute, never by UI rendering or audit export."""
    from wr.portfolio import is_box3_fact

    books: dict[int, RateBook | Exception] = {}
    for fact in conn.execute("SELECT * FROM account_year_facts WHERE is_canonical=1 AND currency='USD'").fetchall():
        if not is_box3_fact(fact) or eur_conversion(fact):
            continue
        extra = fact_extra(fact)
        try:
            transactions = _transactions(fact, extra)
            nonzero = bool(transactions or fact["start_balance"] or fact["end_balance"])
            book = None
            if nonzero:
                year = fact["tax_year"]
                if year not in books:
                    try:
                        books[year] = historical_rates(conn, year)
                    except (OSError, ValueError, KeyError, UnicodeError, csv.Error) as exc:
                        books[year] = exc
                book = books[year]
                if isinstance(book, Exception):
                    raise ConversionUnavailable("Historical ECB rates unavailable; retry import or recompute") from book
            extra["eur_conversion"] = _convert(fact, extra, transactions, book)
            extra.pop("eur_conversion_error", None)
            extra["fx_status"] = "converted_to_eur"
        except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
            extra.pop("eur_conversion", None)
            extra["eur_conversion_error"] = str(exc)
            extra["fx_status"] = "requires_eur_conversion"
        conn.execute("UPDATE account_year_facts SET extra=? WHERE id=?", (json.dumps(extra), fact["id"]))
    conn.commit()
