"""
B2C Test Script — Send Sample B2C Lead Batch to n8n Webhook
============================================================
Sends a realistic B2C test payload to verify the full pipeline:
Hugo → n8n B2C webhook → Notion B2C Leads DB

Usage:
    export B2C_WEBHOOK_URL="https://n8n.bigtorig.com/webhook/b2c-lead-ingestion"
    export B2C_WEBHOOK_TOKEN="your_bearer_token_here"

    uv run test_b2c_webhook.py
"""

import os
import sys
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

B2C_WEBHOOK_URL = os.environ.get("B2C_WEBHOOK_URL")
B2C_WEBHOOK_TOKEN = os.environ.get("B2C_WEBHOOK_TOKEN") or os.environ.get("WEBHOOK_TOKEN")


def get_sample_payload() -> dict:
    """Generate a realistic B2C test batch with 3 sample consumer leads."""
    batch_id = f"B2C-BATCH-{datetime.now().strftime('%Y-%m-%d')}-TEST"

    return {
        "batch_id": batch_id,
        "segment": "B2C",
        "leads": [
            {
                # Lead 1: Hellopeter churn candidate — high intent, already in-market
                "full_name": "Thabo Dlamini",
                "phone": "+27 82 555 0101",
                "email": "thabo.dlamini@gmail.com",
                "province": "Gauteng",
                "city": "Johannesburg",
                "intent_signal": (
                    "Posted 1-star review on Hellopeter for Cartrack: "
                    "'Terrible service, they never respond to theft alerts. "
                    "My car was stolen twice and they did nothing. Looking to switch to a better provider ASAP.'"
                ),
                "intent_source": "Hellopeter",
                "intent_source_url": "https://www.hellopeter.com/cartrack/reviews/test-review-001",
                "intent_date": datetime.now().strftime("%Y-%m-%d"),
                "vehicle_make_model": "Toyota Fortuner",
                "vehicle_year": 2022,
                "call_script_opener": (
                    "Hi Thabo, I noticed you recently had a frustrating experience with your current "
                    "tracker provider after your Fortuner was targeted. Our theft recovery response time "
                    "averages under 4 minutes in Joburg — I'd love to show you how we're different. "
                    "Do you have 5 minutes?"
                ),
                "data_confidence": "High",
                "sources_used": "Hellopeter public review",
                "intent_strength": 9,
                "urgency_score": 8,
            },
            {
                # Lead 2: Gumtree Wanted ad — explicit buyer intent, high urgency
                "full_name": "Priya Naidoo",
                "phone": "+27 83 555 0202",
                "email": "priya.naidoo@webmail.co.za",
                "province": "KwaZulu-Natal",
                "city": "Umhlanga",
                "intent_signal": (
                    "Gumtree Wanted ad posted today: "
                    "'WANTED: Reliable car tracker for Toyota Fortuner. "
                    "Had an attempted hijacking in Umhlanga last week. "
                    "Need something installed ASAP. Please contact Priya.'"
                ),
                "intent_source": "Gumtree",
                "intent_source_url": "https://www.gumtree.co.za/a-car-parts/umhlanga/wanted-car-tracker/test-ad-002",
                "intent_date": datetime.now().strftime("%Y-%m-%d"),
                "vehicle_make_model": "Toyota Fortuner",
                "vehicle_year": 2021,
                "call_script_opener": (
                    "Hi Priya, I saw your Gumtree post — I completely understand the urgency after "
                    "what happened in Umhlanga last week. We can have a tracker installed on your "
                    "Fortuner within 24 hours at a location near you. Want to sort this out today?"
                ),
                "data_confidence": "High",
                "sources_used": "Gumtree SA Wanted ads",
                "intent_strength": 10,
                "urgency_score": 10,
            },
            {
                # Lead 3: MyBroadband forum — research phase, medium urgency
                "full_name": "Werner van der Merwe",
                "phone": "+27 72 555 0303",
                "email": None,
                "province": "Western Cape",
                "city": "Cape Town",
                "intent_signal": (
                    "MyBroadband forum post in Motoring section: "
                    "'Hey everyone, just bought a Golf 8 GTI and looking at tracker options. "
                    "Anyone compared Cartrack vs Netstar vs Matrix recently? "
                    "Want something with a good app and decent theft recovery in Cape Town.'"
                ),
                "intent_source": "MyBroadband",
                "intent_source_url": "https://mybroadband.co.za/forum/threads/tracker-comparison-2026/test-post-003",
                "intent_date": datetime.now().strftime("%Y-%m-%d"),
                "vehicle_make_model": "Volkswagen Golf 8 GTI",
                "vehicle_year": 2026,
                "call_script_opener": (
                    "Hi Werner, I saw you're researching trackers for your new Golf 8 — great choice "
                    "of car. We're often compared to Cartrack and Netstar, and we consistently beat "
                    "them on app experience and Cape Town recovery times. Can I send you a quick "
                    "comparison and a quote?"
                ),
                "data_confidence": "Medium",
                "sources_used": "MyBroadband public forum",
                "intent_strength": 7,
                "urgency_score": 5,
            },
        ],
    }


def main():
    if not B2C_WEBHOOK_URL:
        print("❌ B2C_WEBHOOK_URL not set.")
        print('   export B2C_WEBHOOK_URL="https://n8n.bigtorig.com/webhook/b2c-lead-ingestion"')
        sys.exit(1)
    if not B2C_WEBHOOK_TOKEN:
        print("❌ B2C_WEBHOOK_TOKEN (or WEBHOOK_TOKEN) not set.")
        print('   export B2C_WEBHOOK_TOKEN="your_bearer_token"')
        sys.exit(1)

    payload = get_sample_payload()

    print(f"🚀 Sending B2C test batch: {payload['batch_id']}")
    print(f"   Leads: {len(payload['leads'])}")
    print(f"   Target: {B2C_WEBHOOK_URL}")
    print()

    print("📦 Payload preview:")
    for lead in payload["leads"]:
        composite = lead["intent_strength"] * 0.6 + lead["urgency_score"] * 0.4
        print(f"   • {lead['full_name']}")
        print(f"     Location: {lead['city']}, {lead['province']}")
        print(f"     Source: {lead['intent_source']}")
        print(f"     Intent: {lead['intent_strength']}/10 | Urgency: {lead['urgency_score']}/10 | B2C Score: {composite:.1f}")
        print(f"     Confidence: {lead['data_confidence']}")
        print(f"     Has phone: {'Yes' if lead.get('phone') else 'No'} | Has email: {'Yes' if lead.get('email') else 'No'}")
        print()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {B2C_WEBHOOK_TOKEN}",
    }

    try:
        response = httpx.post(B2C_WEBHOOK_URL, json=payload, headers=headers, timeout=30.0)
        print(f"📡 Response: {response.status_code}")
        print(f"   {response.text}")

        if response.status_code == 200:
            print()
            print("✅ B2C test batch sent successfully!")
            print("   Check Notion B2C Leads DB — you should see 3 new leads")
            print("   in 'Pending QA' status.")
        else:
            print()
            print("❌ Webhook returned an error. Check n8n execution logs.")

    except httpx.ConnectError as e:
        print(f"❌ Connection failed: {e}")
        print("   Is the B2C n8n workflow active? Is the webhook URL correct?")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
