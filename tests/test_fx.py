import csv
import io
import json
import sqlite3
import zipfile
from dataclasses import asdict
from datetime import date
from decimal import Decimal

import pytest

from dashboard.app import _overview_return_totals, _return_components
from wr.db import init_db, insert_facts
from wr.export import create_audit_export
from wr.fx import (ConversionUnavailable, RateBook, convert_usd_facts, eur_conversion,
                   historical_rates)
from wr.models import AccountYearFact
from wr.parsers.revolut import parse_revolut
from wr.portfolio import _coverage_for_year, _fact_return


USD_STATEMENT = """
USD Statement
Revolut Bank UAB (Netherlands Branch)
ALEX EXAMPLE
IBAN NL00REVO0000000000
Balance summary
Account (Current Account) $0.00 $100.00 $100.00 $0.00
Deposit $0.00 $20.00 $110.00 $90.00
Total $0.00 $120.00 $210.00 $90.00
Account transactions from January 1, 2025 to December 31, 2025
Jan 2, 2025 Exchanged to USD              $100.00 $100.00
€97.00
Jan 2, 2025 To Instant Access Savings     $100.00 $0.00
Deposit transactions from January 1, 2025 to December 31, 2025
Jan 2, 2025 To Instant Access Savings     $100.00 $100.00
Jan 3, 2025 Net Interest Paid to 'Instant Access Savings' for Jan 3, $10.00 $110.00
2025
\f
USD Statement
Jan 6, 2025 From Instant Access Savings   $20.00 $90.00
"""

RATES = {'2024-12-31': '1', '2025-01-02': '1', '2025-01-03': '1',
         '2025-01-06': '2', '2025-12-31': '2'}
SOURCE = {'provider': 'ECB', 'series': 'EXR.D.USD.EUR.SP00.A', 'url': 'https://data-api.ecb.europa.eu/public',
          'response_sha256': 'synthetic', 'fetched_at': 'now'}


def database(path=':memory:', facts=None):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO documents(content_sha256,byte_size,imported_at,parse_status,processing_profile) VALUES('test',1,'now','parsed','synthetic-demo-v1')")
    if facts is None:
        facts = parse_revolut(USD_STATEMENT, 2025, 'account_statement').facts
    insert_facts(conn, 'test', [asdict(fact) for fact in facts])
    conn.execute('UPDATE account_year_facts SET is_canonical=1')
    conn.commit()
    return conn


def facts(conn):
    return conn.execute('SELECT * FROM account_year_facts ORDER BY id').fetchall()


def forbidden(*args, **kwargs):
    pytest.fail('No exchange-rate download should occur')


def test_usd_parser_retains_dates_and_reconciles_each_product():
    current, deposit = parse_revolut(USD_STATEMENT, 2025, 'account_statement').facts
    assert current.extra['fx_evidence']['reconciled']
    assert deposit.extra['fx_evidence']['reconciled']
    assert len(deposit.extra['fx_evidence']['transactions']) == 3
    assert deposit.extra['fx_evidence']['transactions'][1] == {
        'date': '2025-01-03', 'amount': '10.00', 'direction': 'in', 'kind': 'interest'}


def test_conversion_counts_interest_once_and_internal_transfers_cancel(monkeypatch):
    downloads = []
    monkeypatch.setattr('wr.fx._download_rates', lambda year: (downloads.append(year) or RATES, SOURCE))
    conn = database()
    convert_usd_facts(conn)
    current, deposit = facts(conn)
    assert downloads == [2025]
    assert current['currency'] == deposit['currency'] == 'USD'
    assert deposit['interest_received'] == 10
    assert deposit['end_balance'] == 90
    assert _fact_return(current) == 0
    assert _fact_return(deposit) == -45
    converted = eur_conversion(deposit)
    assert converted['values']['interest_received'] == 10
    assert converted['values']['end_balance'] == 45
    assert converted['fx_gain'] == -55
    assert converted['values']['deposits'] == 100
    assert converted['values']['withdrawals'] == 10
    coverage = _coverage_for_year(conn, 2025)
    assert coverage.coverage_status == 'COMPLETE'
    assert coverage.known_combined_actual_return == -45
    assert coverage.end_balance == 45
    assert coverage.interest_received == 10
    assert _overview_return_totals(facts(conn)) == {'earned': 10, 'currency': -55, 'other': 0, 'effective': -45}


