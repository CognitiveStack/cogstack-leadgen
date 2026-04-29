"""
Claire-Prospects Notion Database Setup Script
=============================================
Creates the Claire-Prospects database for WhatsApp outreach tracking.
Written directly via the Notion API — does NOT go through n8n.

Run once before using whatsapp_outreach.py.

Usage:
    uv run python create_claire_prospects_db.py

Requirements:
    NOTION_API_KEY and NOTION_PAGE_ID in .env
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


def check_config():
    """Validate environment variables are present."""
    if not NOTION_API_KEY:
        print("❌ NOTION_API_KEY not set. Export it first:")
        print('   export NOTION_API_KEY="ntn_your_secret_here"')
        sys.exit(1)
    if not NOTION_PAGE_ID:
        print("❌ NOTION_PAGE_ID not set. Export it first:")
        print('   export NOTION_PAGE_ID="your_32_char_page_id_here"')
        sys.exit(1)

    print("✅ Config loaded")
    print(f"   Page ID:    {NOTION_PAGE_ID[:8]}...{NOTION_PAGE_ID[-4:]}")
    print(f"   API Key:    {NOTION_API_KEY[:8]}...{NOTION_API_KEY[-4:]}")
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


def create_claire_prospects_database(client: httpx.Client) -> str:
    """Create the Claire-Prospects outreach tracking database."""
    properties = {
        "Full Name": {"title": {}},
        "Phone": {"phone_number": {}},
        "Email": {"email": {}},
        "Business": {"rich_text": {}},
        "Motivation": {"rich_text": {}},
        "Outreach Message": {"rich_text": {}},
        "Outreach Sent At": {"date": {}},
        "Response": {"rich_text": {}},
        "Response Status": {
            "select": {
                "options": [
                    {"name": "Pending",  "color": "gray"},
                    {"name": "Yes",      "color": "green"},
                    {"name": "No",       "color": "red"},
                    {"name": "Maybe",    "color": "yellow"},
                    {"name": "No Reply", "color": "orange"},
                ]
            }
        },
        "Response At": {"date": {}},
        "Submitted to Pipeline": {"checkbox": {}},
        "Date Added": {"date": {}},
    }

    return create_database(client, "Claire-Prospects", "📱", properties)


def print_manual_steps(db_id: str):
    """Print Notion UI steps that cannot be done via API."""
    print()
    print("=" * 60)
    print("📋 MANUAL STEPS REQUIRED IN NOTION UI")
    print("=" * 60)
    print()
    print("Create these views in the Claire-Prospects database:")
    print()
    print("1. ACTIVE OUTREACH")
    print("   Table | Filter: Response Status = 'Pending'")
    print("   Sort: Outreach Sent At ASC")
    print()
    print("2. WARM LEADS")
    print("   Table | Filter: Response Status = 'Yes' OR 'Maybe'")
    print()
    print("3. ALL PROSPECTS")
    print("   Table | No filter — full view")
    print()


def print_database_ids(db_id: str):
    """Print and save Claire-Prospects DB ID, merging with existing notion_config.json."""
    print()
    print("=" * 60)
    print("🔑 CLAIRE-PROSPECTS DATABASE ID")
    print("=" * 60)
    print()
    print(f"  CLAIRE_PROSPECTS_DB_ID = {db_id}")
    print()

    config = {}
    if os.path.exists("notion_config.json"):
        with open("notion_config.json") as f:
            config = json.load(f)

    config["claire_prospects_db_id"] = db_id
    config["claire_prospects_created_at"] = datetime.now().isoformat()

    with open("notion_config.json", "w") as f:
        json.dump(config, f, indent=2)

    print("💾 ID merged into notion_config.json (existing IDs preserved)")


def main():
    print()
    print("🚀 Claire-Prospects Notion Database Setup")
    print("=" * 60)
    print()

    check_config()

    with httpx.Client(headers=HEADERS, timeout=30.0) as client:
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

        print("📦 Creating Claire-Prospects database...")
        print("-" * 40)

        db_id = create_claire_prospects_database(client)

        print_database_ids(db_id)
        print_manual_steps(db_id)

    print("🎉 Setup complete!")
    print("   Next: Run whatsapp_outreach.py --dry-run --max 5 to validate.")
    print()


if __name__ == "__main__":
    main()
