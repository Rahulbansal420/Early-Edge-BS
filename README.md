# EARLY EDGE V6 — FIXED DEPLOYMENT

This package fixes the Streamlit Cloud error `ModuleNotFoundError: src.nse_client`.

## Fix
All Python modules are now in the repository root and `app.py` imports them directly. There is no `src` package dependency.

## Streamlit Cloud
- Branch: `main`
- Main file: `app.py`
- Python dependencies: `requirements.txt`

## Features
NSE public announcements, filing attachment parsing, event classification, 0–100 Edge Score, optional market confirmation, SQLite persistence and Telegram alerts.

No dummy market/news fallback is used.