def test_native_income_and_eur_income_are_kept_distinct(monkeypatch):
    monkeypatch.setattr('wr.fx._download_rates', lambda year: ({day: '2' for day in RATES}, SOURCE))
    conn = database()
    convert_usd_facts(conn)
    deposit = facts(conn)[1]
    assert _return_components(deposit) == {'earned': 10, 'currency': 0, 'other': 0, 'effective': 5}
    assert _overview_return_totals(facts(conn))['earned'] == 5


def test_cached_rates_survive_reopen_and_reprocessing_offline(tmp_path, monkeypatch):
    path = tmp_path/'db.sqlite'
    conn = database(path)
    monkeypatch.setattr('wr.fx._download_rates', lambda year: (RATES, SOURCE))
    convert_usd_facts(conn)
    conn.close()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Simulate freshly reparsed source records, while retaining the rate cache.
    insert_facts(conn, 'test', [asdict(f) for f in parse_revolut(USD_STATEMENT, 2025, 'account_statement').facts])
    conn.execute('UPDATE account_year_facts SET is_canonical=1')
    monkeypatch.setattr('wr.fx._download_rates', forbidden)
    convert_usd_facts(conn)
    assert _fact_return(facts(conn)[1]) == -45
    assert conn.execute('SELECT COUNT(*) FROM exchange_rate_cache').fetchone()[0] == 1


@pytest.mark.parametrize('case', ['eur', 'eur_fund', 'gbp', 'unsupported_usd', 'excluded', 'noncanonical'])
def test_download_is_lazy_and_limited_to_supported_required_usd(case, monkeypatch):
    native = AccountYearFact(2025, 'bank', 'cash', 'Cash', interest_received=10, gain_method='interest_only')
    if case == 'eur_fund':
        native.extra = {'fund_currency': 'USD', 'earned_return': 10, 'fx_gain': -5}
    elif case == 'gbp':
        native.currency = 'GBP'
    elif case == 'unsupported_usd':
        native.currency = 'USD'
    if case in {'excluded', 'noncanonical'}:
        conn = database()
        if case == 'excluded':
            for row in facts(conn):
                extra = json.loads(row['extra']); extra['box3'] = False
                conn.execute('UPDATE account_year_facts SET extra=? WHERE id=?', (json.dumps(extra), row['id']))
        else:
            conn.execute('UPDATE account_year_facts SET is_canonical=0')
    else:
        conn = database(facts=[native])
    monkeypatch.setattr('wr.fx._download_rates', forbidden)
    convert_usd_facts(conn)
    assert conn.execute('SELECT COUNT(*) FROM exchange_rate_cache').fetchone()[0] == 0


def test_repeated_conversion_and_read_only_views_make_no_requests(monkeypatch):
    conn = database()
    monkeypatch.setattr('wr.fx._download_rates', lambda year: (RATES, SOURCE))
    convert_usd_facts(conn)
    monkeypatch.setattr('wr.fx._download_rates', forbidden)
    convert_usd_facts(conn)
    _coverage_for_year(conn, 2025)
    _overview_return_totals(facts(conn))
    create_audit_export(conn, [2025])


def test_network_failure_preserves_native_evidence_and_retries_once_per_year(monkeypatch):
    attempts = []
    def fail(year):
        attempts.append(year)
        raise OSError('offline')
    monkeypatch.setattr('wr.fx._download_rates', fail)
    conn = database()
    convert_usd_facts(conn)
    assert attempts == [2025]
    assert _coverage_for_year(conn, 2025).coverage_status == 'PARTIAL'
    assert all(_fact_return(row) is None for row in facts(conn))
    assert facts(conn)[1]['interest_received'] == 10
    assert conn.execute('SELECT COUNT(*) FROM exchange_rate_cache').fetchone()[0] == 0
    monkeypatch.setattr('wr.fx._download_rates', lambda year: (RATES, SOURCE))
    convert_usd_facts(conn)
    assert _fact_return(facts(conn)[1]) == -45


