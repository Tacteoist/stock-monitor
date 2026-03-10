import yfinance as yf
import smtplib
import json
import os
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import time

portfolio = [
"ABBV","ABM","ABR","AGNC","ALB","AMCR","ANDE","AVNT","AWR","BEN","BKH","CINF",
"CL","CSCO","CVX","CWT","DCI","DGICA","DGICB","EMLAF","EMR","ENB","F","FRT",
"GECC","GOOD","HRL","HRZN","IP","IRM","JEPI","KBWY","KEY","KMB","KO","LEG",
"LTC","LYB","MAIN","MCD","MCY","MDU","MMM","MO","MPT","NEE","NFG","NHI","NJR",
"NNN","NUE","NWE","NWN","O","OHI","OKE","ORI","OXSQ","PBA","PFE","PM","PMT",
"PPG","PSEC","PTEN","QQQH","QSR","QYLD","RBCAA","RITM","RYLD","SBSI","SPHD",
"SRET","SWK","SYY","T","TDS","TGT","TROW","UGI","UHT","UPS","UVV","VPC","VZ",
"WASH","WEYS","WMT","XOM","XYLD","YYY"
]

EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECIPIENT = [EMAIL_ADDRESS,"monyyong@att.net"]

# ---------------- EMAIL ---------------- #
def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(RECIPIENT)
    with smtplib.SMTP_SSL("smtp.gmail.com",465) as server:
        server.login(EMAIL_ADDRESS,EMAIL_PASSWORD)
        server.send_message(msg)

# ---------------- DIVIDEND CACHE ---------------- #
def load_dividend_cache():
    cache_file = "dividend_cache.json"
    try:
        with open(cache_file,"r") as f:
            cache=json.load(f)
    except:
        cache={"data":{}}

    old_data=cache.get("data",{})
    today=datetime.now().strftime("%Y-%m-%d")

    if cache.get("last_update")==today:
        return old_data,[]

    print("Updating dividend database...")
    new_data={}
    dividend_cuts=[]

    for ticker in portfolio:
        try:
            stock=yf.Ticker(ticker)
            dividends=stock.dividends
            annual_div=float(dividends[-4:].sum()) if len(dividends)>0 else 0
        except:
            annual_div=0

        new_data[ticker]=annual_div
        old_div=old_data.get(ticker,0)
        if old_div>0 and annual_div==0:
            dividend_cuts.append(ticker)

    cache={"last_update":today,"data":new_data}
    with open(cache_file,"w") as f:
        json.dump(cache,f)

    return new_data,dividend_cuts

# ---------------- ALERT STATE ---------------- #
try:
    with open("alert_state.json","r") as f:
        alerted=json.load(f)
except:
    alerted={}

annual_dividends,dividend_cuts=load_dividend_cache()

# ---------------- INTRADAY CACHE ---------------- #
intraday_cache_file = "intraday_cache.json"
try:
    with open(intraday_cache_file,"r") as f:
        intraday_cache=json.load(f)
except:
    intraday_cache={}

print("Fetching intraday market data...")

def fetch_intraday(tickers_batch):
    batch_data={}
    for ticker in tickers_batch:
        try:
            stock = yf.Ticker(ticker)
            last_time_str = intraday_cache.get(ticker, {}).get("last_timestamp")
            if last_time_str:
                last_time = datetime.fromisoformat(last_time_str)
                # add 1 minute to avoid fetching duplicate candle
                start_time = last_time + timedelta(minutes=1)
                hist = stock.history(period="1d", interval="15m", start=start_time)
            else:
                hist = stock.history(period="1d", interval="15m")
            if hist.empty:
                continue
            batch_data[ticker] = hist["Close"].dropna()
            # update cache
            intraday_cache[ticker] = {
                "last_price": float(batch_data[ticker].iloc[-1]),
                "last_timestamp": batch_data[ticker].index[-1].to_pydatetime().isoformat()
            }
            time.sleep(0.5)  # reduce rate-limit risk
        except:
            continue
    return batch_data

# Split portfolio into chunks to reduce throttling
chunk_size=15
data={}
for i in range(0,len(portfolio),chunk_size):
    batch = portfolio[i:i+chunk_size]
    batch_data = fetch_intraday(batch)
    data.update(batch_data)

# Save intraday cache
with open(intraday_cache_file,"w") as f:
    json.dump(intraday_cache,f)

# ---------------- ALERTS & SIGNALS ---------------- #
alerts=[]
radar=[]
buy_signals=[]
crash_count=0
panic_count=0

