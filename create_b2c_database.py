"""
B2C Notion Database Setup Script
=================================
Creates B2C Leads and B2C Batches databases, then seeds B2C-specific
sources into the existing shared Sources database.

Run AFTER create_notion_databases.py — the shared Sources DB must exist first.

Usage:
    uv run create_b2c_database.py

Requirements:
    NOTION_API_KEY and NOTION_PAGE_ID in .env (same as B2B setup)
    notion_config.json must exist with sources_database_id
"""

import os
import sys
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID")
NOTION_VERSION = "2022-06-28"

BASE_URL = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

SA_PROVINCES = [
    {"name": "Gauteng", "color": "blue"},
    {"name": "Western Cape", "color": "green"},
    {"name": "KwaZulu-Natal", "color": "orange"},
    {"name": "Eastern Cape", "color": "yellow"},
    {"name": "Free State", "color": "red"},
    {"name": "Limpopo", "color": "brown"},
    {"name": "Mpumalanga", "color": "purple"},
    {"name": "North West", "color": "pink"},
    {"name": "Northern Cape", "color": "gray"},
]


def check_config():
    """Validate environment variables and notion_config.json are present."""
    if not NOTION_API_KEY:
        print("❌ NOTION_API_KEY not set. Export it first:")
        print('   export NOTION_API_KEY="ntn_your_secret_here"')
        sys.exit(1)
    if not NOTION_PAGE_ID:
        print("❌ NOTION_PAGE_ID not set. Export it first:")
        print('   export NOTION_PAGE_ID="your_32_char_page_id_here"')
        sys.exit(1)

    if not os.path.exists("notion_config.json"):
        print("❌ notion_config.json not found.")
        print("   Run create_notion_databases.py first to create the shared Sources DB.")
        sys.exit(1)

    with open("notion_config.json") as f:
        config = json.load(f)

    if not config.get("sources_database_id"):
        print("❌ sources_database_id missing from notion_config.json.")
        print("   Run create_notion_databases.py first.")
        sys.exit(1)

    print("✅ Config loaded")
    print(f"   Page ID:    {NOTION_PAGE_ID[:8]}...{NOTION_PAGE_ID[-4:]}")
    print(f"   API Key:    {NOTION_API_KEY[:8]}...{NOTION_API_KEY[-4:]}")
    print(f"   Sources DB: {config['sources_database_id']}")
    print()
    return config["sources_database_id"]


def create_database(client: httpx.Client, title: str, icon: str, properties: dict) -> str:
    """Create a Notion database under the parent page. Returns the database ID."""
    payload = {
        "parent": {"type": "page_id", "page_id": NOTION_PAGE_ID},
        "icon": {"type": "emoji", "emoji": icon},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    }

    response = client.post(f"{BASE_URL}/databases", json=payload)

    if response.status_code != 200:
        print(f"❌ Failed to create '{title}': {response.status_code}")
        print(f"   {response.text}")
        sys.exit(1)

    db_id = response.json()["id"]
    print(f"✅ Created '{title}' — ID: {db_id}")
    return db_id


def create_b2c_batches_database(client: httpx.Client) -> str:
    """Create the B2C Batches operations database."""
    properties = {
        "Batch ID": {"title": {}},
        "Run Date": {"date": {}},
        "Status": {
            "select": {
                "options": [
                    {"name": "Running", "color": "blue"},
                    {"name": "Completed", "color": "green"},
                    {"name": "Partial", "color": "yellow"},
                    {"name": "Failed", "color": "red"},
                ]
            }
        },
        "Leads Found": {"number": {"format": "number"}},
        "Leads After Dedup": {"number": {"format": "number"}},
        "Sources Crawled": {"rich_text": {}},
        "Errors": {"rich_text": {}},
        "API Cost (USD)": {"number": {"format": "dollar"}},
    }

    return create_database(client, "B2C Batches", "⚙️", properties)


