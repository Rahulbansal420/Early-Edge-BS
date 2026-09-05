import io, json, hashlib, sqlite3, re
from pathlib import Path
from datetime import datetime, timedelta, timezone
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup

NSE_HOME="https://www.nseindia.com"
NSE_API=NSE_HOME+"/api/corporate-announcements?index=equities"
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
         "Accept":"application/json,text/plain,*/*","Referer":NSE_HOME+"/",
         "Accept-Language":"en-US,en;q=0.9"}

EVENTS=[
("FUNDRAISE/DILUTION",["preferential","qip","rights issue","fund raising","fundraising","warrants","allotment"]),
("M&A",["acquisition","acquire","merger","amalgamation","joint venture","jv"]),
("ORDER",["order","contract","bagging","work order","purchase order"]),
("APPROVAL",["approval","approved","license","clearance","regulatory approval"]),
("PROMOTER/INSIDER",["promoter","insider","regulation 29","pledge"]),
("MANAGEMENT",["resignation","appointment","director","key managerial","auditor"]),
("CAPEX",["capex","capital expenditure","new plant","expansion","capacity"]),
("RESULTS",["financial results","results","revenue","ebitda","profit"]),
("REGULATORY",["penalty","show cause","sebi","order passed","litigation","fraud"])]
BASE={"M&A":88,"FUNDRAISE/DILUTION":82,"ORDER":78,"APPROVAL":74,"CAPEX":70,
      "PROMOTER/INSIDER":68,"REGULATORY":64,"RESULTS":62,"MANAGEMENT":58,"GENERAL":25}
MONEY=re.compile(r"(?i)(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(crore|cr|lakh|lac|million|billion)?")
PCT=re.compile(r"(?<!\w)(\d+(?:\.\d+)?)\s*%")

def session():
    s=requests.Session(); s.headers.update(HEADERS)
    try: s.get(NSE_HOME,timeout=15)
    except Exception: pass
    return s

def scan_nse():
    try:
        r=session().get(NSE_API,timeout=20); r.raise_for_status()
        data=r.json()
        if isinstance(data,dict): data=data.get("data",[])
    except Exception as ex:
        return [], f"NSE request unavailable/rate-limited: {type(ex).__name__}"
    out=[]
    for d in data if isinstance(data,list) else []:
        def pick(*keys):
            for k in keys:
                if d.get(k) not in (None,""): return d[k]
            return ""
        subject=str(pick("subject","desc","Subject")).strip()
        symbol=str(pick("symbol","symbolCode","Symbol")).strip()
        details=BeautifulSoup(str(pick("details","description","Details")),"html.parser").get_text(" ",strip=True)
        attachment=str(pick("attchmntFile","attachment","Attachment","fileUrl")).strip()
        published=str(pick("broadcastDateTime","broadcastDate","Broadcast Date","timestamp")).strip()
        if symbol or subject:
            out.append({"symbol":symbol,"subject":subject,"details":details,"attachment":attachment,
                        "published":published,"source":"NSE Corporate Announcements",
                        "source_url":NSE_HOME+"/companies-listing/corporate-filings-announcements"})
    return out,None

def parse_attachment(url):
    if not url or not url.startswith("http"): return ""
    try:
        r=requests.get(url,headers={"User-Agent":HEADERS["User-Agent"]},timeout=20); r.raise_for_status()
        if "pdf" in r.headers.get("content-type","").lower() or url.lower().endswith(".pdf"):
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(r.content))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:20])
        return BeautifulSoup(r.text,"html.parser").get_text(" ",strip=True)
    except Exception: return ""

def classify(text):
    t=text.lower()
    for label,words in EVENTS:
        if any(w in t for w in words): return label
    return "GENERAL"

def extract_figures(text):
    a=[{"value":m.group(1),"unit":m.group(2) or "","text":m.group(0)} for m in MONEY.finditer(text)]
    a += [{"percent":m.group(1),"text":m.group(0)} for m in PCT.finditer(text)]
    return a[:30]

