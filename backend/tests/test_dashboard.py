import math
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import llm, pipeline
from backend.app.main import app
from backend.app.models import ClientProfile, PortfolioDashboard

client = TestClient(app)
PROFILE = dict(reference=' Demo client ', horizon_weeks=4, risk_appetite=3,
               max_loss_pct=8, max_single_holding_pct=20, min_cash_pct=5)
REAL_INTERPRET = llm.interpret_preferences


def preferences(**changes):
    return llm.Preferences(**dict(dict(excluded_assets=[], limits=[], summary='Explicit client rules.', unresolved=[], notes=[]), **changes))


@pytest.fixture(scope='session')
def synthetic_data(tmp_path_factory):
    directory = tmp_path_factory.mktemp('synthetic')
    subprocess.run([sys.executable, '-m', 'backend.analyst.fetch_data', '--synthetic', '--out', str(directory), '--no-excel'], check=True, capture_output=True)
    return directory


@pytest.fixture(autouse=True)
def offline(monkeypatch, synthetic_data):
    monkeypatch.setenv('ANALYST_DATA_DIR', str(synthetic_data))
    monkeypatch.setattr(llm, 'interpret_preferences', lambda p: (preferences(), 0))
    def no_explanation(*args):
        raise llm.AnalystUnavailable('Test provider unavailable')
    monkeypatch.setattr(llm, 'explain', no_explanation)


@pytest.mark.parametrize('changes', [
    {'reference': '  '}, {'age': -1}, {'age': 40.5}, {'age': True},
    {'horizon_weeks': 0}, {'horizon_weeks': 27}, {'horizon_weeks': '4'},
    {'risk_appetite': 6}, {'risk_appetite': True}, {'max_loss_pct': 0},
    {'max_single_holding_pct': 101}, {'min_cash_pct': -1},
    {'values': 'x' * 3001}, {'budget_cents': 1}, {'objective': 'guaranteed'},
])
def test_invalid_profile_is_rejected(changes):
    assert client.post('/api/recommendations', json={**PROFILE, **changes}).status_code == 422


def test_three_portfolios_honour_rules_and_fallback_explanations(monkeypatch):
    monkeypatch.setattr(llm, 'interpret_preferences', lambda p: (preferences(excluded_assets=['WTI', 'NATGAS']), 10))
    response = client.post('/api/recommendations', json=PROFILE)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    data = response.json()
    assert data['status'] == 'ready'
    assert data['client_reference'] == 'Demo client'
    assert data['data_mode'] == 'SYNTHETIC'
    assert data['ai_status'] == 'unavailable'
    assert data['recommended_option'] == 'B'
    assert {o['id'] for o in data['options']} == {'A', 'B', 'C'}
    for option in data['options']:
        positions = {a['asset_id']: a['amount_cents'] for a in option['allocations']}
        assert sum(positions.values()) == 10_000_000
        assert not set(positions) & {'WTI', 'NATGAS', 'TOKEN_RE'}
        assert positions['CASH'] >= 500_000 - 1
        assert all(v <= 2_000_001 for a, v in positions.items() if a != 'CASH')
        assert option['metrics']['vol_annualised_pct'] <= 12.02
        assert option['metrics']['loss_1_in_20_pct'] >= -8.02
        assert all(a['financial_reason'] and a['client_reason'] and a['evidence'] for a in option['allocations'])
    data['options'][0]['allocations'][0]['amount_cents'] -= 1
    with pytest.raises(ValidationError, match='entire budget'):
        PortfolioDashboard(**data)


def test_unverifiable_ethics_requires_clarification_without_optimising(monkeypatch):
    monkeypatch.setattr(llm, 'interpret_preferences', lambda p: (preferences(unresolved=['Which explicit sectors should be excluded?']), 20))
    monkeypatch.setattr(pipeline.optimizer, 'recommend', lambda *a, **k: pytest.fail('Must clarify before solving'))
    data = client.post('/api/recommendations', json={**PROFILE, 'values': 'Only ethical companies'}).json()
    assert data['status'] == 'needs_clarification'
    assert data['options'] == []
    assert data['questions']


def test_conflicting_constraints_are_not_silently_relaxed(monkeypatch):
    limits = [llm.Limit(kind='class', key='bonds', minimum_pct=10, maximum_pct=None)]
    monkeypatch.setattr(llm, 'interpret_preferences', lambda p: (preferences(excluded_assets=['UST10'], limits=limits), 0))
    data = client.post('/api/recommendations', json=PROFILE).json()
    assert data['status'] == 'infeasible'
    assert data['options'] == []
    assert data['questions']


def test_extraction_outage_does_not_ignore_client_preferences(monkeypatch):
    def unavailable(*args):
        raise llm.AnalystUnavailable('The event AI service is unavailable.')
    monkeypatch.setattr(llm, 'interpret_preferences', unavailable)
    response = client.post('/api/recommendations', json={**PROFILE, 'exclusions': 'No oil'})
    assert response.status_code == 503
    assert response.headers['cache-control'] == 'no-store'
    assert 'options' not in response.json()


def test_missing_market_dataset_never_silently_uses_synthetic(monkeypatch, tmp_path):
    monkeypatch.setenv('ANALYST_DATA_DIR', str(tmp_path))
    assert client.post('/api/recommendations', json=PROFILE).status_code == 503


def test_credentials_never_leave_backend(monkeypatch):
    for field in ('ENDPOINT', 'API_KEY', 'DEPLOYMENT'):
        monkeypatch.setenv(f'AZURE_OPENAI_{field}', f'private-{field}')
    response = client.get('/api/status')
    assert 'private-' not in response.text
    assert response.json()['credential_fields_present'] is True
    assert response.json()['event_api'] == 'configured'


def test_largest_remainder_retains_budget_and_rejects_invalid_weights():
    assert sum(pipeline.cents_for_holdings([{'weight': 1 / 3}] * 3)) == 10_000_000
    for weights in ([math.nan], [math.inf], [-1, 2], [.2, .2]):
        with pytest.raises(pipeline.DataUnavailable):
            pipeline.cents_for_holdings([{'weight': w} for w in weights])


def test_invalid_ai_limits_and_placeholder_require_clarification():
    for limit in [llm.Limit(kind='asset', key='AAPL', minimum_pct=10, maximum_pct=None),
                  llm.Limit(kind='asset', key='MSFT', minimum_pct=90, maximum_pct=20),
                  llm.Limit(kind='asset', key='TOKEN_RE', minimum_pct=1, maximum_pct=None)]:
        _, questions = pipeline.build_rules(ClientProfile(**PROFILE), preferences(limits=[limit]))
        assert questions


def test_preference_payload_omits_reference_and_age(monkeypatch):
    # Use the real extraction boundary while replacing only the network call.
    captured = {}
    def capture(schema, system, payload):
        captured.update(payload)
        return preferences(), 0
    monkeypatch.setattr(llm, 'structured_call', capture)
    REAL_INTERPRET(ClientProfile(**PROFILE, age=42, values='No technology'))
    assert 'reference' not in captured['explicit_rules']
    assert 'age' not in captured['explicit_rules']
    assert 'Demo client' not in str(captured)
