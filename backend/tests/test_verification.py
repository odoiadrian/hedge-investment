import copy
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import verification
from backend.mcp_msft import sources


@pytest.fixture
def baseline(monkeypatch, tmp_path):
    prices = pd.DataFrame({'MSFT': np.linspace(100, 140, 140)}, index=pd.bdate_range(end='2026-10-22', periods=140))
    prices.to_csv(tmp_path / 'prices.csv', index_label='date')
    (tmp_path / 'meta.json').write_text('{"mode":"REAL"}')
    monkeypatch.setattr(verification, 'data_directory', lambda: tmp_path)
    request = verification.VerificationRequest(baseline_as_of='2026-10-22', data_mode='REAL')
    evidence = dict(asset_id='MSFT', retrieved_at='2026-10-23T12:00:00+00:00', market=sources.price_summary(prices.MSFT), news=[], warnings=[])
    return request, evidence, tmp_path


def test_comparison_is_read_only_and_consistency_has_limited_scope(baseline):
    request, evidence, path = baseline
    before = (path / 'prices.csv').read_bytes()
    result = verification.compare_evidence(request, evidence)
    assert result['checks'][0]['status'] == 'consistent'
    assert result['checks'][-1]['status'] == 'unverified'
    assert result['portfolio_changed'] is False
    assert (path / 'prices.csv').read_bytes() == before


@pytest.mark.parametrize('change', ['price', 'volatility', 'trend', 'older'])
def test_material_changes_or_older_observations_never_verify_the_rationale(baseline, change):
    request, evidence, _ = baseline
    if change == 'price': evidence['market']['price'] *= 1.02
    if change == 'volatility': evidence['market']['volatility_pct'] += 4
    if change == 'trend': evidence['market']['momentum_pct'] = -5
    if change == 'older': evidence['market']['as_of'] = '2026-10-21'
    result = verification.compare_evidence(request, evidence)
    assert result['checks'][0]['status'] in ('review', 'unverified')
    assert result['assessment'].startswith('Review required')


def test_synthetic_profile_has_no_real_baseline_comparison(baseline):
    request, evidence, _ = baseline
    request.data_mode = 'SYNTHETIC'
    result = verification.compare_evidence(request, evidence)
    assert result['baseline'] is None
    assert result['checks'][0]['status'] == 'unverified'


def test_complete_outage_is_not_reported_as_success(baseline):
    request, evidence, _ = baseline
    evidence['market'] = None
    with pytest.raises(verification.VerificationUnavailable):
        verification.compare_evidence(request, evidence)


def test_news_only_is_partial_and_market_comparison_unverified(baseline):
    request, evidence, _ = baseline
    evidence['market'] = None
    evidence['news'] = [{'title': 'Company announcement', 'url': sources.NEWS_URL, 'published': 'Today'}]
    assert verification.compare_evidence(request, evidence)['checks'][0]['status'] == 'unverified'


def test_http_failure_is_contained_and_does_not_disclose_provider_details(monkeypatch):
    async def fail(): raise RuntimeError('private provider details')
    monkeypatch.setattr(verification, 'call_microsoft_tool', fail)
    client = TestClient(app)
    response = client.post('/api/holdings/MSFT/update', json={'baseline_as_of': '2026-10-23', 'data_mode': 'REAL'})
    assert response.status_code == 503
    assert response.headers['cache-control'] == 'no-store'
    assert 'private' not in response.text
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert client.post('/api/holdings/AAPL/update', json={}).status_code == 404


def test_http_success_preserves_budget_outside_response(monkeypatch, baseline):
    _, evidence, _ = baseline
    async def fetch(): return copy.deepcopy(evidence)
    monkeypatch.setattr(verification, 'call_microsoft_tool', fetch)
    response = TestClient(app).post('/api/holdings/MSFT/update', json={'baseline_as_of': '2026-10-22', 'data_mode': 'REAL'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['connection'] == 'connected'
    assert 'allocations' not in response.json()


def test_news_links_are_limited_to_microsoft(monkeypatch):
    response = Mock(content=b'''<rss><channel><item><title>Official</title><link>https://news.microsoft.com/source/test/</link></item><item><title>Bad</title><link>javascript:alert(1)</link></item><item><title>Wrong host</title><link>https://news.microsoft.com.evil.test/</link></item></channel></rss>''')
    monkeypatch.setattr(sources.requests, 'get', lambda *a, **k: response)
    assert [item['title'] for item in sources.company_news()] == ['Official']


def test_invalid_prices_cannot_produce_nan_metrics():
    with pytest.raises(ValueError): sources.price_summary(pd.Series([1., 2.]))
    with pytest.raises(ValueError): sources.price_summary(pd.Series([np.inf] * 150))


def earnings_event():
    return dict(kind='earnings', event_date='2026-10-28', timing='After market close',
                title='FY2027 first-quarter results', published='2026-10-07', url=sources.EARNINGS_URL)


def test_verified_earnings_event_creates_action_without_fabricating_allocation_change(baseline):
    request, evidence, path = baseline
    evidence['events'] = [earnings_event()]
    (path / 'next_earnings.csv').write_text('asset,next_earnings_date\nMSFT,2026-10-28\n')
    result = verification.compare_evidence(request, evidence)
    assert result['assessment'] == 'Action needed: Microsoft earnings in 5 days'
    flag = result['action_flags'][0]
    assert '4-week' in flag['finding']
    assert 'already contains' in flag['baseline_note']
    assert 'before funding' in flag['action']
    assert result['portfolio_changed'] is False


@pytest.mark.parametrize('event_date', ['2026-10-22', '2026-12-01'])
def test_expired_or_out_of_horizon_event_does_not_force_a_demo_flag(baseline, event_date):
    request, evidence, _ = baseline
    evidence['events'] = [{**earnings_event(), 'event_date': event_date}]
    assert verification.compare_evidence(request, evidence)['action_flags'] == []


def test_client_horizon_is_used_for_event_review(baseline):
    request, evidence, _ = baseline
    request.horizon_weeks = 1
    evidence['events'] = [{**earnings_event(), 'event_date': '2026-11-02'}]
    assert verification.compare_evidence(request, evidence)['action_flags'] == []


def test_earnings_date_is_parsed_from_live_source_not_invented(monkeypatch):
    response = Mock(content=b'valid HTML', text='<p>Microsoft Corp. will publish fiscal year 2027 first-quarter financial results after the close of the market on Wednesday, Oct. 28, 2026, on its website.</p>')
    monkeypatch.setattr(sources.requests, 'get', lambda *a, **k: response)
    assert sources.company_events()[0]['event_date'] == '2026-10-28'
    response.text = '<html>Source unavailable or announcement removed</html>'
    with pytest.raises(ValueError): sources.company_events()


def test_event_only_response_is_useful_even_when_price_and_rss_fail(baseline):
    request, evidence, _ = baseline
    evidence['market'] = None
    evidence['events'] = [earnings_event()]
    assert verification.compare_evidence(request, evidence)['action_flags']
