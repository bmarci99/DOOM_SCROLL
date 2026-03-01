import smtplib
from email.message import EmailMessage
from pathlib import Path


def send_email(subject: str, body: str, to_email: str, from_email: str, app_password: str):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, app_password)
        server.send_message(msg)