import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_ADDR = os.getenv("SMTP_FROM", SMTP_USER)

_HTML = """\
<html><body style="font-family:sans-serif;color:#222">
<h2 style="color:#c0392b">Dein WClouds-Konto wird gelöscht</h2>
<p>Hallo,</p>
<p>dein <strong>WClouds</strong>-Konto war seit über einem Jahr nicht mehr aktiv.</p>
<p>Falls du dich <strong>nicht innerhalb von 7&nbsp;Tagen</strong> einloggst,
wird dein Konto <strong>einschließlich aller gespeicherten Dateien
unwiderruflich gelöscht</strong>.</p>
<p>Logge dich jetzt ein, um dein Konto zu behalten.</p>
<hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
<small style="color:#888">Diese E-Mail wurde automatisch gesendet.
Bitte antworte nicht darauf.</small>
</body></html>"""

_TEXT = (
    "Hallo,\n\n"
    "dein WClouds-Konto war seit über einem Jahr nicht mehr aktiv.\n\n"
    "Falls du dich nicht innerhalb von 7 Tagen einloggst, wird dein Konto "
    "einschließlich aller gespeicherten Dateien unwiderruflich gelöscht.\n\n"
    "Logge dich jetzt ein, um dein Konto zu behalten.\n\n"
    "Diese E-Mail wurde automatisch gesendet."
)


def send_deletion_warning(to_email: str) -> bool:
    """Sendet die Lösch-Warnung. Gibt True zurück wenn erfolgreich (oder SMTP nicht konfiguriert)."""
    if not SMTP_USER or not SMTP_PASS:
        print(f"[Email] SMTP nicht konfiguriert – überspringe {to_email}")
        # True zurückgeben damit deletion_warning_sent trotzdem gesetzt wird
        # und kein Retry-Loop entsteht; Deletion läuft nach 7 Tagen.
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "WClouds: Dein Konto wird in 7 Tagen gelöscht"
    msg["From"]    = FROM_ADDR
    msg["To"]      = to_email
    msg.attach(MIMEText(_TEXT, "plain", "utf-8"))
    msg.attach(MIMEText(_HTML,  "html",  "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(FROM_ADDR, to_email, msg.as_string())
        print(f"[Email] Lösch-Warnung gesendet → {to_email}")
        return True
    except Exception as exc:
        print(f"[Email] Fehler beim Senden an {to_email}: {exc}")
        return False