@pytest.mark.parametrize('change', [
    lambda text: text.replace('$110.00\n2025', '$111.00\n2025'),
    lambda text: text.replace('Jan 6, 2025 From', 'Jan 6, 2024 From'),
    lambda text: text.replace('Jan 6, 2025 From', 'Jan 1, 2025 From'),
    lambda text: text.replace('Jan 6, 2025 From Instant Access Savings   $20.00 $90.00', ''),
])
def test_unreconciled_usd_does_not_trigger_download(change, monkeypatch):
    parsed = parse_revolut(change(USD_STATEMENT), 2025, 'account_statement').facts[1]
    conn = database(facts=[parsed])
    monkeypatch.setattr('wr.fx._download_rates', forbidden)
    convert_usd_facts(conn)
    assert _fact_return(facts(conn)[0]) is None


def test_zero_usd_account_needs_no_rates(monkeypatch):
    parsed = parse_revolut('''USD Statement
Account (Current Account) $0.00 $0.00 $0.00 $0.00
Account transactions from January 1, 2025 to December 31, 2025
''', 2025, 'account_statement').facts
    conn = database(facts=parsed)
    monkeypatch.setattr('wr.fx._download_rates', forbidden)
    convert_usd_facts(conn)
    assert _fact_return(facts(conn)[0]) == 0
    assert _coverage_for_year(conn, 2025).coverage_status == 'COMPLETE'


def test_previous_published_rate_never_uses_future_or_stale_observation():
    book = RateBook(RATES, SOURCE)
    assert book.lookup(date(2025, 1, 1)) == (date(2024, 12, 31), Decimal(1))
    assert book.lookup(date(2025, 1, 5)) == (date(2025, 1, 3), Decimal(1))
    with pytest.raises(ConversionUnavailable):
        book.lookup(date(2025, 1, 14))
    with pytest.raises(ConversionUnavailable):
        book.lookup(date(2024, 12, 30))


def test_missing_rates_keep_account_incomplete(monkeypatch):
    monkeypatch.setattr('wr.fx._download_rates', lambda year: ({'2025-01-06': '2'}, SOURCE))
    conn = database()
    convert_usd_facts(conn)
    assert _coverage_for_year(conn, 2025).coverage_status == 'PARTIAL'
    assert conn.execute('SELECT COUNT(*) FROM exchange_rate_cache').fetchone()[0] == 0


def test_changed_source_evidence_invalidates_previous_conversion(monkeypatch):
    monkeypatch.setattr('wr.fx._download_rates', lambda year: (RATES, SOURCE))
    conn = database()
    convert_usd_facts(conn)
    conn.execute("UPDATE account_year_facts SET end_balance=999 WHERE account_key LIKE '%deposit'")
    assert _fact_return(facts(conn)[1]) is None
    monkeypatch.setattr('wr.fx._download_rates', forbidden)
    convert_usd_facts(conn)
    assert _fact_return(facts(conn)[1]) is None
    assert json.loads(facts(conn)[1]['extra'])['fx_status'] == 'requires_eur_conversion'


def test_export_contains_rates_dates_native_and_eur_amounts(monkeypatch):
    monkeypatch.setattr('wr.fx._download_rates', lambda year: (RATES, SOURCE))
    conn = database()
    convert_usd_facts(conn)
    with zipfile.ZipFile(io.BytesIO(create_audit_export(conn, [2025]))) as bundle:
        read = lambda name: list(csv.DictReader(io.StringIO(bundle.read(name).decode('utf-8-sig'))))
        sources = read('source_facts.csv')
        deposit = sources[1]
        assert deposit['currency'] == 'USD'
        assert deposit['end_capital'] == '90.0'
        assert deposit['eur_end_balance'] == '45.0'
        assert deposit['calculated_actual_return'] == '-45.0'
        assert deposit['included_in_year_total'] == 'True'
        audit = read('fx_conversions.csv')
        credit = next(row for row in audit if row['kind'] == 'interest')
        assert credit['date'] == credit['rate_date'] == '2025-01-03'
        assert credit['native_amount'] == '10.00'
        assert credit['usd_per_eur'] == '1'
        assert credit['eur_unrounded'] == '10.00'
        assert credit['response_sha256'] == 'synthetic'