def create_b2c_leads_database(
    client: httpx.Client,
    sources_db_id: str,
    batches_db_id: str,
) -> str:
    """Create the B2C Leads database with consumer-oriented schema."""
    properties = {
        # --- Identity (individual, not company) ---
        "Full Name": {"title": {}},
        "Phone": {"phone_number": {}},
        "Email": {"email": {}},
        "Province": {"select": {"options": SA_PROVINCES}},
        "City / Area": {"rich_text": {}},

        # --- Intent Signal (dedup key + enrichment) ---
        "Intent Signal": {"rich_text": {}},
        "Intent Source": {
            "select": {
                "options": [
                    {"name": "Hellopeter", "color": "red"},
                    {"name": "Gumtree", "color": "green"},
                    {"name": "Facebook Group", "color": "blue"},
                    {"name": "MyBroadband", "color": "orange"},
                    {"name": "OLX", "color": "yellow"},
                    {"name": "Twitter-X", "color": "gray"},
                    {"name": "Reddit", "color": "purple"},
                    {"name": "Other", "color": "default"},
                ]
            }
        },
        "Intent Source URL": {"url": {}},
        "Intent Date": {"date": {}},

        # --- Vehicle Context (optional) ---
        "Vehicle Make / Model": {"rich_text": {}},
        "Vehicle Year": {"number": {"format": "number"}},

        # --- AI-Generated Enrichment ---
        "Call Script Opener": {"rich_text": {}},
        "Data Confidence": {
            "select": {
                "options": [
                    {"name": "High", "color": "green"},
                    {"name": "Medium", "color": "yellow"},
                    {"name": "Low", "color": "red"},
                ]
            }
        },
        "Sources Used": {"rich_text": {}},

        # --- Scoring ---
        "Intent Strength": {"number": {"format": "number"}},
        "Urgency Score": {"number": {"format": "number"}},
        # Note: B2C Composite Score is a Notion formula property.
        # Must be added manually in Notion UI — see print_manual_steps() below.

        # --- QA Review ---
        "Status": {
            "select": {
                "options": [
                    {"name": "Pending QA", "color": "default"},
                    {"name": "QA Approved", "color": "green"},
                    {"name": "QA Rejected", "color": "red"},
                    {"name": "Sent to Call Centre", "color": "blue"},
                    {"name": "Contacted", "color": "purple"},
                    {"name": "Interested", "color": "yellow"},
                    {"name": "Converted", "color": "green"},
                    {"name": "Not Interested", "color": "orange"},
                    {"name": "Duplicate", "color": "gray"},
                ]
            }
        },
        "QA Review Date": {"date": {}},
        "QA Notes": {"rich_text": {}},
        "Rejection Reason": {
            "select": {
                "options": [
                    {"name": "Disconnected Number", "color": "red"},
                    {"name": "Duplicate", "color": "gray"},
                    {"name": "No Interest Expressed", "color": "orange"},
                    {"name": "Invalid Contact", "color": "red"},
                    {"name": "Out of Area", "color": "purple"},
                    {"name": "Other", "color": "default"},
                ]
            }
        },

        # --- Pipeline Tracking ---
        "Date Added": {"date": {}},
        "Date Delivered": {"date": {}},
        # Note: Rejection Deadline = dateAdd(Date Delivered, 5, "days")
        # Must be added manually in Notion UI as a formula property.
        "Dispute Status": {
            "select": {
                "options": [
                    {"name": "Pending", "color": "yellow"},
                    {"name": "Accepted", "color": "green"},
                    {"name": "Rejected by Client", "color": "red"},
                    {"name": "Disputed", "color": "orange"},
                ]
            }
        },
        "Dispute Reason": {"rich_text": {}},

        # --- Relations ---
        "Batch": {
            "relation": {
                "database_id": batches_db_id,
                "single_property": {},
            }
        },
        "Source": {
            "relation": {
                "database_id": sources_db_id,
                "single_property": {},
            }
        },
    }

    return create_database(client, "B2C Leads", "👤", properties)


