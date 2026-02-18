"""
Notion Database Setup Script — AI Lead Generation System
=========================================================
Creates the three linked databases (Leads, Sources, Batches)
with full schema as defined in the design document v2.0.

Usage:
    # Set environment variables first:
    export NOTION_API_KEY="ntn_your_secret_here"
    export NOTION_PAGE_ID="your_32_char_page_id_here"

    # Run with UV:
    uv run create_notion_databases.py

Requirements:
    httpx (or requests) — we use httpx for async support later
"""

import os
import sys
import json
import httpx
from datetime import datetime

# --- Configuration ---
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID")
NOTION_VERSION = "2022-06-28"  # Stable version — avoids Data Sources breaking changes

BASE_URL = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}


def check_config():
    """Validate environment variables are set."""
    if not NOTION_API_KEY:
        print("❌ NOTION_API_KEY not set. Export it first:")
        print('   export NOTION_API_KEY="ntn_your_secret_here"')
        sys.exit(1)
    if not NOTION_PAGE_ID:
        print("❌ NOTION_PAGE_ID not set. Export it first:")
        print('   export NOTION_PAGE_ID="your_32_char_page_id_here"')
        sys.exit(1)
    print(f"✅ Config loaded")
    print(f"   Page ID: {NOTION_PAGE_ID[:8]}...{NOTION_PAGE_ID[-4:]}")
    print(f"   API Key: {NOTION_API_KEY[:8]}...{NOTION_API_KEY[-4:]}")
    print()


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


def create_sources_database(client: httpx.Client) -> str:
    """Create the Sources reference database."""
    properties = {
        "Source Name": {"title": {}},
        "Source Type": {
            "select": {
                "options": [
                    {"name": "Government Register", "color": "blue"},
                    {"name": "Tender Portal", "color": "green"},
                    {"name": "Business Directory", "color": "yellow"},
                    {"name": "Social Media", "color": "purple"},
                    {"name": "Crime Stats", "color": "red"},
                    {"name": "Other", "color": "gray"},
                ]
            }
        },
        "URL": {"url": {}},
        "POPIA Status": {
            "select": {
                "options": [
                    {"name": "Compliant", "color": "green"},
                    {"name": "Caution Required", "color": "yellow"},
                    {"name": "Blocked", "color": "red"},
                ]
            }
        },
        "Status": {
            "select": {
                "options": [
                    {"name": "Active", "color": "green"},
                    {"name": "Paused", "color": "yellow"},
                    {"name": "Broken", "color": "red"},
                    {"name": "Deprecated", "color": "gray"},
                ]
            }
        },
        "Last Crawled": {"date": {}},
        "Notes": {"rich_text": {}},
    }

    return create_database(client, "Sources", "🔗", properties)


def create_batches_database(client: httpx.Client) -> str:
    """Create the Batches operations database."""
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

    return create_database(client, "Batches", "⚙️", properties)


