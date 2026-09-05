def score_event(e):
    et = e.get("event_type","GENERAL")
    subject = (e.get("subject","") + " " + e.get("details","")).lower()
    base = {
        "M&A": 88, "FUNDRAISE/DILUTION": 82, "ORDER": 78, "APPROVAL": 74,
        "CAPEX": 70, "PROMOTER/INSIDER": 68, "REGULATORY": 64,
        "RESULTS": 62, "MANAGEMENT": 58, "GENERAL": 25
    }.get(et, 25)

    materiality = 0
    if any(x in subject for x in ["material", "significant", "landmark", "largest", "record"]):
        materiality += 7
    if e.get("financial_figures"):
        materiality += 5
    if e.get("parsed_attachment_chars", 0) > 1000:
        materiality += 3

    surprise = 5 if any(x in subject for x in ["unexpected", "strategic", "new", "first", "won"]) else 0

    total = max(0, min(100, base + materiality + surprise))
    return {
        "base_event": base,
        "materiality": materiality,
        "surprise": surprise,
        "price_confirmation": 0,
        "volume_confirmation": 0,
        "relative_strength": 0,
        "total": total
    }
