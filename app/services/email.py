"""
AWS SES email service for OTP / magic-link authentication emails.

SES must be configured with:
  - A verified sender identity (SES_FROM_EMAIL)
  - Sufficient sending quota for your region
  - The destination email addresses verified (while in SES sandbox mode)
"""
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── HTML email template ───────────────────────────────────────────────────────

_EMAIL_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sign in to {app_name}</title>
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:12px;overflow:hidden;
                      box-shadow:0 1px 3px rgba(0,0,0,.1);">

          <!-- Header -->
          <tr>
            <td style="background:#4f46e5;padding:32px 40px;text-align:center;">
              <span style="color:#ffffff;font-size:24px;font-weight:700;
                           letter-spacing:-0.5px;">{app_name}</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 24px;">
              <p style="margin:0 0 8px;font-size:16px;color:#111827;font-weight:600;">
                Your sign-in code
              </p>
              <p style="margin:0 0 24px;font-size:14px;color:#6b7280;line-height:1.5;">
                Use the code below to sign in to your {app_name} account.
                It expires in <strong>{expiry_minutes} minutes</strong>.
              </p>

              <!-- OTP block -->
              <div style="background:#eef2ff;border:2px solid #c7d2fe;border-radius:10px;
                          padding:24px;text-align:center;margin-bottom:28px;">
                <span style="font-size:40px;font-weight:800;letter-spacing:12px;
                             color:#4f46e5;font-variant-numeric:tabular-nums;">
                  {otp_code}
                </span>
              </div>

              <!-- Magic link -->
              <p style="margin:0 0 16px;font-size:14px;color:#6b7280;text-align:center;">
                Or sign in instantly with one click:
              </p>
              <div style="text-align:center;margin-bottom:32px;">
                <a href="{magic_link}"
                   style="display:inline-block;background:#4f46e5;color:#ffffff;
                          font-size:15px;font-weight:600;text-decoration:none;
                          padding:13px 32px;border-radius:8px;">
                  Sign in to {app_name}
                </a>
              </div>

              <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;line-height:1.6;">
                If you didn&apos;t request this, you can safely ignore this email.<br />
                This link can only be used once.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f3f4f6;padding:16px 40px;text-align:center;">
              <span style="font-size:12px;color:#9ca3af;">
                &copy; {app_name}. All rights reserved.
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

_EMAIL_TEXT = """\
Sign in to {app_name}

Your one-time passcode: {otp_code}

This code expires in {expiry_minutes} minutes.

Or sign in instantly using this link:
{magic_link}

If you didn't request this, please ignore this email.
"""


def _ses_client():
    return boto3.client(
        "ses",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


async def send_otp_email(
    *,
    to_email: str,
    otp_code: str,
    magic_link: str,
) -> None:
    """
    Send the OTP + magic-link email via AWS SES.

    Raises HTTP 503 if SES_FROM_EMAIL is not configured.
    Raises HTTP 502 on SES delivery failures (surfaced to the caller so they
    can return a meaningful error instead of a silent no-op).
    """
    if not settings.SES_FROM_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured.",
        )

    from_address = f"{settings.SES_FROM_NAME} <{settings.SES_FROM_EMAIL}>"
    tpl_vars = {
        "app_name": settings.APP_NAME,
        "otp_code": otp_code,
        "magic_link": magic_link,
        "expiry_minutes": settings.OTP_EXPIRY_MINUTES,
    }

    try:
        client = _ses_client()
        client.send_email(
            Source=from_address,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {
                    "Data": f"Your {settings.APP_NAME} sign-in code: {otp_code}",
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": _EMAIL_TEXT.format(**tpl_vars),
                        "Charset": "UTF-8",
                    },
                    "Html": {
                        "Data": _EMAIL_HTML.format(**tpl_vars),
                        "Charset": "UTF-8",
                    },
                },
            },
        )
        logger.info("OTP email sent to %s", to_email)
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        logger.error("SES ClientError sending OTP to %s: %s", to_email, error_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send email: {error_code}",
        )
    except BotoCoreError as exc:
        logger.error("SES BotoCoreError sending OTP to %s: %s", to_email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Email delivery service is temporarily unavailable.",
        )