def test_import_and_recompute_integrate_lazy_conversion(tmp_path, monkeypatch):
    from wr.import_pipeline import run_import, recompute
    documents = tmp_path/'documents'
    documents.mkdir()
    (documents/'statement.pdf').write_bytes(b'synthetic')
    monkeypatch.setattr('wr.import_pipeline.extract_text', lambda path: (USD_STATEMENT, 2))
    requests = []
    monkeypatch.setattr('wr.fx._download_rates', lambda year: (requests.append(year) or RATES, SOURCE))
    db_path = tmp_path/'db.sqlite'
    report = run_import(documents, db_path)
    assert report.parsed == 1 and report.failed == 0
    assert requests == [2025]
    monkeypatch.setattr('wr.fx._download_rates', forbidden)
    recompute(db_path)
    report = run_import(documents, db_path)
    assert report.duplicate == 1
    conn = sqlite3.connect(db_path)
    assert conn.execute('SELECT known_combined_actual_return FROM yearly_portfolio').fetchone()[0] == -45


def test_small_daily_interest_is_rounded_only_after_conversion_total(monkeypatch):
    cash = AccountYearFact(2025, 'revolut', 'usd', 'USD cash', currency='USD',
                          start_balance=0, end_balance=1.03, deposits=1, withdrawals=0,
                          interest_received=.03, capital_gain=.03, gain_method='interest_only',
                          extra={'fx_evidence': {'reconciled': True, 'transactions': [
                              {'date': '2025-01-02', 'amount': '1.00', 'direction': 'in', 'kind': 'transfer'},
                              *[{'date': f'2025-01-0{day}', 'amount': '0.01', 'direction': 'in', 'kind': 'interest'} for day in (3, 4, 5)]
                          ]}})
    monkeypatch.setattr('wr.fx._download_rates', lambda year: ({day: '3' for day in RATES}, SOURCE))
    conn = database(facts=[cash])
    convert_usd_facts(conn)
    converted = eur_conversion(facts(conn)[0])
    assert converted['values']['interest_received'] == .01
    assert converted['effective_return'] == .01
    assert converted['fx_gain'] == 0


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '0', '-1', 'garbage'])
def test_invalid_reference_rates_are_rejected(value):
    with pytest.raises(ConversionUnavailable):
        RateBook({'2025-01-02': value}, SOURCE)


def test_ecb_request_contains_only_public_series_and_dates(monkeypatch):
    from wr.fx import _download_rates
    response_body = ('KEY,CURRENCY,CURRENCY_DENOM,TIME_PERIOD,OBS_VALUE\n'
                     'EXR.D.USD.EUR.SP00.A,USD,EUR,2024-12-31,1.0389\n'
                     'EXR.D.USD.EUR.SP00.A,USD,EUR,2025-12-31,1.175\n').encode()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return response_body
    requests = []
    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', open_request)
    rates, source = _download_rates(2025)
    request, timeout = requests[0]
    assert request.data is None and request.get_method() == 'GET'
    assert request.full_url == ('https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A'
                                '?startPeriod=2024-12-22&endPeriod=2025-12-31&format=csvdata')
    assert timeout == 10
    assert rates['2024-12-31'] == '1.0389'
    assert source['url'] == request.full_url
    assert len(source['response_sha256']) == 64


def test_incomplete_year_is_not_requested(monkeypatch):
    from wr.fx import _download_rates
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    with pytest.raises(ConversionUnavailable, match='completed tax year'):
        _download_rates(2100)