def create_leads_database(
    client: httpx.Client,
    sources_db_id: str,
    batches_db_id: str,
) -> str:
    """Create the Leads primary database with all fields including QA workflow."""
    properties = {
        # --- Identity ---
        "Company Name": {"title": {}},
        "CIPC Reg Number": {"rich_text": {}},
        "Industry": {
            "select": {
                "options": [
                    {"name": "Transport & Logistics", "color": "blue"},
                    {"name": "Construction", "color": "brown"},
                    {"name": "Agriculture", "color": "green"},
                    {"name": "Food & Catering", "color": "orange"},
                    {"name": "Mining", "color": "gray"},
                    {"name": "Rental Services", "color": "purple"},
                    {"name": "Medical/Pharma", "color": "pink"},
                    {"name": "Government", "color": "yellow"},
                    {"name": "Retail & Distribution", "color": "red"},
                    {"name": "Services", "color": "default"},
                    {"name": "Other", "color": "gray"},
                ]
            }
        },
        "Segment": {
            "select": {
                "options": [
                    {"name": "B2B", "color": "blue"},
                    {"name": "B2C", "color": "green"},
                ]
            }
        },
        "Province": {
            "select": {
                "options": [
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
            }
        },
        "City / Area": {"rich_text": {}},
        "Website": {"url": {}},
        "LinkedIn URL": {"url": {}},
        "Public Contact": {"rich_text": {}},

        # --- Prospect Profile (QA-Critical) ---
        "Prospect Summary": {"rich_text": {}},
        "Company Profile": {"rich_text": {}},
        "Fleet Assessment": {"rich_text": {}},
        "Tracking Need Reasoning": {"rich_text": {}},
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
        "Fleet Likelihood": {"number": {"format": "number"}},
        "Est. Fleet Size": {
            "select": {
                "options": [
                    {"name": "Small (1-5)", "color": "gray"},
                    {"name": "Medium (6-20)", "color": "yellow"},
                    {"name": "Large (20+)", "color": "green"},
                    {"name": "Unknown", "color": "default"},
                ]
            }
        },
        "Tracking Need Score": {"number": {"format": "number"}},
        # Note: Composite Score and Quality Gate are Notion formulas —
        # these must be created manually in the Notion UI as the API
        # doesn't support formula property creation. See instructions below.

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
                    {"name": "Incomplete profile", "color": "yellow"},
                    {"name": "Already a customer", "color": "gray"},
                    {"name": "Not relevant industry", "color": "orange"},
                    {"name": "Too small", "color": "red"},
                    {"name": "Out of service area", "color": "purple"},
                    {"name": "Poor data quality", "color": "brown"},
                    {"name": "Other", "color": "default"},
                ]
            }
        },

        # --- Pipeline Tracking ---
        "Date Found": {"date": {}},
        "Date Sent": {"date": {}},
        "Call Centre Feedback": {"rich_text": {}},
        "Notes": {"rich_text": {}},

        # --- Relations ---
        "Source": {
            "relation": {
                "database_id": sources_db_id,
                "single_property": {},  # Single relation (one source per lead)
            }
        },
        "Batch": {
            "relation": {
                "database_id": batches_db_id,
                "single_property": {},
            }
        },
    }

    return create_database(client, "Leads", "🎯", properties)


