// ===========================================
// B2C Lead Ingestion — Direct Notion API (n8n)
// ===========================================

// CONFIGURE THESE THREE VALUES:
const NOTION_API_KEY = process.env.NOTION_API_KEY; // Set in n8n → Settings → Environment Variables
const B2C_LEADS_DB_ID = '32089024-cd3d-812e-a6c6-d8e21d9126b3';
const B2C_BATCHES_DB_ID = '32089024-cd3d-81a7-8691-ca999aa1494f';

// ===========================================

const NOTION_VERSION = '2022-06-28';
const BASE_URL = 'https://api.notion.com/v1';
const SEGMENT = 'B2C';

// Capture `this` at the top level where it is valid in n8n Code nodes
const helpers = this.helpers;

// Helper: Notion API call using n8n's built-in this.helpers.httpRequest()
async function notionRequest(method, path, body) {
  const options = {
    method,
    url: `${BASE_URL}${path}`,
    headers: {
      'Authorization': `Bearer ${NOTION_API_KEY}`,
      'Content-Type': 'application/json',
      'Notion-Version': NOTION_VERSION,
    },
    json: true,
  };
  if (body !== undefined) {
    options.body = body;
  }
  return await helpers.httpRequest(options);
}

// Get the incoming data — n8n webhook delivers payload under .body
const body = $input.first().json.body;

if (!body || !body.batch_id || !body.leads || !body.leads.length) {
  return [{ json: { status: 'error', message: 'Invalid payload: missing batch_id or leads array' } }];
}

if (body.segment && body.segment !== SEGMENT) {
  return [{ json: { status: 'error', message: `Wrong segment: expected B2C, got ${body.segment}` } }];
}

const batchId = body.batch_id;
const leads = body.leads;
let created = 0;
let duplicates = 0;
let errors = [];
let batchPageId = null;

// --- Step 1: Create B2C Batch Record ---
try {
  const batchPage = await notionRequest('POST', '/pages', {
    parent: { database_id: B2C_BATCHES_DB_ID },
    properties: {
      'Batch ID': { title: [{ text: { content: batchId } }] },
      'Run Date': { date: { start: new Date().toISOString() } },
      'Status': { select: { name: 'Running' } },
      'Leads Found': { number: leads.length },
    },
  });
  batchPageId = batchPage.id;
} catch (e) {
  errors.push(`Batch creation error: ${e.message}`);
}

// --- Step 2: Process each B2C lead ---
for (const lead of leads) {
  try {
    // B2C dedup: by intent_source_url only
    // Same post URL = same lead (duplicate). Same person posting again = new URL = new lead.
    if (lead.intent_source_url) {
      const searchData = await notionRequest('POST', `/databases/${B2C_LEADS_DB_ID}/query`, {
        filter: {
          property: 'Intent Source URL',
          url: { equals: lead.intent_source_url },
        },
        page_size: 1,
      });

      if (searchData.results && searchData.results.length > 0) {
        duplicates++;
        continue;
      }
    }

    // Build Notion page properties
    const properties = {
      'Full Name': { title: [{ text: { content: lead.full_name || 'Unknown' } }] },
      'Status': { select: { name: 'Pending QA' } },
      'Date Added': { date: { start: new Date().toISOString() } },
    };

    // Phone and email (dedicated Notion property types)
    if (lead.phone) properties['Phone'] = { phone_number: lead.phone };
    if (lead.email) properties['Email'] = { email: lead.email };

    // URL fields
    if (lead.intent_source_url) properties['Intent Source URL'] = { url: lead.intent_source_url };

    // Date fields
    if (lead.intent_date) {
      properties['Intent Date'] = { date: { start: lead.intent_date } };
    }

    // Rich text fields
    const textFields = {
      'City / Area': lead.city,
      'Intent Signal': lead.intent_signal,
      'Vehicle Make / Model': lead.vehicle_make_model,
      'Call Script Opener': lead.call_script_opener,
      'Sources Used': lead.sources_used,
      'Dispute Reason': lead.dispute_reason,
    };

    for (const [key, value] of Object.entries(textFields)) {
      if (value) {
        properties[key] = { rich_text: [{ text: { content: String(value).substring(0, 2000) } }] };
      }
    }

    // Select fields
    const selectFields = {
      'Province': lead.province,
      'Intent Source': lead.intent_source,
      'Data Confidence': lead.data_confidence,
    };

    for (const [key, value] of Object.entries(selectFields)) {
      if (value) {
        properties[key] = { select: { name: value } };
      }
    }

    // Number fields
    if (lead.intent_strength != null) {
      properties['Intent Strength'] = { number: lead.intent_strength };
    }
    if (lead.urgency_score != null) {
      properties['Urgency Score'] = { number: lead.urgency_score };
    }
    if (lead.vehicle_year != null) {
      properties['Vehicle Year'] = { number: lead.vehicle_year };
    }

    // Batch relation
    if (batchPageId) {
      properties['Batch'] = { relation: [{ id: batchPageId }] };
    }

    // Create the B2C lead page
    await notionRequest('POST', '/pages', {
      parent: { database_id: B2C_LEADS_DB_ID },
      properties,
    });

    created++;

  } catch (e) {
    errors.push(`Error processing ${lead.full_name}: ${e.message}`);
  }
}

// --- Step 3: Update B2C batch record ---
try {
  if (batchPageId) {
    await notionRequest('PATCH', `/pages/${batchPageId}`, {
      properties: {
        'Status': { select: { name: errors.length > 0 ? 'Partial' : 'Completed' } },
        'Leads After Dedup': { number: created },
        'Errors': errors.length > 0
          ? { rich_text: [{ text: { content: errors.join('; ').substring(0, 2000) } }] }
          : { rich_text: [] },
      },
    });
  }
} catch (e) {
  errors.push(`Batch update error: ${e.message}`);
}

// Return result
return [{
  json: {
    status: errors.length > 0 ? 'partial' : 'success',
    segment: SEGMENT,
    batch_id: batchId,
    leads_found: leads.length,
    leads_created: created,
    duplicates_skipped: duplicates,
    errors: errors,
  }
}];
