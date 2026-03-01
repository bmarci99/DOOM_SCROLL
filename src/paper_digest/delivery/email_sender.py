import smtplib
from email.message import EmailMessage
from html import escape
import re

def _md_to_basic_html(md: str) -> str:
    # Minimal “good enough” conversion:
    # - escape HTML
    # - turn Markdown links [t](u) into <a>
    # - preserve line breaks
    text = escape(md)

    # links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # headers
    text = re.sub(r"^# (.+)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)

    # bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)

    # line breaks
    text = text.replace("\n", "<br>\n")

    return f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif; line-height: 1.45;">
        {text}
      </body>
    </html>
    """.strip()

def send_email(subject: str, body: str, to_email: str, from_email: str, app_password: str):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    # Plain text fallback
    msg.set_content(body)

    # HTML version
    html = _md_to_basic_html(body)
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, app_password)
        server.send_message(msg)