def seed_b2c_sources(client: httpx.Client, sources_db_id: str):
    """Seed B2C-specific sources into the shared Sources database."""
    sources = [
        {
            "Source Name": "Hellopeter — Competitor Reviews",
            "Source Type": "Consumer Review",
            "URL": "https://www.hellopeter.com",
            "POPIA Status": "Compliant",
            "Status": "Active",
            "Notes": (
                "1-2 star reviews of Cartrack, Matrix, Tracker = churn candidates. "
                "High intent signal: person is in-market and dissatisfied with competitor."
            ),
        },
        {
            "Source Name": "Gumtree SA — Wanted Ads",
            "Source Type": "Business Directory",
            "URL": "https://www.gumtree.co.za",
            "POPIA Status": "Compliant",
            "Status": "Active",
            "Notes": (
                "Wanted section: 'vehicle tracker', 'car tracker', 'GPS tracking'. "
                "Self-authored public posts — explicit buying intent."
            ),
        },
        {
            "Source Name": "Facebook Public Groups — SA Car Security",
            "Source Type": "Social Media",
            "URL": "https://www.facebook.com",
            "POPIA Status": "Caution Required",
            "Status": "Active",
            "Notes": (
                "Public group posts only — never private groups or personal profiles. "
                "Target groups: Joburg Car Security, Cape Town Car Watch, SA Stolen Vehicles. "
                "Posts asking for tracker recommendations or reporting break-ins."
            ),
        },
        {
            "Source Name": "MyBroadband Forums",
            "Source Type": "Social Media",
            "URL": "https://mybroadband.co.za/forum",
            "POPIA Status": "Compliant",
            "Status": "Active",
            "Notes": (
                "Security and motoring sub-forums. Tech-savvy users comparing tracker products. "
                "High data confidence — users typically provide detailed vehicle info."
            ),
        },
        {
            "Source Name": "OLX SA — Wanted",
            "Source Type": "Business Directory",
            "URL": "https://www.olx.co.za",
            "POPIA Status": "Compliant",
            "Status": "Active",
            "Notes": "Wanted section for vehicle security products. Active buyer intent.",
        },
        {
            "Source Name": "Reddit r/southafrica",
            "Source Type": "Social Media",
            "URL": "https://www.reddit.com/r/southafrica",
            "POPIA Status": "Compliant",
            "Status": "Active",
            "Notes": (
                "Public posts about car security, tracking, vehicle theft. "
                "Moderate volume but high signal quality — users ask specific questions."
            ),
        },
    ]

    print(f"\n📝 Seeding B2C sources into shared Sources database ({len(sources)} sources)...")

    for source in sources:
        properties = {
            "Source Name": {"title": [{"text": {"content": source["Source Name"]}}]},
            "Source Type": {"select": {"name": source["Source Type"]}},
            "URL": {"url": source["URL"]},
            "POPIA Status": {"select": {"name": source["POPIA Status"]}},
            "Status": {"select": {"name": source["Status"]}},
        }

        if "Notes" in source:
            properties["Notes"] = {
                "rich_text": [{"text": {"content": source["Notes"]}}]
            }

        payload = {
            "parent": {"database_id": sources_db_id},
            "properties": properties,
        }

        response = client.post(f"{BASE_URL}/pages", json=payload)

        if response.status_code == 200:
            print(f"   ✅ {source['Source Name']}")
        else:
            print(f"   ❌ {source['Source Name']}: {response.status_code}")
            print(f"      {response.text[:200]}")


