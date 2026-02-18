// ===========================================

// Lead Ingestion — Direct Notion API (n8n)

// ===========================================

// CONFIGURE THESE THREE VALUES:

const NOTION_API// ===========================================

// Lead Ingestion — Direct Notion API (n8n)

// ===========================================

// CONFIGURE THESE THREE VALUES:

const NOTION_API_KEY = process.env.NOTION_API_KEY || 'YOUR_NOTION_API_KEY';

const LEADS_DB_ID = '30b89024-cd3d-8123-94f7-ee27b966bc0d';

const BATCHES_DB_ID = '30b89024-cd3d-8198-bb49-ec8e3e9fe40e';

// ===========================================



const NOTION_VERSION = '2022-06-28';

const BASE_URL = 'https://api.notion.com/v1';



const baseOptions = {

  headers: {

    'Authorization': `Bearer ${NOTION_API_KEY}`,

    'Content-Type': 'application/json',

    'Notion-Version': NOTION_VERSION,

  },

  returnFullResponse: false,

  json: true,

};



// Get the incoming data

const body = $input.first().json.body;



if (!body || !body.batch_id || !body.leads || !body.leads.length) {

  return [{ json: { status: 'error', message: 'Invalid payload' } }];

}



const batchId = body.batch_id;

const leads = body.leads;

let created = 0;

let duplicates = 0;

let errors = [];



// --- Step 1: Create Batch Record ---
[<32;22;26M
try {

  await $http.request({

    method: 'POST',
[<32;58;27M
    url: `${BASE_URL}/pages`,

    body: {

      parent: { database_id: BATCHES_DB_ID },

      properties: {

        'Batch ID': { title: [{ text: { content: batchId } }] },

        'Run Date': { date: { start: new Date().toISOString() } },

        'Status': { select: { name: 'Running' } },

        'Leads Found': { number: leads.length },

      },

    },

    ...baseOptions,

  });

} catch (e) {

  errors.push(`Batch creation error: ${e.message}`);

}



// --- Step 2: Process each lead ---

for (const lead of leads) {

  try {

    // Dedup check: search for existing company name

    const searchData = await $http.request({

      method: 'POST',

      url: `${BASE_URL}/databases/${LEADS_DB_ID}/query`,

      body: {

        filter: {

          property: 'Company Name',

          title: { equals: lead.company_name },

        },

        page_size: 1,

      },

      ...baseOptions,

    });



    if (searchData.results && searchData.results.length > 0) {

      duplicates++;

      continue;

    }



    // Build the Notion page properties

    const properties = {

      'Company Name': { title: [{ text: { content: lead.company_name || '' } }] },

      'Status': { select: { name: 'Pending QA' } },

      'Date Found': { date: { start: new Date().toISOString() } },

    };



    // Text fields

    const textFields = {

      'CIPC Reg Number': lead.cipc_reg,

      'City / Area': lead.city,

      'Public Contact': lead.contact,

      'Prospect Summary': lead.prospect_summary,

      'Company Profile': lead.company_profile,

      'Fleet Assessment': lead.fleet_assessment,

      'Tracking Need Reasoning': lead.tracking_reasoning,

      'Call Script Opener': lead.call_script_opener,

      'Sources Used': lead.sources_used,

    };



    for (const [key, value] of Object.entries(textFields)) {

      if (value) {

        properties[key] = { rich_text: [{ text: { content: value } }] };

      }

    }



    // URL fields

    if (lead.website) properties['Website'] = { url: lead.website };

    if (lead.linkedin) properties['LinkedIn URL'] = { url: lead.linkedin };



    // Select fields

    const selectFields = {

      'Industry': lead.industry,

      'Segment': lead.segment,

      'Province': lead.province,

      'Est. Fleet Size': lead.fleet_size,

      'Data Confidence': lead.data_confidence,

    };



    for (const [key, value] of Object.entries(selectFields)) {

      if (value) {

        properties[key] = { select: { name: value } };

      }

    }



    // Number fields

    if (lead.fleet_likelihood != null) {

      properties['Fleet Likelihood'] = { number: lead.fleet_likelihood };

    }

    if (lead.tracking_need != null) {

      properties['Tracking Need Score'] = { number: lead.tracking_need };

    }



    // Create the lead page

    await $http.request({

      method: 'POST',

      url: `${BASE_URL}/pages`,

      body: {

        parent: { database_id: LEADS_DB_ID },

        properties,

      },

      ...baseOptions,

    });



    created++;



  } catch (e) {

    errors.push(`Error processing ${lead.company_name}: ${e.message}`);

  }

}



// --- Step 3: Update batch record ---

try {

  const batchData = await $http.request({

    method: 'POST',

    url: `${BASE_URL}/databases/${BATCHES_DB_ID}/query`,

    body: {

      filter: {

        property: 'Batch ID',

        title: { equals: batchId },

      },

      page_size: 1,

    },

    ...baseOptions,

  });



  if (batchData.results && batchData.results.length > 0) {

    const batchPageId = batchData.results[0].id;



    await $http.request({

      method: 'PATCH',

      url: `${BASE_URL}/pages/${batchPageId}`,

      body: {

        properties: {

          'Status': { select: { name: errors.length > 0 ? 'Partial' : 'Completed' } },

          'Leads After Dedup': { number: created },

          'Errors': errors.length > 0

            ? { rich_text: [{ text: { content: errors.join('; ').substring(0, 2000) } }] }

            : { rich_text: [] },

        },

      },

      ...baseOptions,

    });

  }

} catch (e) {

  errors.push(`Batch update error: ${e.message}`);

}



// Return result

return [{

  json: {

    status: errors.length > 0 ? 'partial' : 'success',

    batch_id: batchId,

    leads_found: leads.length,

    leads_created: created,

    duplicates_skipped: duplicates,

    errors: errors,

  }

}];
