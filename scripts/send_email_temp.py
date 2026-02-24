import os
import sys
import smtplib
from email.message import EmailMessage

# Ensure src is importable and load settings from src.config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
try:
    import config
    settings = config.settings
except Exception:
    # Fallback to reading .env directly
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
    class _S:
        pass
    settings = _S()
    settings.SMTP_HOST = os.getenv('SMTP_HOST')
    settings.SMTP_PORT = int(os.getenv('SMTP_PORT') or 587)
    settings.SMTP_USER = os.getenv('SMTP_USER')
    settings.SMTP_PASS = os.getenv('SMTP_PASS')
    settings.SMTP_FROM = os.getenv('SMTP_FROM')

recipient = 'playgames0926@gmail.com'
subject = 'Final Check'
body = 'Agent 能力感知測試'

msg = EmailMessage()
msg['Subject'] = subject
msg['From'] = settings.SMTP_FROM
msg['To'] = recipient
msg.set_content(body)

with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login(settings.SMTP_USER, settings.SMTP_PASS)
    s.send_message(msg)

print('Email sent to', recipient)
