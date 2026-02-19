"""
Test Script — Send Sample Lead Batch to n8n Webhook
=====================================================
Sends a realistic test payload to verify the full pipeline:
OpenClaw → n8n webhook → Notion

Usage:
    export WEBHOOK_URL="https://<hostinger-tailscale-ip>:5678/webhook/lead-ingestion"
    export WEBHOOK_TOKEN="your_bearer_token_here"

    uv run test_webhook.py
"""

import os
import sys
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN")


def get_sample_payload() -> dict:
    """Generate a realistic test batch with 3 sample leads."""
    batch_id = f"BATCH-{datetime.now().strftime('%Y-%m-%d')}-TEST"

    return {
        "batch_id": batch_id,
        "leads": [
            {
                "company_name": "Gauteng Express Logistics (Pty) Ltd",
                "cipc_reg": "2019/456789/07",
                "industry": "Transport & Logistics",
                "segment": "B2B",
                "province": "Gauteng",
                "city": "Johannesburg",
                "website": "https://gautengexpress.example.co.za",
                "linkedin": None,
                "contact": "info@gautengexpress.example.co.za / 011 555 1234",
                "prospect_summary": (
                    "Mid-size logistics firm operating an estimated 15+ vehicles across Gauteng. "
                    "Recently awarded a JHB Metropolitan Municipality tender for medical supply delivery, "
                    "which requires GPS compliance reporting. Operating primarily in Johannesburg CBD "
                    "and Soweto — both high vehicle theft zones. Strong tracking need for tender compliance, "
                    "fleet visibility, and fuel cost management."
                ),
                "company_profile": (
                    "Registered 2019. Transport & logistics focused on last-mile delivery and cold chain "
                    "logistics for retail and medical clients in Gauteng. Approximately 45 employees "
                    "based on CIPC filing. Growing rapidly due to recent municipal contract wins."
                ),
                "fleet_assessment": (
                    "Estimated 12-18 vehicles: mix of refrigerated panel vans (cold chain), "
                    "light delivery vehicles (medical supplies), and 2-3 trucks for bulk distribution. "
                    "Fleet likely expanding due to new municipal tender requirements."
                ),
                "tracking_reasoning": (
                    "Three strong signals: (1) Municipal tender requires GPS compliance reporting — "
                    "tracking is effectively mandatory. (2) Operating in JHB CBD and Soweto, both top-10 "
                    "vehicle theft hotspots in SA. (3) Cold chain logistics requires temperature + "
                    "location monitoring for regulatory compliance."
                ),
                "call_script_opener": (
                    "Hi, I'm calling from [Company]. I noticed you recently won a municipal logistics "
                    "tender in Johannesburg — congratulations! Many fleet operators in your position find "
                    "that vehicle tracking helps with tender compliance reporting and fuel management. "
                    "Would you have 5 minutes to chat about how we could support your fleet operations?"
                ),
                "data_confidence": "High",
                "sources_used": "CIPC registration, eTenders award #GT-2026-0891, company website",
                "fleet_likelihood": 9,
                "fleet_size": "Medium (6-20)",
                "tracking_need": 8,
                "source": "eTenders Portal",
            },
            {
                "company_name": "Cape Harvest Agricultural Services",
                "cipc_reg": "2021/234567/07",
                "industry": "Agriculture",
                "segment": "B2B",
                "province": "Western Cape",
                "city": "Stellenbosch",
                "website": "https://capeharvest.example.co.za",
                "linkedin": "https://linkedin.com/company/cape-harvest-ag",
                "contact": "office@capeharvest.example.co.za",
                "prospect_summary": (
                    "Agricultural services company operating across the Western Cape wine and fruit farming "
                    "regions. Provides harvesting, transport, and cold storage services to farms in "
                    "Stellenbosch, Paarl, and Robertson. Estimated 8-12 vehicles including refrigerated "
                    "trucks for produce transport. Seasonal fleet scaling during harvest periods "
                    "(Jan-Apr) increases tracking value."
                ),
                "company_profile": (
                    "Registered 2021. Agricultural services — harvesting, produce transport, and cold "
                    "storage logistics. Services farms across Stellenbosch, Paarl, and Robertson regions. "
                    "Small but growing operation, approximately 25 employees."
                ),
                "fleet_assessment": (
                    "Estimated 8-12 vehicles: refrigerated trucks for produce transport, bakkies for "
                    "farm-to-farm operations, and seasonal rental vehicles during peak harvest. "
                    "Fleet doubles during Jan-Apr harvest season."
                ),
                "tracking_reasoning": (
                    "Produce transport requires cold chain monitoring. Rural operating area means "
                    "vehicles cover long distances with limited oversight. Seasonal fleet scaling "
                    "makes tracking especially valuable — rental vehicles need monitoring too."
                ),
                "call_script_opener": (
                    "Hi, I'm calling from [Company]. We work with several agricultural transport "
                    "companies in the Western Cape. With harvest season being such a busy time for "
                    "fleet management, I wanted to see if vehicle tracking could help you keep tabs "
                    "on your trucks across the farming regions. Do you have a moment?"
                ),
                "data_confidence": "Medium",
                "sources_used": "CIPC registration, LinkedIn company page, Yellow Pages SA",
                "fleet_likelihood": 7,
                "fleet_size": "Medium (6-20)",
                "tracking_need": 6,
                "source": "CIPC Registrations",
            },
            {
                "company_name": "Durban QuickFix Plumbing",
                "cipc_reg": "2023/891234/07",
                "industry": "Services",
                "segment": "B2B",
                "province": "KwaZulu-Natal",
                "city": "Durban",
                "website": None,
                "linkedin": None,
                "contact": "072 555 9876 (Yellow Pages listing)",
                "prospect_summary": (
                    "Small plumbing services company in Durban. Likely operates 3-5 service vehicles "
                    "for callout jobs across the greater Durban area. Limited online presence suggests "
                    "a traditional business that may not have considered fleet tracking. Lower confidence "
                    "lead — included because service vehicle companies in metro areas often benefit from "
                    "dispatch tracking and job costing."
                ),
                "company_profile": (
                    "Registered 2023. Plumbing services in greater Durban area. "
                    "Limited online presence — Yellow Pages listing only. Estimated 5-10 employees."
                ),
                "fleet_assessment": (
                    "Estimated 3-5 vehicles: bakkies or panel vans equipped for plumbing callouts. "
                    "Likely no current fleet management system."
                ),
                "tracking_reasoning": (
                    "Service dispatch tracking can improve response times and job costing. "
                    "Operating in metro Durban — moderate theft risk. Small fleet means lower "
                    "value per customer but potential for many similar businesses."
                ),
                "call_script_opener": (
                    "Hi, I'm calling from [Company]. We help service businesses like plumbers and "
                    "electricians keep track of their vehicles on the road. It helps with dispatching "
                    "the nearest technician to a job and managing fuel costs. Would you be interested "
                    "in hearing how it works?"
                ),
                "data_confidence": "Low",
                "sources_used": "CIPC registration, Yellow Pages SA",
                "fleet_likelihood": 5,
                "fleet_size": "Small (1-5)",
                "tracking_need": 4,
                "source": "Yellow Pages SA",
            },
        ],
    }


