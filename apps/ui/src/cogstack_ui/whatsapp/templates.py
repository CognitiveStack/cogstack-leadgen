from __future__ import annotations

# MESSAGE_TEMPLATE and build_message() are copied verbatim from
# scripts/whatsapp_outreach.py. Keep in sync if the template changes.
# Inline editing of this template is a Phase 2 UI feature; for now,
# edit this file and redeploy.

MESSAGE_TEMPLATE = """\
Hi {name}! 👋

{business_line}

We offer competitive vehicle GPS tracking from *R99/month*, installation included. \
Can we give you a free quote?

Reply *YES* to be called, *NO* if not interested, or *MAYBE* if you'd like more info first. 😊"""


def build_message(name: str, expressed_interest: str) -> str:
    """Compose outreach message from prospect data.

    Future personalisation (e.g. motivation) can be added as
    `motivation: str = ""` when it lands in the message body.

    TODO(tech-debt): scripts/whatsapp_outreach.py's build_message() accepts
    a `motivation` parameter (unused in the template body). Keep the two
    signatures in sync if the template gains a motivation line.
    """
    interest = (expressed_interest or "").strip()
    if interest:
        business_line = f"Do you have vehicle tracking for your {interest.rstrip('.')}?"
    else:
        business_line = "Do you have vehicle tracking for your business vehicles?"
    return MESSAGE_TEMPLATE.format(name=name, business_line=business_line)
