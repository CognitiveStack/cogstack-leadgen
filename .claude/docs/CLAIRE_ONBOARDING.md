# Welcome to the AI Lead Pipeline — QA Reviewer Guide

Hi Claire 👋

This document explains everything you need to know to review and approve leads in the Cogstack AI Lead Pipeline.

---

## What Is This?

An AI agent called **Hugo** automatically finds South African companies that are likely to need vehicle tracking services. He researches each company, scores them, and adds them to this Notion workspace for your review.

Your job is simple: **look at each lead, decide if it's worth calling, and mark it Approved or Rejected.**

The call centre (Paul's team) only sees leads you've approved.

---

## Your Notion Workspace

You have access to the **AI Lead Pipeline** section in Notion. The key pages are:

| Page | What it's for |
|---|---|
| **Leads** | All leads Hugo has found — this is where you work |
| **Batches** | A log of each time Hugo ran a search (for reference) |
| **Sources** | The data sources Hugo uses (for reference) |

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
| **Est. Fleet Size** | Small (1-5) / Medium (6-20) / Large (21+) |
| **Industry** | Sector (Transport, Construction, Agriculture, etc.) |
| **Province / City** | Where they operate |
| **Website / LinkedIn** | Links to verify the company |
| **Public Contact** | Phone or email for the call centre to use |
| **CIPC Reg Number** | Company registration number (verify at cipc.co.za if needed) |

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
