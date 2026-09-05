import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup

BASE = "https://www.nseindia.com"
API = BASE + "/api/corporate-announcements?index=equities"
RSS_PAGE = BASE + "/static/rss-feed"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": BASE + "/",
    "Accept-Language": "en-US,en;q=0.9",
}

def _session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(BASE, timeout=15)
    return s

def _get_json(s, url):
    r = s.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

def _pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return ""

def fetch_announcements(days: int = 2) -> List[Dict[str, Any]]:
    """Fetch public NSE corporate announcements. Returns [] if NSE throttles/blocks."""
    s = _session()
    try:
        data = _get_json(s, API)
    except Exception:
        return []

    if not isinstance(data, list):
        data = data.get("data", []) if isinstance(data, dict) else []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for d in data:
        symbol = _pick(d, "symbol", "symbolCode", "Symbol")
        subject = _pick(d, "subject", "desc", "Subject")
        details = _pick(d, "details", "description", "Details")
        attachment = _pick(d, "attchmntFile", "attachment", "Attachment", "fileUrl")
        ts = _pick(d, "broadcastDateTime", "broadcastDate", "Broadcast Date", "timestamp")
        if not symbol and not subject:
            continue
        out.append({
            "symbol": str(symbol).strip(),
            "subject": str(subject).strip(),
            "details": BeautifulSoup(str(details), "html.parser").get_text(" ", strip=True),
            "attachment": str(attachment).strip(),
            "published": str(ts).strip(),
            "source": "NSE Corporate Announcements",
            "source_url": BASE + "/companies-listing/corporate-filings-announcements",
        })
    return out
