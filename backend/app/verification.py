"""Independent evidence refresh; never writes datasets or changes portfolio weights."""
from datetime import date, datetime, timedelta
import json
import sys

import anyio
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from .config import ROOT
from .pipeline import data_directory
from ..mcp_msft.sources import price_summary


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    baseline_as_of: date
    data_mode: Literal['REAL', 'SYNTHETIC']
    horizon_weeks: int = Field(default=4, ge=1, le=26, strict=True)


class VerificationUnavailable(Exception):
    pass


async def call_microsoft_tool():
    # Lazy import keeps the existing application runnable if the optional SDK is absent.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=['-m', 'backend.mcp_msft.server'],
                                   cwd=str(ROOT), env={'PYTHONIOENCODING': 'utf-8'})
    with anyio.fail_after(55):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                if 'refresh_microsoft' not in {t.name for t in tools.tools}:
                    raise VerificationUnavailable('Microsoft MCP tool is unavailable.')
                response = await session.call_tool('refresh_microsoft', {})
                if response.isError:
                    raise VerificationUnavailable('Microsoft MCP refresh failed.')
                return response.structuredContent or json.loads(response.content[0].text)


def compare_evidence(request, evidence):
    if evidence.get('asset_id') != 'MSFT' or not evidence.get('retrieved_at'):
        raise VerificationUnavailable('Invalid Microsoft MCP response.')
    if evidence.get('market') is None and not evidence.get('news') and not evidence.get('events'):
        raise VerificationUnavailable('Live sources are unavailable. The original portfolio is unchanged.')
    baseline = None
    try:
        meta = json.loads((data_directory() / 'meta.json').read_text())
        prices = pd.read_csv(data_directory() / 'prices.csv', index_col='date', parse_dates=True)
        if request.data_mode == meta.get('mode') == 'REAL' and prices.index[-1].date() == request.baseline_as_of:
            baseline = price_summary(prices['MSFT'])
    except (OSError, ValueError, KeyError, IndexError):
        pass
    current = evidence.get('market')
    checks = []
    if current and baseline and current['as_of'] >= baseline['as_of']:
        price_change = (current['price'] / baseline['price'] - 1) * 100
        vol_change = current['volatility_pct'] - baseline['volatility_pct']
        trend_changed = (current['momentum_pct'] >= 0) != (baseline['momentum_pct'] >= 0)
        changed = abs(price_change) >= 1 or abs(vol_change) >= 3 or trend_changed
        checks.append(dict(status='review' if changed else 'consistent', title='Market inputs compared',
                           detail=f'Adjusted daily price changed {price_change:+.2f}%; observed annualised volatility changed {vol_change:+.2f} percentage points. The 120-session momentum direction {"changed" if trend_changed else "is unchanged"}.'))
    else:
        changed = True
        checks.append(dict(status='unverified', title='Market comparison incomplete', detail='No comparable real baseline or newer market observation is available. A connection alone does not verify the investment rationale.'))
    checks.append(dict(status='review', title='Company announcements', detail='Review the dated Microsoft announcements below for new developments. Headlines are evidence to review, not an automated endorsement.' if evidence.get('news') else 'Microsoft announcements could not be retrieved.'))
    checks.append(dict(status='unverified', title='Return estimates and client fit', detail='The CAPM, event and implied-volatility assumptions and client alignment have not been revalidated. Rebuild the portfolio after refreshing the full dataset to recalculate allocations and risk.'))
    action_flags = earnings_flags(request, evidence)
    if action_flags:
        assessment = action_flags[0]['title']
    else:
        assessment = 'Review required: market inputs changed or comparison is incomplete.' if changed else 'Observed market inputs are consistent within the demo review thresholds. Review the company announcements and remaining assumptions.'
    return dict(**evidence, baseline=baseline, checks=checks, connection='connected',
                assessment=assessment, action_flags=action_flags,
                methodology='Review thresholds: one percent price change, three percentage points of historical volatility, or a change in momentum direction. These are demo rules, not statistical validation.',
                portfolio_changed=False)


def earnings_flags(request, evidence):
    today = datetime.fromisoformat(evidence['retrieved_at'].replace('Z', '+00:00')).date()
    end = today + timedelta(weeks=request.horizon_weeks)
    flags = []
    cached_date = None
    try:
        cached = pd.read_csv(data_directory() / 'next_earnings.csv')
        cached_date = str(cached.loc[cached.asset == 'MSFT', 'next_earnings_date'].iloc[0])
    except (OSError, ValueError, KeyError, IndexError):
        pass
    for event in evidence.get('events', []):
        event_date = date.fromisoformat(event['event_date'])
        # No permanent demo flag: expired or out-of-horizon events do not trigger it.
        if event.get('kind') != 'earnings' or not today <= event_date <= end:
            continue
        days = (event_date - today).days
        known = request.data_mode == 'REAL' and cached_date == event['event_date']
        flags.append(dict(title=f'Action needed: Microsoft earnings in {days} days' if days else 'Action needed: Microsoft earnings today',
                          event_date=event['event_date'], timing=event['timing'], published=event['published'], source_url=event['url'],
                          finding=f'Microsoft confirms {event["title"]} on {event_date.strftime("%d %B %Y")}, {event["timing"].lower()}. This falls inside the client’s {request.horizon_weeks}-week investment horizon.',
                          implication='The entry decision crosses an imminent results announcement. Review earnings-event exposure before treating the proposed allocation as ready to fund.',
                          action='Change the execution plan: require an earnings-risk review before funding Microsoft, and refresh the allocation inputs after results are published.',
                          baseline_note='The cached dataset already contains this earnings date. MCP independently confirms the event and makes the execution review explicit; this is not newly discovered information.' if known else 'This event has not been confirmed against the portfolio’s cached earnings calendar. Review and refresh that calendar before funding.',
                          allocation_note='No numeric position reduction is inferred from a scheduled event alone. The proposed allocation is unchanged.'))
    return flags


async def verify_microsoft(request):
    try:
        evidence = await call_microsoft_tool()
        return compare_evidence(request, evidence)
    except VerificationUnavailable:
        raise
    except Exception as exc:
        raise VerificationUnavailable('Microsoft update is unavailable. The original portfolio is unchanged; please try again.') from exc