def main():
    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL not set.")
        print('   export WEBHOOK_URL="https://<ip>:5678/webhook/lead-ingestion"')
        sys.exit(1)
    if not WEBHOOK_TOKEN:
        print("❌ WEBHOOK_TOKEN not set.")
        print('   export WEBHOOK_TOKEN="your_bearer_token"')
        sys.exit(1)

    payload = get_sample_payload()

    print(f"🚀 Sending test batch: {payload['batch_id']}")
    print(f"   Leads: {len(payload['leads'])}")
    print(f"   Target: {WEBHOOK_URL}")
    print()

    # Pretty print the payload for review
    print("📦 Payload preview:")
    for lead in payload["leads"]:
        score = lead["fleet_likelihood"] * 0.4 + lead["tracking_need"] * 0.4
        size_bonus = 1 if "Medium" in lead["fleet_size"] else (2 if "Large" in lead["fleet_size"] else 0)
        composite = score + size_bonus * 0.2
        print(f"   • {lead['company_name']}")
        print(f"     Industry: {lead['industry']} | Province: {lead['province']}")
        print(f"     Fleet: {lead['fleet_likelihood']}/10 | Need: {lead['tracking_need']}/10 | Composite: {composite:.1f}")
        print(f"     Confidence: {lead['data_confidence']}")
        print()

    # Send the request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {WEBHOOK_TOKEN}",
    }

    try:
        response = httpx.post(WEBHOOK_URL, json=payload, headers=headers, timeout=30.0)
        print(f"📡 Response: {response.status_code}")
        print(f"   {response.text}")

        if response.status_code == 200:
            print()
            print("✅ Test batch sent successfully!")
            print("   Check your Notion workspace — you should see 3 new leads")
            print("   in the 'Pending QA' status.")
        else:
            print()
            print("❌ Webhook returned an error. Check n8n execution logs.")

    except httpx.ConnectError as e:
        print(f"❌ Connection failed: {e}")
        print("   Is n8n running? Is the Tailscale connection active?")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