def load_market():
    frames=[]
    for p in sorted(Path("market_data").glob("*.csv")):
        try:
            x=pd.read_csv(p)
            if {"timestamp","symbol","close","volume"}.issubset(x.columns):
                x["timestamp"]=pd.to_datetime(x["timestamp"],errors="coerce")
                x["close"]=pd.to_numeric(x["close"],errors="coerce")
                x["volume"]=pd.to_numeric(x["volume"],errors="coerce")
                frames.append(x.dropna(subset=["timestamp","symbol","close"]))
        except Exception: pass
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()

def confirm(symbol,market,event_time):
    if market.empty: return {"price_confirmation":"UNCONFIRMED","volume_confirmation":"UNCONFIRMED",
                             "price_points":0,"volume_points":0,"relative_strength_points":0}
    x=market[market.symbol.astype(str).eq(str(symbol))].sort_values("timestamp")
    t=pd.to_datetime(event_time,errors="coerce")
    if pd.notna(t): x=x[x.timestamp<=t]
    if len(x)<21: return {"price_confirmation":"UNCONFIRMED","volume_confirmation":"UNCONFIRMED",
                          "price_points":0,"volume_points":0,"relative_strength_points":0}
    last=x.iloc[-1]; hist=x.iloc[-21:-1]
    br=bool(last.close>hist.close.max()); vr=bool(last.volume>hist.volume.mean()*1.5)
    rs=4 if len(x)>=61 and last.close/x.iloc[-21].close>1 and last.close/x.iloc[-61].close>1 else 0
    return {"price_confirmation":"CONFIRMED" if br else "UNCONFIRMED",
            "volume_confirmation":"CONFIRMED" if vr else "UNCONFIRMED",
            "price_points":6 if br else 0,"volume_points":5 if vr else 0,
            "relative_strength_points":rs}

def score_event(e,mc):
    text=(e["subject"]+" "+e["details"]).lower(); et=e["event_type"]
    base=BASE.get(et,25)
    mat=(7 if any(x in text for x in ["material","significant","landmark","largest","record"]) else 0)
    mat += 5 if e["financial_figures"] else 0
    mat += 3 if e["parsed_attachment_chars"]>1000 else 0
    surprise=5 if any(x in text for x in ["unexpected","strategic","new","first","won"]) else 0
    total=max(0,min(100,base+mat+surprise+mc["price_points"]+mc["volume_points"]+mc["relative_strength_points"]))
    return {"base_event":base,"materiality":mat,"surprise":surprise,
            "price_confirmation":mc["price_points"],"volume_confirmation":mc["volume_points"],
            "relative_strength":mc["relative_strength_points"],"price_status":mc["price_confirmation"],
            "volume_status":mc["volume_confirmation"],"total":total}

