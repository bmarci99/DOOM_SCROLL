import smtplib
from email.message import EmailMessage


def send_email(
    subject: str,
    body_plain: str,
    to_email: str,
    from_email: str,
    app_password: str,
    body_html: str | None = None,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    # Plain text fallback (Markdown)
    msg.set_content(body_plain)

    # Rich HTML version
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, app_password)
        server.send_message(msg)
