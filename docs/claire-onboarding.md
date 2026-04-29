# Welcome to the AI Lead Pipeline — QA Reviewer Guide

Hi Claire 👋

This document explains everything you need to know to review and approve leads in the Cogstack AI Lead Pipeline.

---

## What Is Notion?

**Notion** is an all-in-one workspace that combines notes, databases, and collaboration in one place. Think of it as a smart spreadsheet where each row can be opened like a document and fields can be linked across tables.

You access it in your browser at [notion.so](https://notion.so) — no software to install. It works on your phone too.

**Why Notion for this pipeline:**
- It gives you a clean, visual interface to review leads without needing to touch any code or spreadsheets
- Each lead is a rich page — you can see all the research Hugo did, click through to websites, and leave feedback notes
- The databases are linked — a lead knows which batch it came from, a batch knows how many leads it contains
- It's easy to share with Paul's call centre team, with fine-grained control over who can see or edit what

---

## How Notion Fits Into the Pipeline

Here is how a lead travels from discovery to your phone call:

```
Hugo (AI agent on Raspberry Pi)
    │
    │  Searches the web for SA companies
    │  Scores and enriches each prospect
    │  Builds a structured batch of leads
    │
    ▼
n8n Webhook (automation server)
    │
    │  Validates the payload
    │  Checks for duplicates
    │  Creates records in Notion
    │
    ▼
Notion — AI Lead Pipeline
    │
    ├── Leads DB       ← YOU WORK HERE (QA review)
    ├── Batches DB     ← Audit trail of Hugo's runs
    └── Sources DB     ← Reference: where Hugo searches
    │
    ▼
Claire reviews → QA Approved
    │
    ▼
Paul's Call Centre → Contacted → Converted / Not Interested
```

**Your role is the quality gate** — you are the human check between the AI and the call centre. Nothing reaches Paul's team without your approval.

---

## Your Notion Workspace

You have access to the **AI Lead Pipeline** section. The three databases are:

| Database | Purpose |
|---|---|
| **Leads** | Every company Hugo has found — this is where you spend your time |
| **Batches** | A log of each time Hugo ran a search run |
| **Sources** | The data sources Hugo uses (CIPC, Yellow Pages, eTenders, etc.) |

### The Leads Database
This is your main workspace. Each row is one company Hugo found. Click any row to open the full lead record with all the research.

### The Batches Database
Each row represents one search run by Hugo — it records:
- **Batch ID** — a unique ID like `BATCH-HUGO-2026-02-20-004`
- **Run Date** — when Hugo ran the search
- **Leads Found** — how many companies he found
- **Leads After Dedup** — how many were new (not already in the system)
- **Status** — Running / Completed / Partial / Failed
- **Errors** — any problems Hugo encountered

**How to trace a lead back to its batch:** In the Leads database, click the value in the **Batch** column — it opens the batch record showing exactly when it was run and what Hugo was searching for that day.

### The Sources Database
Reference data about where Hugo searches — CIPC, Yellow Pages SA, eTenders portal, Road Freight Association, etc. You don't need to work in this database, but it helps you understand where a lead's data came from.

---

## The QA Queue View

In the **Leads** database, click the **"QA Queue"** view. This filters to only show leads waiting for your review (Status = Pending QA) — so you're not distracted by leads already processed.

---

## Reviewing a Lead

Click on any lead to open it. You'll see:

| Field | What it means |
|---|---|
| **Company Name** | The company Hugo found |
| **Prospect Summary** | Hugo's 2-3 sentence summary of why this is a good prospect |
| **Fleet Assessment** | Estimated number and type of vehicles |
| **Tracking Need Reasoning** | Specific reasons why they need tracking |
| **Call Script Opener** | A suggested opening line for the cold call |
| **Data Confidence** | High / Medium / Low — how sure Hugo is about the data |
| **Fleet Likelihood** | Score 0-10: how likely they operate a vehicle fleet |
| **Tracking Need Score** | Score 0-10: how urgently they need tracking |
| **Composite Score** | The overall score — see formula below |
| **Est. Fleet Size** | Small (1-5) / Medium (6-20) / Large (21+) |
| **Industry** | Sector (Transport, Construction, Agriculture, etc.) |
| **Province / City** | Where they operate |
| **Website / LinkedIn** | Links to verify the company |
| **Public Contact** | Phone or email for the call centre to use |
| **CIPC Reg Number** | Company registration number (verify at cipc.co.za if needed) |
| **Batch** | Which Hugo search run this lead came from |

---

## Your Decision: Approve or Reject

After reading the lead, update the **Status** field:

| Status | When to use |
|---|---|
| **QA Approved** | Looks legitimate, fleet is plausible, worth a call |
| **QA Rejected** | Sole trader, wrong industry, bad data, or not worth calling |
| **Duplicate** | Same company submitted twice |

You can also leave a note in **Call Centre Feedback** — e.g. "check website before calling" or "CIPC reg looks suspicious."

---

## What Makes a Good Lead?

Hugo scores leads on two dimensions. As a rough guide:

- **Fleet Likelihood 7+** and **Tracking Need 6+** = strong lead, approve unless something looks off
- **Fleet Likelihood 5-6** = borderline, use your judgment
- **Fleet Likelihood < 5** = usually reject unless there's a specific reason

**Good signals:**
- Transport, logistics, construction, agriculture, waste management, security companies
- Multiple vehicles mentioned on their website
- Operating in high-theft areas (JHB, Cape Town, Durban)
- Government tender wins for delivery/supply contracts
- Cold chain / refrigerated transport

**Red flags:**
- Solo operator or home-based business
- No website, no CIPC number, single directory listing
- Industry doesn't match (e.g. an IT company)
- Data Confidence = Low with no corroborating info

---

## Scoring Reference (Composite Score)

Hugo calculates a Composite Score for each lead:

```
(Fleet Likelihood × 0.4) + (Tracking Need × 0.4) + (Fleet Size Bonus × 0.2)
```

Fleet Size Bonus: Small = 0, Medium = 1, Large = 2

A score of **7+** is a strong lead. **4-6** is borderline. **Below 4** Hugo usually filters out before sending.

---

## Questions?

Contact Charles on WhatsApp: **+27836177469**

---

*This pipeline is automated — Hugo runs searches automatically several times per week. New leads will appear in your QA Queue without you needing to do anything to trigger it.*
