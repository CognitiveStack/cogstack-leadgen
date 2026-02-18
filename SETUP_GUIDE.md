# Notion Workspace Setup Guide
# AI Lead Generation System — Cogstack & Claire Shuttleworth
# ============================================================

## Step 1: Create the Notion Workspace (Manual — 5 minutes)

1. Go to https://www.notion.so/signup
2. Create a **new workspace** (don't use a personal one)
   - Workspace name: "Lead Generation — Cogstack"
   - Choose the **Free plan** to start (upgrade later if needed)
3. Invite collaborators:
   - Claire Shuttleworth → **Editor** role (can edit, create views, update statuses)
   - Paul → **Commenter** role (can view all data, add comments)

## Step 2: Create a Top-Level Page

1. In the workspace sidebar, create a new page called **"AI Lead Pipeline"**
2. This page will be the parent for all three databases
3. Note down the **Page ID** — it's the 32-character string at the end of the URL:
   ```
   https://www.notion.so/AI-Lead-Pipeline-<THIS_IS_THE_PAGE_ID>
   ```
   Remove any hyphens to get the raw ID.

## Step 3: Create the Notion Integration (Manual — 3 minutes)

1. Go to https://www.notion.so/profile/integrations
2. Click **"+ New integration"**
3. Settings:
   - Name: "Cogstack Lead Ingestion"
   - Associated workspace: "Lead Generation — Cogstack"
   - Capabilities: **Read content**, **Update content**, **Insert content**
4. Click **Submit**
5. Copy the **Internal Integration Secret** (starts with `ntn_...`)
6. **CRITICAL**: Go back to your "AI Lead Pipeline" page in Notion:
   - Click the `...` menu (top right)
   - Click **"+ Add Connections"**
   - Search for "Cogstack Lead Ingestion" and select it
   - This gives the API permission to access this page and its children

## Step 4: Set Environment Variables

Create a `.env` file (or add to your existing one):

```bash
NOTION_API_KEY=ntn_your_secret_here
NOTION_PAGE_ID=your_32_char_page_id_here
```

## Step 5: Run the Database Creation Script

```bash
# Using UV (your preferred package manager)
uv run create_notion_databases.py
```

This will create all three databases (Leads, Sources, Batches) with the
full schema from the design document, including all properties, select
options, and relation links.

## Step 6: Create the Views (Manual — but guided)

After the script creates the databases, you'll need to create views
manually in Notion (the API doesn't support creating views).

See the schema document Section 6 for the full list of views to create.
The most important ones to set up first:

### QA Queue (Claire's daily view)
- Open the Leads database
- Click "+ New view" → Table
- Name: "🔍 QA Queue"  
- Filter: Status = "Pending QA"
- Sort: Composite Score — Descending
- Show columns: Company Name, Industry, Province, Composite Score,
  Prospect Summary, Fleet Assessment, Data Confidence

### Approved — Ready to Send
- New view → Table
- Name: "✅ Approved — Ready to Send"
- Filter: Status = "QA Approved"
- Sort: Date Found — Ascending

### Full Pipeline (Kanban)
- New view → Board
- Name: "📋 Full Pipeline"
- Group by: Status

### Batch Monitor (for you, Charles)
- Open the Batches database
- New view → Table
- Name: "⚙️ Batch Monitor"
- Sort: Run Date — Descending