class Store:
    def __init__(self,path="data/edge.db"):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.path=path
        with sqlite3.connect(path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS events(
            id TEXT PRIMARY KEY,symbol TEXT,event_type TEXT,subject TEXT,details TEXT,attachment TEXT,
            published TEXT,source TEXT,edge_score REAL,materiality TEXT,financial_figures TEXT,
            score_components TEXT,price_confirmation TEXT,volume_confirmation TEXT)""")
    def key(self,e):
        raw="|".join(str(e.get(k,"")) for k in ["symbol","subject","published","attachment"])
        return hashlib.sha256(raw.encode()).hexdigest()
    def upsert(self,e):
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.key(e),e["symbol"],e["event_type"],e["subject"],e["details"],e["attachment"],e["published"],
             e["source"],e["edge_score"],e.get("materiality","UNKNOWN"),json.dumps(e.get("financial_figures",[])),
             json.dumps(e["score_components"]),e["price_confirmation"],e["volume_confirmation"]))
    def recent(self,n=1000):
        with sqlite3.connect(self.path) as c:
            rows=c.execute("SELECT * FROM events ORDER BY rowid DESC LIMIT ?",(n,)).fetchall()
        cols=["id","symbol","event_type","subject","details","attachment","published","source","edge_score",
              "materiality","financial_figures","score_components","price_confirmation","volume_confirmation"]
        out=[]
        for row in rows:
            d=dict(zip(cols,row))
            d["financial_figures"]=json.loads(d["financial_figures"] or "[]")
            d["score_components"]=json.loads(d["score_components"] or "{}")
            out.append(d)
        return out

def telegram(token,chat,e):
    if not token or not chat: return False
    msg=f"⚡ EARLY EDGE\n{e['symbol']} • {e['event_type']}\nEdge {e['edge_score']:.0f}/100\n{e['subject'][:500]}"
    try: return requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat,"text":msg},timeout=15).ok
    except Exception: return False

st.set_page_config(page_title="EARLY EDGE V6.1",page_icon="⚡",layout="wide")
st.title("⚡ EARLY EDGE V6.1")
st.caption("NSE-first public-information intelligence • single-file deployment • no dummy data")

store=Store(); market=load_market()
with st.sidebar:
    st.header("CONTROL ROOM")
    threshold=st.slider("High-impact threshold",50,100,75)
    token=st.text_input("Telegram bot token (optional)",type="password")
    chat=st.text_input("Telegram chat ID (optional)")
    st.write(f"Local market rows: **{len(market):,}**")

if st.button("⚡ SCAN NSE PUBLIC FILINGS",type="primary"):
    with st.spinner("Scanning public NSE announcements and available filing attachments..."):
        events,err=scan_nse()
        if err: st.warning(err)
        for e in events:
            txt=parse_attachment(e["attachment"])
            combined=(e["subject"]+" "+e["details"]+" "+txt).strip()
            e["event_type"]=classify(combined); e["financial_figures"]=extract_figures(combined)
            e["parsed_attachment_chars"]=len(txt)
            mc=confirm(e["symbol"],market,e["published"])
            sc=score_event(e,mc); e["score_components"]=sc; e["edge_score"]=sc["total"]
            e["materiality"]=str(sc["materiality"])
            e["price_confirmation"]=sc["price_status"]; e["volume_confirmation"]=sc["volume_status"]
            store.upsert(e)
            if e["edge_score"]>=threshold and token and chat: telegram(token,chat,e)
        st.success(f"Processed {len(events)} public announcements.")

events=store.recent()
if not events:
    st.info("No stored events yet. Click SCAN NSE PUBLIC FILINGS.")
    st.stop()

df=pd.DataFrame(events)
df["edge_score"]=pd.to_numeric(df["edge_score"],errors="coerce").fillna(0)
df["published"]=pd.to_datetime(df["published"],errors="coerce")
df=df.sort_values(["edge_score","published"],ascending=[False,False])

a,b,c,d=st.columns(4)
a.metric("PUBLIC EVENTS",len(df)); b.metric("HIGH IMPACT",int((df.edge_score>=threshold).sum()))
c.metric("TOP EDGE",f"{df.edge_score.max():.0f}/100"); d.metric("AVG EDGE",f"{df.edge_score.mean():.1f}")

t1,t2,t3,t4=st.tabs(["🔥 HIGH IMPACT","🕒 EVENT TAPE","📈 CONFIRMATION","🧠 ANALOGUES"])
with t1:
    st.dataframe(df[df.edge_score>=threshold][["symbol","event_type","subject","edge_score","published","price_confirmation","volume_confirmation"]],use_container_width=True,hide_index=True)
with t2:
    st.dataframe(df[["symbol","event_type","subject","edge_score","published","source"]].head(250),use_container_width=True,hide_index=True)
with t3:
    st.dataframe(df[["symbol","event_type","edge_score","price_confirmation","volume_confirmation","published"]].head(250),use_container_width=True,hide_index=True)
with t4:
    st.dataframe(df.groupby("event_type").agg(events=("symbol","count"),avg_score=("edge_score","mean"),max_score=("edge_score","max")).sort_values("avg_score",ascending=False).round(1),use_container_width=True)

st.divider()
i=st.selectbox("EVENT INSPECTOR",df.index,format_func=lambda x:f"{df.loc[x,'symbol']} • {df.loc[x,'event_type']} • {df.loc[x,'edge_score']:.0f}")
r=df.loc[i]
st.subheader(f"{r['symbol']} | {r['event_type']} | {r['edge_score']:.0f}/100")
st.write(r.get("details",""))
st.json({"published":str(r.get("published")),"source":r.get("source"),"attachment":r.get("attachment"),
         "financial_figures":r.get("financial_figures",[]),"score_components":r.get("score_components",{})})
