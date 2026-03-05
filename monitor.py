import yfinance as yf
import smtplib
import json
import os
from email.mime.text import MIMEText
from datetime import datetime

portfolio = [
    "ABM", "AGNC", "BEN"
    # ← Replace with all 69 of your tickers
]

EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECIPIENT = EMAIL_ADDRESS

def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = RECIPIENT

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

try:
    with open("alert_state.json", "r") as f:
        alerted = json.load(f)
except:
    alerted = {}

data = yf.download(portfolio, period="20d", group_by="ticker", progress=False)

alerts = []

for ticker in portfolio:
    try:
        closes = data[ticker]["Close"].dropna()
        if len(closes) < 14:
            continue

        two_week_low = closes[-14:].min()
        current_price = closes.iloc[-1]

        if current_price <= two_week_low:
            drop_pct = (two_week_low - current_price) / two_week_low * 100

            if alerted.get(ticker) != str(two_week_low):
                alerts.append((ticker, current_price, drop_pct))
                alerted[ticker] = str(two_week_low)
    except:
        continue

alerts.sort(key=lambda x: x[2], reverse=True)

if alerts:
    today = datetime.now().strftime("%Y-%m-%d")
    body = "🚨 2-Week Lows (Ranked by Biggest Drop)\n\n"

    for i, (ticker, price, drop) in enumerate(alerts, 1):
        body += f"{i}. {ticker} – ${price:.2f}\n"
        body += f"   -{drop:.2f}% below 2W low\n\n"

    send_email(
        subject=f"2-Week Low Alerts – {today}",
        body=body
    )

with open("alert_state.json", "w") as f:
    json.dump(alerted, f)
