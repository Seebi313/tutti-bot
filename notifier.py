"""Send email notifications via SMTP and push alerts via ntfy."""

import html
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)


def send_ntfy_alert(config: dict, title: str, body: str):
    ntfy = config.get("ntfy", {})
    url = (ntfy.get("url") or "").rstrip("/")
    topic = ntfy.get("topic") or ""
    if not url or not topic:
        return
    try:
        requests.post(
            f"{url}/{topic}",
            data=body.encode("utf-8"),
            headers={"Title": title, "Priority": "high"},
            timeout=10,
        )
        logger.info("ntfy-Alert gesendet: %s", title)
    except Exception as e:
        logger.warning("ntfy-Alert fehlgeschlagen: %s", e)


def send_notification(listings: list[dict], config: dict):
    cfg = config["email"]
    subject = f"🎁 Tutti.ch: {len(listings)} neue Treffer in deiner Nähe"
    html_body = _build_html(listings)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.get("from", cfg["smtp_user"])
    msg["To"] = cfg["to"]
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(cfg["smtp_user"], cfg["smtp_password"])
        smtp.sendmail(cfg["smtp_user"], cfg["to"], msg.as_string())

    logger.info("Email sent to %s (%d listings)", cfg["to"], len(listings))


def _build_html(listings: list[dict]) -> str:
    cards = "".join(_card(l) for l in listings)
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="de">
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;margin:0 auto;padding:20px;background:#f0f0f0;">
  <div style="background:#d62839;color:white;padding:20px 24px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:20px;">🎁 Neue Treffer auf tutti.ch</h1>
    <p style="margin:6px 0 0;opacity:.85;font-size:14px;">{len(listings)} relevante Inserate · {now}</p>
  </div>
  <div style="padding:8px 0;">{cards}</div>
  <p style="text-align:center;color:#999;font-size:12px;padding:12px 0;">
    <a href="https://www.tutti.ch" style="color:#999;">tutti.ch</a>
  </p>
</body>
</html>"""


def _card(l: dict) -> str:
    score = l.get("score", 0)
    stars = "⭐" * max(0, score - 5) if score else ""
    reason_html = (
        f'<p style="color:#555;font-size:13px;font-style:italic;margin:6px 0;">🤖 {html.escape(l["reason"])}</p>'
        if l.get("reason")
        else ""
    )
    desc = html.escape((l.get("description") or "")[:280])
    desc_html = f'<p style="color:#333;font-size:14px;margin:6px 0;">{desc}…</p>' if desc else ""
    time_str = _fmt_time(l.get("timestamp", ""))
    url = html.escape(l["url"])
    price = html.escape(l.get("price") or "?")

    return f"""
<div style="background:#fff;border-radius:6px;padding:16px;margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,.1);">
  <h2 style="margin:0 0 6px;font-size:16px;">
    <a href="{url}" style="color:#d62839;text-decoration:none;">{html.escape(l['title'])}</a>
  </h2>
  <p style="color:#777;font-size:13px;margin:0 0 6px;">
    📍 {html.escape(l['location'])} ({html.escape(l['postcode'])}) &nbsp;·&nbsp;
    🕒 {time_str} &nbsp;·&nbsp;
    💰 {price} {stars}
  </p>
  {reason_html}
  {desc_html}
  <a href="{url}" style="display:inline-block;background:#d62839;color:white;padding:7px 14px;border-radius:4px;text-decoration:none;font-size:13px;margin-top:6px;">Zum Inserat →</a>
</div>"""


def _fmt_time(ts: str) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d.%m. %H:%M")
    except ValueError:
        return ts