def print_manual_steps(leads_db_id: str):
    """Print Notion UI steps that cannot be done via API."""
    print()
    print("=" * 60)
    print("📋 MANUAL STEPS REQUIRED IN NOTION UI (B2C)")
    print("=" * 60)
    print()
    print("The Notion API does not support formula or person properties.")
    print("Add these manually to the B2C Leads database:")
    print()
    print("1. B2C COMPOSITE SCORE")
    print("   - Open B2C Leads database → '+' → Formula")
    print("   - Name: B2C Composite Score")
    print("   - Formula:")
    print('     prop("Intent Strength") * 0.6 + prop("Urgency Score") * 0.4')
    print()
    print("2. B2C QUALITY GATE")
    print("   - Add another Formula property")
    print("   - Name: B2C Quality Gate")
    print("   - Formula:")
    print('     if(prop("B2C Composite Score") >= 7, "✅ Auto-Approve", if(prop("B2C Composite Score") >= 4, "⚠️ Review", "❌ Auto-Reject"))')
    print()
    print("3. REJECTION DEADLINE")
    print("   - Add a Formula property")
    print("   - Name: Rejection Deadline")
    print("   - Formula (calendar day approximation — adjust manually for weekends):")
    print('     dateAdd(prop("Date Delivered"), 5, "days")')
    print()
    print("4. QA REVIEWED BY")
    print("   - Add a Person property")
    print("   - Name: QA Reviewed By")
    print()
    print("5. CREATE VIEWS in B2C Leads database:")
    print("   - 🔍 B2C QA Queue")
    print("     Table | Filter: Status = 'Pending QA' | Sort: B2C Composite Score DESC")
    print("   - ✅ B2C Approved — Ready to Send")
    print("     Table | Filter: Status = 'QA Approved'")
    print("   - 📋 B2C Pipeline Kanban")
    print("     Board | Group by: Status")
    print("   - ⚖️ Dispute Tracker")
    print("     Table | Filter: Date Delivered is not empty, Dispute Status = 'Pending'")
    print("     Sort: Rejection Deadline ASC")
    print()


def print_database_ids(batches_id: str, leads_id: str):
    """Print and save B2C database IDs, merging with existing notion_config.json."""
    print()
    print("=" * 60)
    print("🔑 B2C DATABASE IDs — SAVE FOR n8n CONFIGURATION")
    print("=" * 60)
    print()
    print(f"  B2C_LEADS_DB_ID    = {leads_id}")
    print(f"  B2C_BATCHES_DB_ID  = {batches_id}")
    print()
    print("Add these to your .env file and n8n B2C Code node constants.")
    print()

    # Read existing config and merge B2C IDs
    config = {}
    if os.path.exists("notion_config.json"):
        with open("notion_config.json") as f:
            config = json.load(f)

    config["b2c_leads_database_id"] = leads_id
    config["b2c_batches_database_id"] = batches_id
    config["b2c_created_at"] = datetime.now().isoformat()

    with open("notion_config.json", "w") as f:
        json.dump(config, f, indent=2)

    print("💾 B2C IDs merged into notion_config.json (B2B IDs preserved)")


def main():
    print()
    print("🚀 B2C Notion Database Setup")
    print("=" * 60)
    print()

    sources_db_id = check_config()

    with httpx.Client(headers=HEADERS, timeout=30.0) as client:
        # Verify connection
        print("🔌 Verifying Notion API connection...")
        response = client.get(f"{BASE_URL}/users/me")
        if response.status_code != 200:
            print(f"❌ API connection failed: {response.status_code}")
            print(f"   {response.text}")
            print("   Check your NOTION_API_KEY and integration permissions.")
            sys.exit(1)
        bot_name = response.json().get("name", "Unknown")
        print(f"✅ Connected as: {bot_name}")
        print()

        print("📦 Creating B2C databases...")
        print("-" * 40)

        # 1. B2C Batches first (no dependencies)
        batches_db_id = create_b2c_batches_database(client)

        # 2. B2C Leads (depends on Batches and shared Sources for relations)
        leads_db_id = create_b2c_leads_database(client, sources_db_id, batches_db_id)

        # 3. Seed B2C sources into shared Sources DB
        seed_b2c_sources(client, sources_db_id)

        # 4. Output results
        print_database_ids(batches_db_id, leads_db_id)
        print_manual_steps(leads_db_id)

    print("🎉 B2C setup complete!")
    print("   Next: Follow manual steps above, then create the n8n B2C workflow.")
    print("   Paste n8n_b2c_code_node.js into the new workflow's Code node.")
    print()


if __name__ == "__main__":
    main()
