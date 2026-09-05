import io
import re
import requests

from bs4 import BeautifulSoup

MONEY = re.compile(r"(?i)(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(crore|cr|lakh|lac|million|billion)?")
PCT = re.compile(r"(?<!\w)(\d+(?:\.\d+)?)\s*%")
EVENTS = [
    ("FUNDRAISE/DILUTION", ["preferential", "qip", "rights issue", "fund raising", "fundraising", "warrants", "allotment"]),
    ("M&A", ["acquisition", "acquire", "merger", "amalgamation", "joint venture", "jv"]),
    ("ORDER", ["order", "contract", "bagging", "work order", "purchase order"]),
    ("APPROVAL", ["approval", "approved", "license", "clearance", "regulatory approval"]),
    ("PROMOTER/INSIDER", ["promoter", "insider", "disclosure under regulation 29", "pledge"]),
    ("MANAGEMENT", ["resignation", "appointment", "director", "key managerial", "auditor"]),
    ("CAPEX", ["capex", "capital expenditure", "new plant", "expansion", "capacity"]),
    ("RESULTS", ["financial results", "results", "revenue", "ebitda", "profit"]),
    ("REGULATORY", ["penalty", "show cause", "sebi", "order passed", "litigation", "fraud"]),
]

def classify(text: str) -> str:
    t = text.lower()
    for label, words in EVENTS:
        if any(w in t for w in words):
            return label
    return "GENERAL"

def extract_figures(text: str):
    figures = []
    for m in MONEY.finditer(text):
        figures.append({"value": m.group(1), "unit": m.group(2) or "", "text": m.group(0)})
    for m in PCT.finditer(text):
        figures.append({"percent": m.group(1), "text": m.group(0)})
    return figures[:30]

def fetch_attachment(url: str):
    if not url or not url.startswith("http"):
        return ""
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        ct = r.headers.get("content-type","").lower()
        if "pdf" in ct or url.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(r.content))
                return "\n".join((p.extract_text() or "") for p in reader.pages[:20])
            except Exception:
                return ""
        return BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    except Exception:
        return ""

def enrich_event(e):
    text = f"{e.get('subject','')} {e.get('details','')}"
    attachment_text = fetch_attachment(e.get("attachment",""))
    combined = f"{text}\n{attachment_text}".strip()
    e["event_type"] = classify(combined)
    e["financial_figures"] = extract_figures(combined)
    e["materiality"] = "UNKNOWN"
    e["parsed_attachment_chars"] = len(attachment_text)
    return e