for ticker, closes in data.items():
    try:
        if len(closes)<20:
            continue
        current_price=closes.iloc[-1]
        yesterday=closes.iloc[-2]
        daily_drop=(yesterday-current_price)/yesterday*100

        # Crash/Panic Detector
        if daily_drop>=10:
            panic_count+=1
            if alerted.get(ticker+"_panic")!=str(current_price):
                alerts.append((ticker,current_price,f"🔥 PANIC DROP {daily_drop:.2f}%"))
                alerted[ticker+"_panic"]=str(current_price)
        elif daily_drop>=5:
            crash_count+=1
            if alerted.get(ticker+"_crash")!=str(current_price):
                alerts.append((ticker,current_price,f"💥 CRASH {daily_drop:.2f}%"))
                alerted[ticker+"_crash"]=str(current_price)

        # 2 Week Low
        two_week_low=closes[-14:].min()
        drop_pct=abs(current_price-two_week_low)/two_week_low*100
        if current_price<=two_week_low and alerted.get(ticker+"_2w")!=str(two_week_low):
            alerts.append((ticker,current_price,f"-{drop_pct:.2f}% below 2W low"))
            alerted[ticker+"_2w"]=str(two_week_low)

        # 52 Week Low
        low_52=closes.min()
        pct_from_low=(current_price-low_52)/low_52*100
        if current_price<low_52:
            alerts.append((ticker,current_price,"🚨 BELOW 52W LOW"))
        elif pct_from_low<=10:
            alerts.append((ticker,current_price,f"{pct_from_low:.2f}% above 52W low"))

        radar.append((ticker,current_price,pct_from_low))

        # Dividend Trap
        annual_div=annual_dividends.get(ticker,0)
        div_yield=(annual_div/current_price*100) if annual_div>0 else 0
        trap_score=sum([div_yield>=10, pct_from_low<=5, daily_drop>=5])
        if trap_score>=2:
            alerts.append((ticker,current_price,
                           f"⚠️ DIVIDEND TRAP RISK – Yield {div_yield:.1f}% | {pct_from_low:.1f}% above 52W low"))

        # Buy Signal Score
        score=0
        if pct_from_low<=10: score+=2
        if pct_from_low<=5: score+=3
        if daily_drop>=5: score+=3
        if daily_drop>=10: score+=5
        buy_signals.append((ticker,current_price,pct_from_low,score))

    except:
        continue

# Dividend cut alerts
for ticker in dividend_cuts:
    alerts.append((ticker,0,"🚨 DIVIDEND CUT (Dividend dropped to $0)"))

# Market panic
portfolio_size=len(portfolio)
panic_ratio=panic_count/portfolio_size
crash_ratio=crash_count/portfolio_size
market_alert=""
if panic_ratio>=0.05:
    market_alert="🔥 MARKET PANIC MODE"
elif crash_ratio>=0.15:
    market_alert="⚠️ MARKET SELL-OFF"

# Rankings
radar.sort(key=lambda x:x[2])
top_radar=radar[:10]
buy_signals.sort(key=lambda x:x[3],reverse=True)
top_buys=buy_signals[:5]


# ---------------- EMAIL ---------------- #
today = datetime.now().strftime("%Y-%m-%d")
body = f"📊 PORTFOLIO OPPORTUNITY RADAR – {today}\n\n"

# ⭐ TOP BUY SIGNALS FIRST
body += "⭐ TOP BUY SIGNALS\n\n"
for i, (ticker, price, pct, score) in enumerate(top_buys, 1):
    body += f"{i}. {ticker} – ${price:.2f}\n   Score: {score}\n   {pct:.2f}% above 52W low\n\n"

# Market alert
if market_alert: 
    body += market_alert + "\n\n"

# Alerts
if alerts:
    body += "🚨 ALERTS\n\n"
    for i, (ticker, price, msg) in enumerate(alerts, 1):
        body += f"{i}. {ticker} – ${price:.2f}\n   {msg}\n\n"

# Closest to 52W low
body += "\n📉 CLOSEST TO 52W LOW\n\n"
for i, (ticker, price, pct) in enumerate(top_radar, 1):
    body += f"{i}. {ticker} – ${price:.2f}\n   {pct:.2f}% above 52W low\n\n"

if alerts or market_alert:
    send_email(subject=f"Portfolio Opportunity Radar – {today}", body=body)

# Save alert state
with open("alert_state.json","w") as f:
    json.dump(alerted,f)
