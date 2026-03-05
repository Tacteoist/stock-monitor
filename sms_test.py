import os
import smtplib
from email.mime.text import MIMEText

# Your credentials from environment variables
EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

# The SMS gateway address
RECIPIENT = ["7138705232@txt.att.net"]  # Replace with your number + carrier gateway

def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(RECIPIENT)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

# Send a tiny test SMS
send_email("Test SMS", "Hello! This is a test.")
print("Test email sent!")