def seed_sources(client: httpx.Client, sources_db_id: str):
    """Seed the Sources database with initial data sources."""
    sources = [
        {
            "Source Name": "CIPC Registrations",
            "Source Type": "Government Register",
            "URL": "https://eservices.cipc.co.za",
            "POPIA Status": "Compliant",
            "Status": "Active",
        },
        {
            "Source Name": "eTenders Portal",
            "Source Type": "Tender Portal",
            "URL": "https://www.etenders.gov.za",
            "POPIA Status": "Compliant",
            "Status": "Active",
        },
        {
            "Source Name": "Yellow Pages SA",
            "Source Type": "Business Directory",
            "URL": "https://www.yellowpages.co.za",
            "POPIA Status": "Compliant",
            "Status": "Active",
        },
        {
            "Source Name": "LinkedIn Company Pages",
            "Source Type": "Social Media",
            "URL": "https://www.linkedin.com",
            "POPIA Status": "Caution Required",
            "Status": "Active",
            "Notes": "Public company pages only. Never scrape personal profiles.",
        },
        {
            "Source Name": "SAPS Crime Stats",
            "Source Type": "Crime Stats",
            "URL": "https://www.saps.gov.za/services/crimestats.php",
            "POPIA Status": "Compliant",
            "Status": "Active",
            "Notes": "Vehicle theft hotspot data by area. Used for scoring, not lead sourcing.",
        },
        {
            "Source Name": "Road Freight Association",
            "Source Type": "Business Directory",
            "URL": "https://www.rfa.co.za",
            "POPIA Status": "Compliant",
            "Status": "Active",
            "Notes": "Member directory — transport and logistics companies.",
        },
    ]

    print(f"\n📝 Seeding Sources database with {len(sources)} initial sources...")

    for source in sources:
        properties = {
            "Source Name": {
                "title": [{"text": {"content": source["Source Name"]}}]
            },
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
    """Print steps that must be done manually in the Notion UI."""
    print()
    print("=" * 60)
    print("📋 MANUAL STEPS REQUIRED IN NOTION UI")
    print("=" * 60)
    print()
    print("The Notion API doesn't support creating formula properties")
    print("or rollup properties. You need to add these manually:")
    print()
    print("1. COMPOSITE SCORE (Leads database)")
    print("   - Open the Leads database")
    print("   - Click '+' to add a new property")
    print("   - Type: Formula")
    print("   - Name: Composite Score")
    print("   - Formula:")
    print('     prop("Fleet Likelihood") * 0.4 + prop("Tracking Need Score") * 0.4 + if(prop("Est. Fleet Size") == "Large (20+)", 2, if(prop("Est. Fleet Size") == "Medium (6-20)", 1, 0)) * 0.2')
    print()
    print("2. QUALITY GATE (Leads database)")
    print("   - Add another Formula property")
    print("   - Name: Quality Gate")
    print("   - Formula:")
    print('     if(prop("Composite Score") >= 7, "✅ Auto-Approve", if(prop("Composite Score") >= 4, "⚠️ Review", "❌ Auto-Reject"))')
    print()
    print("3. QA REVIEWED BY (Leads database)")
    print("   - Add a Person property")
    print("   - Name: QA Reviewed By")
    print()
    print("4. LEADS GENERATED (Sources database)")
    print("   - Add a Rollup property")
    print("   - Name: Leads Generated")
    print("   - Relation: Leads (the reverse relation)")
    print("   - Property: (any)")
    print("   - Calculate: Count all")
    print()
    print("5. QA APPROVED (Batches database)")
    print("   - Add a Rollup property")
    print("   - Name: QA Approved")
    print("   - Relation: Leads")
    print("   - Property: Status")
    print("   - Calculate: Count values where Status = 'QA Approved'")
    print()
    print("6. CREATE VIEWS (see SETUP_GUIDE.md for the full list)")
    print("   Priority views to create first:")
    print("   - 🔍 QA Queue (Table: Status = Pending QA)")
    print("   - ✅ Approved — Ready to Send (Table: Status = QA Approved)")
    print("   - 📋 Full Pipeline (Kanban: grouped by Status)")
    print("   - ⚙️ Batch Monitor (Batches DB, sorted by Run Date)")
    print()


def print_database_ids(sources_id: str, batches_id: str, leads_id: str):
    """Print the database IDs for use in n8n and OpenClaw config."""
    print()
    print("=" * 60)
    print("🔑 DATABASE IDs — SAVE THESE FOR n8n CONFIGURATION")
    print("=" * 60)
    print()
    print(f"  LEADS_DB_ID    = {leads_id}")
    print(f"  SOURCES_DB_ID  = {sources_id}")
    print(f"  BATCHES_DB_ID  = {batches_id}")
    print()
    print("Add these to your n8n environment variables or credential store.")
    print()

    # Also write to a file for easy reference
    config = {
        "leads_database_id": leads_id,
        "sources_database_id": sources_id,
        "batches_database_id": batches_id,
        "notion_api_version": NOTION_VERSION,
        "created_at": datetime.now().isoformat(),
    }
    with open("notion_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print("💾 Database IDs saved to notion_config.json")


def main():
    print()
    print("🚀 Notion Database Setup — AI Lead Generation System")
    print("=" * 60)
    print()

    check_config()

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

        # Create databases in dependency order
        print("📦 Creating databases...")
        print("-" * 40)

        # 1. Sources first (no dependencies)
        sources_db_id = create_sources_database(client)

        # 2. Batches second (no dependencies)
        batches_db_id = create_batches_database(client)

        # 3. Leads last (depends on Sources and Batches for relations)
        leads_db_id = create_leads_database(client, sources_db_id, batches_db_id)

        # 4. Seed initial source data
        seed_sources(client, sources_db_id)

        # 5. Output results
        print_database_ids(sources_db_id, batches_db_id, leads_db_id)
        print_manual_steps(leads_db_id)

    print("🎉 Setup complete! Your Notion workspace is ready.")
    print("   Next: Complete the manual steps above, then build the n8n workflow.")
    print()


if __name__ == "__main__":
    main()
