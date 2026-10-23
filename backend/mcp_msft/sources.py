"""Fixed public sources only. No client information or credentials are transmitted."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse
from html.parser import HTMLParser
import math
import re
import xml.etree.ElementTree as ET

import numpy as np
import requests
import yfinance as yf

NEWS_URL = 'https://news.microsoft.com/source/feed/'
PRICE_URL = 'https://finance.yahoo.com/quote/MSFT/'
USER_AGENT = 'HedgeHog/1.0 research demo (https://github.com/odoiadrian/hedge-investment)'
EARNINGS_URL = 'https://news.microsoft.com/source/2026/10/07/microsoft-announces-quarterly-earnings-release-date-69/'


class AnnouncementText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def company_events():
    """Demo source is pinned; the event must be verified from its live contents."""
    response = requests.get(EARNINGS_URL, headers={'User-Agent': USER_AGENT}, timeout=15)
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError('Oversized earnings announcement')
    parser = AnnouncementText()
    parser.feed(response.text)
    text = ' '.join(' '.join(parser.parts).split())
    match = re.search(r'will publish fiscal year (\d{4}) (first|second|third|fourth)-quarter financial results after the close of the market on \w+, ([A-Za-z]+)\.? (\d{1,2}), (\d{4})', text)
    if not match:
        raise ValueError('Could not verify the earnings date from Microsoft')
    fiscal_year, quarter, month, day, year = match.groups()
    event_date = datetime.strptime(f'{month[:3]} {day} {year}', '%b %d %Y').date()
    return [dict(kind='earnings', event_date=event_date.isoformat(), timing='After market close',
                 title=f'FY{fiscal_year} {quarter}-quarter results', published='2026-10-07',
                 url=EARNINGS_URL, source='Microsoft company announcement')]


def price_summary(close):
    close = close.dropna().astype(float)
    if len(close) < 121 or not np.isfinite(close).all() or (close <= 0).any():
        raise ValueError('Insufficient valid price history')
    log_returns = np.log(close / close.shift(1)).dropna().tail(120)
    values = dict(price=float(close.iloc[-1]), momentum_pct=float((close.iloc[-1] / close.iloc[-121] - 1) * 100),
                  volatility_pct=float(log_returns.std() * math.sqrt(252) * 100))
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError('Invalid price summary')
    return {**{k: round(v, 4) for k, v in values.items()}, 'as_of': str(close.index[-1].date())}


def market_data():
    history = yf.Ticker('MSFT').history(period='1y', auto_adjust=True, timeout=15)
    return {**price_summary(history['Close']), 'source': PRICE_URL,
            'observation': 'Latest available adjusted daily price in USD; may be delayed or include an unfinished session.'}


def company_news():
    response = requests.get(NEWS_URL, headers={'User-Agent': USER_AGENT}, timeout=15)
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError('Oversized news response')
    root = ET.fromstring(response.content)
    news = []
    for item in root.findall('./channel/item')[:5]:
        link = item.findtext('link', '')
        if urlparse(link).scheme == 'https' and urlparse(link).hostname == 'news.microsoft.com':
            news.append(dict(title=item.findtext('title', '')[:500], published=item.findtext('pubDate', '')[:100], url=link))
    if not news:
        raise ValueError('No valid Microsoft news items')
    return news


def fetch_update():
    result = dict(asset_id='MSFT', retrieved_at=datetime.now(timezone.utc).isoformat(), market=None, news=[], events=[], warnings=[])
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [(pool.submit(market_data), 'market'), (pool.submit(company_news), 'news'), (pool.submit(company_events), 'events')]
        for job, key in jobs:
            try:
                result[key] = job.result()
            except Exception:
                label = {'market': 'Market prices', 'news': 'Microsoft company news', 'events': 'Microsoft earnings announcement'}[key]
                result['warnings'].append(f'{label} could not be refreshed. Try again later.')
    result['retrieved_at'] = datetime.now(timezone.utc).isoformat()
    return result
