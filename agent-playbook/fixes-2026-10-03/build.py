"""Builds the fixed n8n workflow exports for the RealEstateInvestor pipeline.

Each workflow keeps the node names, webhook paths, credential references and
cross-workflow IDs of the live exports (2026-10-03) so it can be imported into
the existing workflow in place. Only the changes listed in CHANGES.md differ.
"""
import json, os

OUT = os.path.dirname(os.path.abspath(__file__))

ANTHROPIC_CRED = {"anthropicApi": {"id": "9aisnVU8hkPDQDUR", "name": "Anthropic account"}}
BRIGHTDATA_CRED = {"httpHeaderAuth": {"id": "4gNuBXdzHsOTzczk", "name": "Bright Data-Datasets API"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "R6UIxy7KGJ6rVGyY", "name": "Google Sheets account"}}
SHEET_ID = "1A_160yTDK5HQejwSA6LsViaQfoNilaxw9q8lg40ZyWY"
ZILLOW_WF = "5MIjR1WcvWIbqhjj"
AIRBNB_WF = "ZikKb3g2jC8jfErn"
PUBLISH_WF = "ITZ1EvjozAxRBAic"
SETTINGS = {"executionOrder": "v1", "binaryMode": "separate", "availableInMCP": False}

# Shared: map a place/address to one of the researched market keys used by the
# Report Agent's reference tables. A name only counts when the state matches.
MARKET_JS = r"""const MARKETS = [
  { market: 'Park City, UT', state: 'UT', names: ['park city', 'deer valley', 'snyderville', 'kimball junction'] },
  { market: 'Steamboat Springs, CO', state: 'CO', names: ['steamboat'] },
  { market: 'Jackson Hole, WY', state: 'WY', names: ['jackson', 'teton village', 'wilson'] },
  { market: 'Vail, CO', state: 'CO', names: ['vail', 'avon', 'edwards', 'beaver creek', 'minturn'] }
];
function resolveMarket(...texts) {
  for (const t of texts) {
    const s = String(t || '').toLowerCase();
    if (!s) continue;
    const hit = MARKETS.find(m => new RegExp('\\b' + m.state.toLowerCase() + '\\b').test(s) && m.names.some(n => s.includes(n)));
    if (hit) return hit.market;
  }
  return null;
}
"""


def node(name, type_, version, x, y, params, **extra):
    n = {"parameters": params, "name": name, "type": type_, "typeVersion": version, "position": [x, y]}
    n.update(extra)
    return n


def main_conn(pairs):
    """pairs: list of (src, [targets for output 0], [targets for output 1]...)"""
    conns = {}
    for src, *outputs in pairs:
        conns[src] = {"main": [[{"node": t, "type": "main", "index": 0} for t in out] for out in outputs]}
    return conns


def ai_conn(conns, src, kind, target):
    conns[src] = {kind: [[{"node": target, "type": kind, "index": 0}]]}


def poll_loop(prefix_y, deadline_ms, deadline_label, cred):
    """Async snapshot polling nodes shared by both Bright Data sub-workflows (unchanged logic)."""
    return [
        node("Init Poll State", "n8n-nodes-base.code", 2, 896, 160, {
            "jsCode": "const snapshot_id = $input.first().json.snapshot_id;\nreturn [{ json: { snapshot_id, deadline: Date.now() + %d } }];\n" % deadline_ms}),
        node("Wait Before Check", "n8n-nodes-base.wait", 1.1, 1120, 160, {"amount": 20}),
        node("Check Snapshot Status", "n8n-nodes-base.httpRequest", 4.5, 1344, 160, {
            "url": "=https://api.brightdata.com/datasets/v3/progress/{{ $('Init Poll State').item.json.snapshot_id }}",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth", "options": {}},
            credentials=cred),
        node("Ready?", "n8n-nodes-base.if", 2.3, 1568, 160, {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 3},
                           "conditions": [{"id": "ready-0001", "leftValue": "={{ $json.status }}", "rightValue": "ready",
                                           "operator": {"type": "string", "operation": "equals"}}],
                           "combinator": "and"}, "options": {}}),
        node("Download Snapshot", "n8n-nodes-base.httpRequest", 4.5, 1792, 0, {
            "url": "=https://api.brightdata.com/datasets/v3/snapshot/{{ $('Init Poll State').item.json.snapshot_id }}?format=json",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth", "options": {}},
            credentials=cred, alwaysOutputData=True),
        node("Download Complete?", "n8n-nodes-base.if", 2.3, 2016, 0, {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 3},
                           "conditions": [{"id": "building-0002", "leftValue": "={{ $json.status }}", "rightValue": "building",
                                           "operator": {"type": "string", "operation": "notEquals"}}],
                           "combinator": "and"}, "options": {}}),
        node("Deadline Passed?", "n8n-nodes-base.if", 2.3, 1792, 320, {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 3},
                           "conditions": [{"id": "deadline-0003", "leftValue": "={{ Date.now() }}",
                                           "rightValue": "={{ $('Init Poll State').item.json.deadline }}",
                                           "operator": {"type": "number", "operation": "gt"}}],
                           "combinator": "and"}, "options": {}}),
        node("Timeout - No Data", "n8n-nodes-base.code", 2, 2016, 320, {
            "jsCode": "return [{ json: { candidates: [], source_count: 0, gaps: ['Bright Data snapshot did not complete within the polling deadline (%s).'] } }];\n" % deadline_label}),
    ]


SNAPSHOT_IF = lambda x, y: node("Got Snapshot ID?", "n8n-nodes-base.if", 2.3, x, y, {
    "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 3},
                   "conditions": [{"id": "snapshot-0000", "leftValue": "={{ $json.snapshot_id }}", "rightValue": "",
                                   "operator": {"type": "string", "operation": "exists", "singleValue": True}}],
                   "combinator": "and"}, "options": {}})


def poll_connections(normalize_name):
    return [
        ("Got Snapshot ID?", ["Init Poll State"], [normalize_name]),
        ("Init Poll State", ["Wait Before Check"]),
        ("Wait Before Check", ["Check Snapshot Status"]),
        ("Check Snapshot Status", ["Ready?"]),
        ("Ready?", ["Download Snapshot"], ["Deadline Passed?"]),
        ("Deadline Passed?", ["Timeout - No Data"], ["Wait Before Check"]),
        ("Download Snapshot", ["Download Complete?"]),
        ("Download Complete?", [normalize_name], ["Wait Before Check"]),
    ]


def search_node(name, dataset_id, discover_by):
    return node(name, "n8n-nodes-base.httpRequest", 4.5, 448, 0, {
        "method": "POST", "url": "https://api.brightdata.com/datasets/v3/scrape",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "dataset_id", "value": dataset_id}, {"name": "notify", "value": "false"},
            {"name": "include_errors", "value": "true"}, {"name": "type", "value": "discover_new"},
            {"name": "discover_by", "value": discover_by}]},
        "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.brightdata_body) }}",
        "options": {"timeout": 120000}},
        credentials=BRIGHTDATA_CRED, retryOnFail=True, maxTries=3, waitBetweenTries=2000, alwaysOutputData=True)


# ---------------------------------------------------------------- Zillow search
def zillow():
    build_query = r"""const input = $input.first().json;

function mapHomeType(propertyType) {
  const t = (propertyType || '').toLowerCase();
  if (t.includes('condo')) return 'Condos';
  if (t.includes('town')) return 'Townhomes';
  if (t.includes('land') || t.includes('lot')) return 'Lots/Land';
  if (t.includes('multi')) return 'Multi-family';
  if (t.includes('cabin') || t.includes('single') || t.includes('house')) return 'Houses';
  return ''; // unrecognized type - leave unfiltered rather than wrongly exclude it
}

const brightdata_body = {
  input: [{
    location: input.location,
    listingCategory: 'House for sale',
    HomeType: mapHomeType(input.property_type),
    days_on_zillow: '',
    exact_address: false
  }],
  limit_per_input: null
};

return [{
  json: {
    ...input,
    brightdata_body
  }
}];
"""
    normalize = MARKET_JS + r"""
// Maps raw Zillow records into the Finder Agent's candidate schema and applies
// the filters Bright Data's endpoint doesn't support (price, beds, baths,
// radius). Records arrive either straight from the synchronous /scrape call or
// from the snapshot download after polling.
function haversineMiles(lat1, lon1, lat2, lon2) {
  if ([lat1, lon1, lat2, lon2].some(v => v === null || v === undefined || v === '')) return null;
  const R = 3958.8;
  const toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

function buildAddress(r) {
  const parts = [r.streetAddress, r.city, r.state, r.zipcode].filter(Boolean);
  return parts.length ? parts.join(', ') : null;
}

const criteria = $('Build Bright Data Query').first().json;
const rawItems = $input.all().map(i => i.json);

const budgetMin = Number(criteria.budget_min) || 0;
const budgetMax = criteria.budget_max !== undefined && criteria.budget_max !== null
  ? Number(criteria.budget_max) : Infinity;
const minBeds = Number(criteria.min_beds) || 0;
const minBaths = Number(criteria.min_baths) || 0;
const radiusMiles = criteria.radius_miles !== undefined && criteria.radius_miles !== null
  ? Number(criteria.radius_miles) : null;
const maxResults = Number(criteria.max_results) || 10;

const records = rawItems.filter(r => r && typeof r.url === 'string' && r.url.length > 0);

const candidates = records
  .map(r => {
    const distance = haversineMiles(criteria.lat, criteria.lng, r.latitude, r.longitude);
    const price = typeof r.price === 'number' ? r.price : null;
    const beds = r.bedrooms !== undefined ? r.bedrooms : null;
    const baths = r.bathrooms !== undefined ? r.bathrooms : null;
    const cityState = [r.city, r.state].filter(Boolean).join(', ');
    return {
      address: buildAddress(r),
      price,
      url: r.url,
      source: 'zillow',
      beds,
      baths,
      sqft: r.livingArea !== undefined ? r.livingArea : (r.livingAreaValue !== undefined ? r.livingAreaValue : null),
      property_type: r.homeType !== undefined ? r.homeType : null,
      listing_status: r.homeStatus !== undefined ? r.homeStatus : null,
      distance_miles_from_resort: distance,
      lat: typeof r.latitude === 'number' ? r.latitude : null,
      lng: typeof r.longitude === 'number' ? r.longitude : null,
      market: resolveMarket(cityState, criteria.location) || cityState || null,
      _price: price, _beds: beds, _baths: baths, _distance: distance
    };
  })
  .filter(c => c._price === null || (c._price >= budgetMin && c._price <= budgetMax))
  .filter(c => minBeds === 0 || (c._beds !== null && c._beds >= minBeds))
  .filter(c => minBaths === 0 || (c._baths !== null && c._baths >= minBaths))
  .filter(c => radiusMiles === null || c._distance === null || c._distance <= radiusMiles)
  .map(({ _price, _beds, _baths, _distance, ...clean }) => clean)
  .slice(0, maxResults);

const gaps = [];
if (records.length === 0) gaps.push(`Bright Data returned no listings for "${criteria.location}".`);
else if (candidates.length === 0) gaps.push(`${records.length} listing(s) found near "${criteria.location}", but none matched budget, bed/bath and radius filters.`);

return [{ json: { candidates, source_count: records.length, gaps } }];
"""
    inputs = [{"name": "location"}, {"name": "lat", "type": "number"}, {"name": "lng", "type": "number"},
              {"name": "radius_miles", "type": "number"}, {"name": "budget_min", "type": "number"},
              {"name": "budget_max", "type": "number"}, {"name": "property_type"},
              {"name": "min_beds", "type": "number"}, {"name": "min_baths", "type": "number"},
              {"name": "max_results", "type": "number"}]
    nodes = [
        node("When Called by Finder Agent", "n8n-nodes-base.executeWorkflowTrigger", 1.2, 0, 0,
             {"workflowInputs": {"values": inputs}}),
        node("Build Bright Data Query", "n8n-nodes-base.code", 2, 224, 0, {"jsCode": build_query}),
        search_node("Search Zillow (Bright Data)", "gd_lfqkr8wm13ixtbd8f5", "input_filters"),
        SNAPSHOT_IF(672, 0),
        *poll_loop(0, 900000, "15 minutes", BRIGHTDATA_CRED),
        node("Normalize Candidates", "n8n-nodes-base.code", 2, 2240, 0, {"jsCode": normalize}),
    ]
    conns = main_conn([
        ("When Called by Finder Agent", ["Build Bright Data Query"]),
        ("Build Bright Data Query", ["Search Zillow (Bright Data)"]),
        ("Search Zillow (Bright Data)", ["Got Snapshot ID?"]),
        *poll_connections("Normalize Candidates"),
    ])
    return {"name": "BrightData - Zillow Search", "nodes": nodes, "connections": conns, "settings": SETTINGS,
            "pinData": {"When Called by Finder Agent": [{"json": {
                "location": "Park City, UT", "property_type": "single_family", "budget_min": 300000,
                "budget_max": 1300000, "min_beds": 2, "min_baths": 1, "radius_miles": 15, "max_results": 10,
                "lat": 40.6514, "lng": -111.508}}]}}


# ---------------------------------------------------------------- Airbnb search
def airbnb():
    build_query = r"""const input = $input.first().json;

function defaultDate(daysFromNow) {
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString();
}

// Bright Data expects full ISO datetime strings (...T00:00:00.000Z), not
// plain date strings - confirmed from Bright Data's own curl example.
// If the caller doesn't supply specific dates, use a representative near-term
// stay (30 days out, 3 nights) so we still get a real comp sample.
const check_in = input.check_in || defaultDate(30);
const check_out = input.check_out || defaultDate(33);

const brightdata_body = {
  input: [{
    location: input.location,
    check_in,
    check_out,
    num_of_adults: input.num_of_adults || 2,
    num_of_children: input.num_of_children ?? '',
    num_of_infants: input.num_of_infants ?? '',
    num_of_pets: input.num_of_pets ?? 0,
    currency: input.currency || 'USD',
    country: input.country || ''
  }],
  limit_per_input: null
};

return [{
  json: {
    ...input,
    check_in,
    check_out,
    brightdata_body
  }
}];
"""
    normalize = r"""function pick(obj, keys) {
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k];
  }
  return null;
}

// Confirmed live 2026-09-09 against a real Park City snapshot: this dataset has
// no discrete bedrooms/bathrooms/rating fields - they're embedded in the title
// text, e.g. "Home in Park City · ★4.8 · 5 bedrooms · 11 beds · 4 baths".
function parseFromTitle(title) {
  if (!title || typeof title !== 'string') return {};
  const rating = title.match(/★\s*([\d.]+)/);
  const bedrooms = title.match(/(\d+)\s*bedrooms?/i);
  const beds = title.match(/(\d+)\s*beds?\b/i);
  const baths = title.match(/([\d.]+)\s*baths?/i);
  return {
    rating: rating ? Number(rating[1]) : null,
    bedrooms: bedrooms ? Number(bedrooms[1]) : null,
    beds: beds ? Number(beds[1]) : null,
    bathrooms: baths ? Number(baths[1]) : null
  };
}

const criteria = $('Build Bright Data Query').first().json;
const rawItems = $input.all().map(i => i.json).filter(r => r && Object.keys(r).length > 0);
const maxResults = Number(criteria.max_results) || 10;

const candidates = rawItems
  .filter(r => r && (r.url || r.final_url))
  .map(r => {
    const title = pick(r, ['name', 'listing_title', 'title']);
    const parsed = parseFromTitle(title);
    return {
      url: pick(r, ['url', 'final_url']),
      title,
      // 'price' is Bright Data's field for nightly rate on this dataset - not yet
      // independently confirmed against a multi-night comparison. total_price and
      // pricing_details are kept alongside so a mismatch would be visible, not hidden.
      nightly_price: pick(r, ['price']),
      total_price: pick(r, ['total_price']),
      pricing_details_raw: r.pricing_details ?? null,
      currency: pick(r, ['currency']) || 'USD',
      bedrooms: parsed.bedrooms,
      beds: parsed.beds,
      bathrooms: parsed.bathrooms,
      guests: pick(r, ['guests', 'person_capacity', 'max_guests']),
      rating: parsed.rating,
      reviews_count: pick(r, ['property_number_of_reviews', 'number_of_reviews']),
      is_superhost: pick(r, ['is_supperhost', 'is_superhost']),
      is_guest_favorite: pick(r, ['is_guest_favorite']),
      minimum_nights: pick(r, ['minimum_nights']),
      latitude: pick(r, ['lat', 'latitude']),
      longitude: pick(r, ['long', 'longitude']),
      source: 'airbnb'
    };
  })
  .slice(0, maxResults);

const sampleRawKeys = rawItems.length ? Object.keys(rawItems[0]) : [];
const gaps = [];
if (rawItems.length === 0) {
  gaps.push(`Bright Data returned no Airbnb listings for "${criteria.location}" (${criteria.check_in} to ${criteria.check_out}).`);
}
if (rawItems.length > 0 && candidates.length === 0) {
  gaps.push('Snapshot returned data but no items had a recognizable url field - field mapping needs verification. Raw keys sample: ' + sampleRawKeys.join(', '));
}
// Confirmed live 2026-09-09: 'price' matches pricing_details.initial_price_per_night
// (the un-discounted asking nightly rate) - flag only if a specific candidate disagrees.
candidates.forEach(c => {
  const listed = c.pricing_details_raw && c.pricing_details_raw.initial_price_per_night;
  if (listed !== null && listed !== undefined && Math.abs(listed - c.nightly_price) > 1) {
    gaps.push(`Price mismatch for ${c.url}: nightly_price=${c.nightly_price} vs pricing_details.initial_price_per_night=${listed}`);
  }
});

return [{ json: { candidates, source_count: rawItems.length, raw_keys_sample: sampleRawKeys, check_in: criteria.check_in, check_out: criteria.check_out, gaps } }];
"""
    inputs = [{"name": "location"}, {"name": "check_in"}, {"name": "check_out"},
              {"name": "num_of_adults", "type": "number"}, {"name": "num_of_children", "type": "number"},
              {"name": "num_of_infants", "type": "number"}, {"name": "num_of_pets", "type": "number"},
              {"name": "currency"}, {"name": "country"}, {"name": "max_results", "type": "number"}]
    nodes = [
        node("When Called by Report Agent", "n8n-nodes-base.executeWorkflowTrigger", 1.2, 0, 0,
             {"workflowInputs": {"values": inputs}}),
        node("Build Bright Data Query", "n8n-nodes-base.code", 2, 224, 0, {"jsCode": build_query}),
        search_node("Search Airbnb (Bright Data)", "gd_ld7ll037kqy322v05", "location"),
        SNAPSHOT_IF(672, 0),
        *poll_loop(0, 1500000, "25 minutes", BRIGHTDATA_CRED),
        node("Normalize Rental Comps", "n8n-nodes-base.code", 2, 2240, 0, {"jsCode": normalize}),
    ]
    conns = main_conn([
        ("When Called by Report Agent", ["Build Bright Data Query"]),
        ("Build Bright Data Query", ["Search Airbnb (Bright Data)"]),
        ("Search Airbnb (Bright Data)", ["Got Snapshot ID?"]),
        *poll_connections("Normalize Rental Comps"),
    ])
    return {"name": "BrightData - Airbnb Search", "nodes": nodes, "connections": conns, "settings": SETTINGS, "pinData": {}}


# ---------------------------------------------------------------- Finder Agent
FINDER_PROMPT = """You are the Finder Agent, a property search agent for a real-estate investment
system. Your ONLY job: given an investor's search criteria (a ski resort or
mountain-town area in the USA, budget, property type, strategy), find REAL,
currently-listed properties near that location and return them as structured
data.

You are NOT the Report Agent. You do not judge whether a property is a good
investment. You do not compute comps, cap rate, cash-on-cash, ROI, financing,
or any financial model. You do not talk to the investor directly - your only
output is the structured JSON described below, consumed by another system.

=== NON-NEGOTIABLE RULE: NEVER INVENT A LISTING ===
Every property you return MUST come from a real tool call result and MUST
carry the exact URL that tool call returned. You may never:
- Invent an address, price, or URL
- "Complete" a partial result with a plausible-sounding value
- Present a property you are not certain is currently a real, active listing
- Round, estimate, or paraphrase a URL - copy it exactly as returned

If your tools return zero results, or results that don't meet the criteria,
say so honestly in the gaps field. A missing answer is always better than
a fabricated one.

=== TOOL MAP ===
geocode_location -> resolves a resort/area name to coordinates. ALWAYS call
 this FIRST, before search_listings - you need these coordinates to report
 resolved_location and to compute each candidate's distance from the resort.
 This tool does NOT perform the property search itself.

search_listings -> the ONLY source of real listing data. Takes a
 human-readable location (city/state or zip near the resort) and searches
 live for-sale listings there via Bright Data. NEVER answer a question
 about available properties without calling this tool. The search itself
 is NOT filtered by budget or bed/bath count (the underlying API doesn't
 support that) - those filters are applied automatically after the tool
 returns, against the real data it found. If it returns no results, try at
 most ONE reasonable relaxation (e.g. a nearby larger town instead of the
 exact resort town) and clearly label any results returned under relaxed
 criteria as such - never relax silently. Copy any gaps it returns into
 your own gaps field.

=== OUTPUT FORMAT ===
Respond with ONLY a single JSON object, no prose, no markdown, no code
fences, matching exactly this shape:

{
 "search_criteria": <echo of the input criteria object>,
 "resolved_location": {"lat": <number>, "lng": <number>, "radius_miles": <number>},
 "candidates_found": <integer>,
 "candidates": [
 {
 "address": <string>,
 "price": <number>,
 "url": <string, exact tool-returned URL>,
 "source": <string, e.g. "zillow">,
 "beds": <number|null>,
 "baths": <number|null>,
 "sqft": <number|null>,
 "property_type": <string>,
 "listing_status": <string>,
 "distance_miles_from_resort": <number>,
 "market": <string, exactly as search_listings returned it>,
 "lat": <number|null, exactly as search_listings returned it>,
 "lng": <number|null, exactly as search_listings returned it>
 }
 ],
 "gaps": [<string, plain-language explanation, empty array if none>],
 "generated_at": <ISO-8601 timestamp>
}

If a field genuinely isn't available for a candidate, use null - never a
guess. Cap candidates at the max_results given in the input (default 10).

=== LIMITS ===
Your job is finding candidates. Everything else -> a different system:
- "Is this a good deal?" / "What's the ROI?" -> NOT your job. Return the
 candidate data; the Report Agent handles evaluation.
- Requests unrelated to property search (general chat, unrelated locations
 outside the USA, non-real-estate questions) -> return an empty candidates
 array with a gap explaining this is out of scope.

=== FINAL RULES ===
- Always call geocode_location before search_listings.
- Never call search_listings more than twice per request (original + at
 most one relaxed retry).
- Never fabricate, estimate, or silently modify a URL, address, or price.
- Copy market, lat and lng for each candidate exactly as search_listings
 returned them - never fill them in yourself.
- Never exceed max_results.
- Output ONLY the JSON object - no explanation, no markdown, no apology text.
- If you are not fully certain a piece of data came from a real tool result,
 omit it (null) rather than guess."""

GEOCODE_DESC = """Resolves a place name (ski resort, mountain town, or "city, state") to latitude/longitude coordinates, used only for reporting resolved_location
and computing each candidate's distance from the resort. It does NOT search for properties - that's search_listings' job.

USE OBLIGATORILY when:
- This is the first tool call of the request (always call before search_listings)
- The investor's criteria names a resort/area, not raw coordinates

NEVER use for:
- Evaluating whether a location is a good investment area (not your job)
- Anything after you already have resolved_location for this request - call once

AFTER using this tool:
- Keep the returned lat/lng to report as resolved_location and to pass into
 search_listings for distance calculation
- If geocoding fails (place not found), do not guess coordinates - return a gap explaining the location could not be resolved"""

SEARCH_DESC = """Searches real, currently active for-sale property listings near a named
place (city/state or zip - e.g. "Park City, UT") via Bright Data's Zillow
data. This is the ONLY source of truth for what properties exist - you have
no other way to know about real listings.

USE OBLIGATORILY when:
- You need to answer any question about available properties
- You have a resolved_location from geocode_location (pass its lat/lng
 through so results can be scored by distance from the resort)

NEVER use for:
- Guessing at listings without calling this tool first
- Re-running the exact same query more than once (only retry with an
 explicitly different/nearby location, and label the relaxation in the output)

AFTER using this tool:
- Use ONLY the properties actually returned - never add, complete, or
 "round out" the list. Budget, bed/bath, and distance filtering already
 happened inside the tool against the real returned data - trust its output.
- Copy each candidate's market, lat and lng exactly as returned.
- If it returns fewer than requested, that's the honest answer - report the
 count truthfully, don't pad it
- If it returns nothing, try at most one relaxed retry (a nearby town),
 then report a gap"""


def finder():
    enforce = r"""// Deterministic safety net - NOT the AI. Drops any candidate without a real
// URL on a recognized listing site before anything leaves this workflow.
const ALLOWED_DOMAINS = [
  'zillow.com', 'realtor.com', 'redfin.com', 'trulia.com', 'homes.com',
  'coldwellbanker.com', 'century21.com', 'compass.com'
];

function hasValidListingUrl(url) {
  if (!url || typeof url !== 'string') return false;
  const match = url.match(/^https?:\/\/([^\/]+)/i);
  if (!match) return false;
  const hostname = match[1].toLowerCase();
  return ALLOWED_DOMAINS.some(d => hostname === d || hostname.endsWith('.' + d));
}
let raw = $input.first().json;
let parsed;

let text = raw.output ?? raw.text ?? raw;
if (typeof text === 'string') {
  text = text.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/i, '').trim();
}

try {
  parsed = typeof text === 'string' ? JSON.parse(text) : text;
} catch (e) {
  return [{
    json: {
      search_criteria: null,
      resolved_location: null,
      candidates_found: 0,
      candidates: [],
      gaps: ['Finder Agent did not return valid JSON. Raw output logged for debugging.'],
      raw_output: typeof text === 'string' ? text.slice(0, 2000) : JSON.stringify(text).slice(0, 2000),
      generated_at: new Date().toISOString()
    }
  }];
}

const incomingCandidates = Array.isArray(parsed.candidates) ? parsed.candidates : [];
const kept = incomingCandidates.filter(c => hasValidListingUrl(c && c.url));
const droppedCount = incomingCandidates.length - kept.length;

const gaps = Array.isArray(parsed.gaps) ? [...parsed.gaps] : [];
if (droppedCount > 0) {
  gaps.push(`${droppedCount} candidate(s) were dropped by the safety filter for missing or invalid source URLs.`);
}
const missingMarket = kept.filter(c => !c.market).length;
if (missingMarket > 0) {
  gaps.push(`${missingMarket} candidate(s) have no market - the Report Agent will try to derive it from the address.`);
}

return [{
  json: {
    search_criteria: parsed.search_criteria ?? null,
    resolved_location: parsed.resolved_location ?? null,
    candidates_found: kept.length,
    candidates: kept,
    gaps,
    generated_at: new Date().toISOString()
  }
}];
"""
    def fromai(name, desc, t):
        return "={{ $fromAI('%s', '%s', '%s') }}" % (name, desc, t)

    search_inputs = {
        "location": fromai("location", "Human-readable place to search near the resort, e.g. \\'Park City, UT\\' or a nearby zip code - this is what actually gets sent to Bright Data", "string"),
        "lat": fromai("lat", "Latitude from geocode_location result, used only for distance filtering/scoring, not sent to Bright Data", "number"),
        "lng": fromai("lng", "Longitude from geocode_location result, used only for distance filtering/scoring, not sent to Bright Data", "number"),
        "radius_miles": fromai("radius_miles", "Search radius in miles - applied client-side after Bright Data returns results", "number"),
        "budget_min": fromai("budget_min", "Minimum price in USD", "number"),
        "budget_max": fromai("budget_max", "Maximum price in USD", "number"),
        "property_type": fromai("property_type", "Property type filter, e.g. single_family, condo, cabin", "string"),
        "min_beds": fromai("min_beds", "Minimum bedrooms", "number"),
        "min_baths": fromai("min_baths", "Minimum bathrooms", "number"),
        "max_results": fromai("max_results", "Maximum number of candidates to return", "number"),
    }
    types = {"location": "string", "property_type": "string"}
    schema = [{"id": k, "displayName": k, "required": False, "defaultMatch": False, "display": True,
               "canBeUsedToMatch": True, "type": types.get(k, "number"), "removed": False} for k in search_inputs]
    criteria = [("resort_name", "={{ $json.body.resort_name }}", "string"),
                ("state", "={{ $json.body.state }}", "string"),
                ("max_distance_miles", "={{ $json.body.max_distance_miles ?? 15 }}", "number"),
                ("budget_min", "={{ $json.body.budget_min ?? 0 }}", "number"),
                ("budget_max", "={{ $json.body.budget_max ?? 1300000 }}", "number"),
                ("property_type", "={{ $json.body.property_type ?? 'single_family' }}", "string"),
                ("min_beds", "={{ $json.body.min_beds ?? 0 }}", "number"),
                ("min_baths", "={{ $json.body.min_baths ?? 0 }}", "number"),
                ("strategy", "={{ $json.body.strategy ?? 'unspecified' }}", "string"),
                ("max_results", "={{ $json.body.max_results ?? 10 }}", "number")]
    nodes = [
        node("Investor Criteria", "n8n-nodes-base.webhook", 2.1, 0, 0,
             {"httpMethod": "POST", "path": "finder-agent", "responseMode": "responseNode", "options": {}},
             webhookId="b745b5cc-bfeb-43d1-98ee-2d381c5ebbd3"),
        node("Normalize Criteria", "n8n-nodes-base.set", 3.5, 224, 0, {"assignments": {"assignments": [
            {"id": "crit-%02d" % i, "name": n, "value": v, "type": t} for i, (n, v, t) in enumerate(criteria)]}, "options": {}}),
        node("Finder Agent", "@n8n/n8n-nodes-langchain.agent", 3.1, 512, 0,
             {"promptType": "define", "text": "={{ JSON.stringify($json) }}", "options": {"systemMessage": FINDER_PROMPT}}),
        node("Model - Claude Sonnet", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.5, 464, 240,
             {"model": {"__rl": True, "mode": "list", "value": "claude-sonnet-4-6", "cachedResultName": "Claude Sonnet 4.6"}, "options": {}},
             credentials=ANTHROPIC_CRED),
        node("geocode_location", "n8n-nodes-base.httpRequestTool", 4.5, 592, 240, {
            "toolDescription": GEOCODE_DESC, "url": "https://nominatim.openstreetmap.org/search", "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "q", "value": fromai("location", "The resort or area name plus state to geocode, e.g. \\'Park City Mountain Resort, UT\\'", "string")},
                {"name": "format", "value": "json"}, {"name": "limit", "value": "1"}, {"name": "countrycodes", "value": "us"}]},
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "User-Agent", "value": "FinderAgent/1.0 (harold.kleeman@gmail.com)"}]},
            "options": {}}),
        node("search_listings", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, 720, 240, {
            "description": SEARCH_DESC,
            "workflowId": {"__rl": True, "value": ZILLOW_WF, "mode": "list", "cachedResultUrl": "/workflow/" + ZILLOW_WF,
                           "cachedResultName": "BrightData - Zillow Search"},
            "workflowInputs": {"mappingMode": "defineBelow", "value": search_inputs, "matchingColumns": [], "schema": schema,
                               "attemptToConvertTypes": False, "convertFieldsToString": False}}),
        node("Enforce Real-Listing Rule", "n8n-nodes-base.code", 2, 912, 0, {"jsCode": enforce}),
        node("Return Results", "n8n-nodes-base.respondToWebhook", 1.5, 1136, 0,
             {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}}),
        node("Publish to Tracker Sheet", "n8n-nodes-base.executeWorkflow", 1.2, 1136, 200, {
            "source": "database",
            "workflowId": {"__rl": True, "mode": "id", "value": PUBLISH_WF},
            "mode": "once",
            "options": {"waitForSubWorkflow": False}}, onError="continueRegularOutput"),
    ]
    conns = main_conn([
        ("Investor Criteria", ["Normalize Criteria"]),
        ("Normalize Criteria", ["Finder Agent"]),
        ("Finder Agent", ["Enforce Real-Listing Rule"]),
        ("Enforce Real-Listing Rule", ["Return Results", "Publish to Tracker Sheet"]),
    ])
    ai_conn(conns, "Model - Claude Sonnet", "ai_languageModel", "Finder Agent")
    conns["geocode_location"] = {"ai_tool": [[{"node": "Finder Agent", "type": "ai_tool", "index": 0}]]}
    conns["search_listings"] = {"ai_tool": [[{"node": "Finder Agent", "type": "ai_tool", "index": 0}]]}
    return {"name": "Finder Agent", "nodes": nodes, "connections": conns, "settings": SETTINGS, "pinData": {}}


# ---------------------------------------------------------------- Publish to sheet
def publisher():
    split = r"""// Accepts either the webhook body or the Finder Agent's result item
// (when called from the Finder workflow) and collects all candidates.
const candidates = [];
for (const item of $input.all()) {
  const src = item.json.body ?? item.json;
  if (Array.isArray(src.candidates)) candidates.push(...src.candidates);
  else if (Array.isArray(src)) candidates.push(...src);
}
return [{ json: { candidates } }];
"""
    keep_new = r"""// Skips listings already in the sheet (matched by URL) and duplicates within
// this batch, and shapes each new one as a row keyed by the sheet's headers.
const existing = new Set(
  $('Read Existing Rows').all()
    .map(i => String(i.json.URL || '').trim())
    .filter(Boolean)
);
const candidates = $('Split Candidates').first().json.candidates || [];
const now = new Date().toISOString();
const seen = new Set();
const rows = [];
let skippedExisting = 0;
let skippedNoUrl = 0;

for (const c of candidates) {
  const url = c && typeof c.url === 'string' ? c.url.trim() : '';
  if (!url) { skippedNoUrl++; continue; }
  if (existing.has(url) || seen.has(url)) { skippedExisting++; continue; }
  seen.add(url);
  rows.push({
    'Address': c.address ?? '',
    'Price': c.price ?? '',
    'Beds': c.beds ?? '',
    'Baths': c.baths ?? '',
    'SqFt': c.sqft ?? '',
    'Market': c.market ?? '',
    'Distance to resort (mi)': typeof c.distance_miles_from_resort === 'number'
      ? Math.round(c.distance_miles_from_resort * 10) / 10 : '',
    'URL': url,
    'Date Added': now,
    'Status': 'New'
  });
}

return [{ json: { rows, appended: rows.length, skipped_existing: skippedExisting, skipped_no_url: skippedNoUrl } }];
"""
    columns = ["Address", "Price", "Beds", "Baths", "SqFt", "Market", "Distance to resort (mi)", "URL",
               "Date Added", "Status", "Report Doc Link"]
    schema = [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True,
               "type": "string", "canBeUsedToMatch": True} for c in columns]
    doc = {"__rl": True, "value": SHEET_ID, "mode": "list", "cachedResultName": "Ski Rental Investment - Candidate Tracker",
           "cachedResultUrl": "https://docs.google.com/spreadsheets/d/%s/edit" % SHEET_ID}
    sheet = {"__rl": True, "value": "gid=0", "mode": "list", "cachedResultName": "Master List",
             "cachedResultUrl": "https://docs.google.com/spreadsheets/d/%s/edit#gid=0" % SHEET_ID}
    nodes = [
        node("New Candidates Received", "n8n-nodes-base.webhook", 2.1, 0, 0,
             {"httpMethod": "POST", "path": "publish-candidates", "responseMode": "responseNode", "options": {}},
             webhookId="61155640-ca66-4bac-881b-c436e096df6a"),
        node("When Called by Finder Agent", "n8n-nodes-base.executeWorkflowTrigger", 1.1, 0, 200,
             {"inputSource": "passthrough"}),
        node("Split Candidates", "n8n-nodes-base.code", 2, 224, 100, {"jsCode": split}),
        node("Read Existing Rows", "n8n-nodes-base.googleSheets", 4.7, 448, 100,
             {"operation": "read", "documentId": doc, "sheetName": sheet, "options": {}},
             credentials=SHEETS_CRED, alwaysOutputData=True, executeOnce=True),
        node("Keep New Only", "n8n-nodes-base.code", 2, 672, 100, {"jsCode": keep_new}),
        node("Any New Rows?", "n8n-nodes-base.if", 2.3, 896, 100, {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 3},
                           "conditions": [{"id": "rows-0001", "leftValue": "={{ $json.appended }}", "rightValue": 0,
                                           "operator": {"type": "number", "operation": "gt"}}],
                           "combinator": "and"}, "options": {}}),
        node("One Item Per Row", "n8n-nodes-base.code", 2, 1120, 0,
             {"jsCode": "return $input.first().json.rows.map(r => ({ json: r }));\n"}),
        node("Append Row", "n8n-nodes-base.googleSheets", 4.7, 1344, 0, {
            "operation": "append", "documentId": doc, "sheetName": sheet,
            "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": schema,
                        "attemptToConvertTypes": False, "convertFieldsToString": False},
            "options": {}}, credentials=SHEETS_CRED),
        node("Summarize", "n8n-nodes-base.code", 2, 1568, 100, {"jsCode": (
            "const s = $('Keep New Only').first().json;\n"
            "return [{ json: { appended: s.appended, skipped_existing: s.skipped_existing, skipped_no_url: s.skipped_no_url } }];\n")}),
        node("Called via Webhook?", "n8n-nodes-base.if", 2.3, 1792, 100, {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 3},
                           "conditions": [{"id": "webhook-0001", "leftValue": "={{ $('New Candidates Received').isExecuted }}",
                                           "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                           "combinator": "and"}, "options": {}}),
        node("Respond", "n8n-nodes-base.respondToWebhook", 1.5, 2016, 0,
             {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}}),
    ]
    conns = main_conn([
        ("New Candidates Received", ["Split Candidates"]),
        ("When Called by Finder Agent", ["Split Candidates"]),
        ("Split Candidates", ["Read Existing Rows"]),
        ("Read Existing Rows", ["Keep New Only"]),
        ("Keep New Only", ["Any New Rows?"]),
        ("Any New Rows?", ["One Item Per Row"], ["Summarize"]),
        ("One Item Per Row", ["Append Row"]),
        ("Append Row", ["Summarize"]),
        ("Summarize", ["Called via Webhook?"]),
        ("Called via Webhook?", ["Respond"], []),
    ])
    return {"name": "Publish Candidates to Sheet", "nodes": nodes, "connections": conns, "settings": SETTINGS, "pinData": {}}


# ---------------------------------------------------------------- Report Agent
REFERENCE_TABLES_JS = r"""const snowReliability = {
 "Park City, UT": { resorts: ["Park City Mountain (PCM)", "Deer Valley"], avgAnnualSnowfallInches: { parkCityMountain: 277, deerValley: 255 }, avgSnowfallDaysPerYear: { parkCityMountain: 56, deerValley: 53 }, seasonLength: "Late Nov/early Dec through mid-April; varies year to year", lowSnowYearRisk: "2025-26: every Utah resort pushed back opening; Deer Valley delayed opening for the first time in resort history. UT drought emergency declared in 17 counties.", confidence: "well-documented (snowfall/base/season), thin on powder-day-specific data", sources: ["https://www.onthesnow.com/utah/park-city-mountain-resort/historical-snowfall", "https://www.onthesnow.com/utah/deer-valley-resort/historical-snowfall"] },
 "Steamboat Springs, CO": { resorts: ["Steamboat Resort"], avgAnnualSnowfallInches: 283, avgAnnualSnowfallInchesAltSource: 347, avgSnowfallDaysPerYear: 67, seasonLength: "~6 months, late Nov through mid/late April", lowSnowYearRisk: "Wide year-to-year variability: historical totals range 174\" (2014-15) to 428\" (2022-23) - widest swing of the 4 markets.", confidence: "well-documented; conflicting totals between sources (283\" vs 347\") - flagged, not resolved", sources: ["https://www.onthesnow.com/colorado/steamboat/historical-snowfall", "https://en.wikipedia.org/wiki/Steamboat_Ski_Resort"] },
 "Jackson Hole, WY": { resorts: ["Jackson Hole Mountain Resort (JHMR)"], avgAnnualSnowfallInches: 414, avgAnnualSnowfallInchesAltSource: 465, avgSnowfallDaysPerYear: 74, seasonLength: "~Thanksgiving through early April (~4.5-5 months)", lowSnowYearRisk: "Deepest/most consistent of the 4 markets historically (record 595\" in 2022-23); general Western snow-drought trend applies regionally.", confidence: "well-documented", sources: ["https://www.onthesnow.com/wyoming/jackson-hole/historical-snowfall", "https://www.jacksonhole.com/mountain-stats"] },
 "Vail, CO": { resorts: ["Vail Mountain"], avgAnnualSnowfallInches: 250, avgAnnualSnowfallInchesAltSource: 354, avgSnowfallDaysPerYear: 66, seasonLength: "Mid/late Nov through mid-April (~5 months)", lowSnowYearRisk: "Historical totals range 171\" (2017-18) to 329\" (2022-23). CO snowpack reported at lowest on record for time-of-year during 2025-26.", confidence: "well-documented, but the two most-cited totals (250\" vs 354\") diverge ~40% by source - flagged, not resolved", sources: ["https://www.onthesnow.com/colorado/vail/historical-snowfall"] }
};

const buildRehabCost = {
 "Park City, UT": { costPerSqFtRangeUSD: { low: 500, high: 1000 }, caveat: "luxury-tier ceiling reference only, not a mid-tier estimate", notes: "Timeline ~18-20 months typical. No moderate/production-tier data exists for this town.", sources: ["https://homesparkcity.com/blog/cost-to-build-a-house-in-park-city"] },
 "Steamboat Springs, CO": { costPerSqFtRangeUSD: { low: 500, high: 800 }, caveat: "luxury-tier ceiling reference only, not a mid-tier estimate", notes: "~20% of total is soft cost on a cited high-end build example.", sources: ["https://f9productions.com/how-much-does-it-really-cost-to-build-a-home-in-colorado/"] },
 "Jackson Hole, WY": { costPerSqFtRangeUSD: { low: 800, high: 1500 }, caveat: "luxury-tier ceiling reference only, not a mid-tier estimate", notes: "Highest of the 4 markets. Strict design/scenic review adds cost and time.", sources: ["https://swagerbuilds.com/2026/05/03/cost-to-build-custom-home-teton-valley-2026/"] },
 "Vail, CO": { costPerSqFtRangeUSD: { low: 600, high: 1200 }, caveat: "luxury-tier ceiling reference only, not a mid-tier estimate", notes: "Remote logistics and short building season cited as main cost drivers.", sources: ["https://evstudio.com/home-building-costs-in-the-rocky-mountain-region/"] }
};

const strRegulatoryStatus = {
 "Park City, UT": { licenseRequired: true, licenseName: "Nightly Rental License (Park City Finance Department)", transferability: "Non-transferable in practice - new owner must apply for own license", capsOrModeratoria: "No verified citywide numeric cap - zoning restricts eligible districts; exact per-zone caps unverified.", confidence: "well-documented on mechanics/enforcement trend; sparse/unverified on exact numeric caps by zone - verify locally", sources: ["https://skyrun.com/park-city/guide-to-park-city-short-term-rental-regulations/"] },
 "Steamboat Springs, CO": { licenseRequired: true, licenseName: "Short-Term Rental License (City of Steamboat Springs), overlay zone system since 2022-06-07", transferability: "Not stated in any source reached - explicitly unknown", capsOrModeratoria: "Three-tier overlay: Green = no cap, Yellow = numeric cap per zone (exact numbers not published), Red = prohibited.", confidence: "well-documented on zone structure; sparse on transferability and exact per-zone caps - verify locally", sources: ["https://www.steamboatpilot.com/news/short-term-rental-regulations-in-steamboat-officially-approved/"] },
 "Jackson Hole, WY": { licenseRequired: true, licenseName: "Varies by jurisdiction - spans Town of Jackson and unincorporated Teton County with different rules", transferability: "Town of Jackson: zoning approval survives sale inside the Lodging Overlay, but new owner still needs own operating license. Unincorporated Teton County: cap/transferability NOT verified from a primary source.", capsOrModeratoria: "Town of Jackson: 60 nights/3 stays per year outside the Lodging Overlay. Unincorporated Teton County: STRs banned outside a short list of pre-approved developments (e.g. Teton Village) - most classic resort-adjacent inventory sits here, the weakest-sourced entry in this table.", confidence: "moderately documented for Town of Jackson; sparse/UNVERIFIED for unincorporated Teton County - confirm directly with Teton County Planning before presenting to the client as settled fact", sources: ["https://www.jacksonwy.gov/335/Short-Term-Rentals", "https://www.tetoncountywy.gov/Faq.aspx?QID=362"] },
 "Vail, CO": { licenseRequired: true, licenseName: "Short-Term Rental License (Town of Vail), per-property, annual renewal", transferability: "Not explicitly stated; inferred (not directly sourced) that a new owner must obtain their own license", capsOrModeratoria: "No published numeric cap under the current flat-fee schedule. A pending switch to a $1,200/bedroom/year fee was passed on FIRST reading only - NOT yet in effect, live regulatory risk.", confidence: "well-documented for current mechanics; the pending fee change and Eagle County's unincorporated-area status are both recent and could shift again - flag for a refresh check", sources: ["https://golocalvr.com/blog/vail-short-term-rental-regulations-compliance-guide-2026"] }
};
"""

FIN_MODEL_JS = r"""const candidate = $input.item.json;
const cg = candidate.client_goals || {};

const ASSUMPTIONS = {
 occupancy_near_resort: 0.55,
 occupancy_far_resort: 0.40,
 near_resort_threshold_miles: 10,
 opex_ratio: 0.40,
 closing_cost_pct: 0.03,
 appreciation_annual_pct: 0.035,
 land_value_pct_of_price: 0.20,
 depreciation_years: 27.5,
 marginal_tax_rate_placeholder: 0.32,
 mortgage_rate: 0.0588,
 mortgage_term_years: 15,
 down_payment_pct: 0.20,
 note: "All values above are stated assumptions, not measured data - see Report Agent Build Guide Section 2. Depreciation/tax figures are a simplified placeholder; the Tax Agent refines this once a property is chosen and a CPA document is available."
};

const price = candidate.price;
const distance = candidate.distance_miles_from_resort;
const personalUseWeeks = Number(cg.personal_use_weeks_per_year) || 0;

const rentalComps = Array.isArray(candidate.rental_comps) ? candidate.rental_comps : [];
const validRates = rentalComps.map(c => c.nightly_price).filter(v => typeof v === 'number');
const adr = validRates.length ? validRates.reduce((a, b) => a + b, 0) / validRates.length : null;

const gaps = [...(candidate.gaps || [])];
if (adr === null) gaps.push('No real rental comps returned for this market - ADR could not be computed, financial model skipped.');
if (price === null || price === undefined) gaps.push('Candidate price missing - financial model cannot be computed.');

let financial_model = null;
if (adr !== null && price) {
 const occupancy = (distance !== null && distance !== undefined && distance <= ASSUMPTIONS.near_resort_threshold_miles)
 ? ASSUMPTIONS.occupancy_near_resort : ASSUMPTIONS.occupancy_far_resort;
 const rentableNights = Math.max(0, 365 - personalUseWeeks * 7);
 const grossRevenue = adr * occupancy * rentableNights;
 const noi = grossRevenue * (1 - ASSUMPTIONS.opex_ratio);
 const capRate = noi / price;

 const closingCosts = price * ASSUMPTIONS.closing_cost_pct;
 const reserve = Number(cg.reserve) || 0;

 const cashInvestedAllCash = price + closingCosts + reserve;
 const cashFlowAllCash = noi;
 const cocAllCash = cashFlowAllCash / cashInvestedAllCash;

 const downPayment = price * ASSUMPTIONS.down_payment_pct;
 const loanAmount = price - downPayment;
 const monthlyRate = ASSUMPTIONS.mortgage_rate / 12;
 const n = ASSUMPTIONS.mortgage_term_years * 12;
 const monthlyPayment = loanAmount * monthlyRate / (1 - Math.pow(1 + monthlyRate, -n));
 const annualDebtService = monthlyPayment * 12;
 const cashFlowFinanced = noi - annualDebtService;
 const cashInvestedFinanced = downPayment + closingCosts + reserve;
 const cocFinanced = cashFlowFinanced / cashInvestedFinanced;

 const appreciationDollar = price * ASSUMPTIONS.appreciation_annual_pct;
 const buildingValue = price * (1 - ASSUMPTIONS.land_value_pct_of_price);
 const annualDepreciation = buildingValue / ASSUMPTIONS.depreciation_years;
 const depreciationTaxShield = annualDepreciation * ASSUMPTIONS.marginal_tax_rate_placeholder;

 const totalReturnAllCash = cashFlowAllCash + appreciationDollar + depreciationTaxShield;
 const totalReturnPctAllCash = totalReturnAllCash / cashInvestedAllCash;
 const totalReturnFinanced = cashFlowFinanced + appreciationDollar + depreciationTaxShield;
 const totalReturnPctFinanced = totalReturnFinanced / cashInvestedFinanced;

 financial_model = {
 adr_from_real_comps: Math.round(adr * 100) / 100,
 comps_used: validRates.length,
 assumed_occupancy_pct: occupancy,
 rentable_nights_per_year: rentableNights,
 gross_str_revenue: Math.round(grossRevenue),
 opex_ratio_assumed: ASSUMPTIONS.opex_ratio,
 noi: Math.round(noi),
 cap_rate: Math.round(capRate * 10000) / 10000,
 all_cash: {
 cash_invested: Math.round(cashInvestedAllCash),
 annual_cash_flow: Math.round(cashFlowAllCash),
 cash_on_cash_pct: Math.round(cocAllCash * 10000) / 10000,
 total_return_dollars: Math.round(totalReturnAllCash),
 total_return_pct: Math.round(totalReturnPctAllCash * 10000) / 10000
 },
 financed_20pct_down_5_88pct_15yr: {
 down_payment: Math.round(downPayment),
 loan_amount: Math.round(loanAmount),
 annual_debt_service: Math.round(annualDebtService),
 cash_invested: Math.round(cashInvestedFinanced),
 annual_cash_flow: Math.round(cashFlowFinanced),
 cash_on_cash_pct: Math.round(cocFinanced * 10000) / 10000,
 total_return_dollars: Math.round(totalReturnFinanced),
 total_return_pct: Math.round(totalReturnPctFinanced * 10000) / 10000
 },
 appreciation_dollar_assumed: Math.round(appreciationDollar),
 depreciation_tax_shield_assumed: Math.round(depreciationTaxShield),
 assumptions: ASSUMPTIONS
 };
}

return { json: { ...candidate, financial_model, gaps } };"""

REPORT_PROMPT = """You are the Report Agent (Underwriting Agent) for a real-estate investment system. You receive a set of client-selected candidate properties, each already enriched with real comps, reference data, and a fully-computed financial model - your ONLY job is to narrate and compare this data into a clear investment report. You are NOT the Finder Agent (you don't search for new properties) and you are NOT the Tax Agent (you never generate federal or estate tax conclusions - that requires the client's own CPA/attorney document).

=== NON-NEGOTIABLE RULES ===
- Never invent a comp, rent estimate, tax rate, regulation, or statistic. Every fact you state must come from the payload you were given.
- Never recalculate or override any number in `financial_model` - narrate it exactly as given. If you disagree with an assumption, note it as a caveat, don't silently substitute your own number.
- Classify uncertain claims plainly: state clearly when a figure is REPORTED/ESTIMATED (per the payload's own `assumptions`/`confidence`/`caveat` fields) versus a real, sourced fact.
- Tax figures are state-level reference only, from `reference_data.str_regulatory_status`/state tax notes - never state a federal or estate tax conclusion. Flag those as questions for the client's CPA/attorney, deferred to the Tax Agent.
- If `gaps` is non-empty for a candidate, say so plainly in that candidate's section - do not paper over missing data with a confident-sounding guess.
- STR license status: if a market's entry says "sparse"/"unverified"/"confirm locally", state that explicitly as a real risk, not a footnote.
- Sold comps and detailed price history are not available in this version of the pipeline - if asked about them or tempted to describe price trend, say this data is not yet available rather than guessing.

=== INPUT ===
You will receive one JSON object: `{ client_goals: {...}, candidates: [ ...one fully-enriched candidate per client selection... ] }`. Each candidate already has: address, price, url, beds, baths, sqft, property_type, market, distance_miles_from_resort, elevation_ft, rental_comps (real Airbnb comps), reference_data (snow_reliability, build_rehab_cost, str_regulatory_status), financial_model (both financing scenarios, total return, assumptions), and gaps (candidate-specific caveats).

=== OUTPUT STRUCTURE ===
Produce a report in clean Markdown with these sections, in this order:
1. **Comparison Overview** - one table, all candidates: price, cap rate, cash-on-cash (both financing scenarios), total return % (both scenarios), elevation, snow reliability tier, STR license risk level, investment score (your qualitative 1-10 ranking based on the data given, with a one-line reason).
2. **Full Deep-Dive** for the top-ranked candidate only: Executive Summary / Property Overview / STR Rental Analysis (cite real ADR and comp count from `financial_model`) / Location Analysis (elevation, snow reliability, distance to resort) / Financial Analysis (both financing scenarios, cite exact numbers from `financial_model`) / State/STR Regulatory Notes / Risks (including STR license durability) / Final Recommendation.
3. **Condensed Summary** for each remaining candidate (3-5 sentences: rank reason, biggest strength, biggest weakness, any major gap).
4. **Final Recommendation Across Candidates.**
5. **Data Gaps & Caveats** - a plain list combining every candidate's `gaps` array, plus a reminder that sold comps/price history aren't in this version yet.
6. **Disclaimer** - research/decision support only; not a substitute for inspection, appraisal, legal/tax/lending/insurance advice, or local regulatory verification. Federal/estate tax questions are explicitly deferred to the Tax Agent and the client's own CPA/attorney.

Output ONLY the Markdown report - no preamble, no meta-commentary about your own process."""


def report():
    normalize = MARKET_JS + r"""
// One item per selected candidate. Fills in market from the address when the
// Finder didn't supply it, and records what's missing as gaps.
const input = $input.first().json.body || $input.first().json;
const client_goals = input.client_goals || {};
const candidates = Array.isArray(input.candidates) ? input.candidates : [];

return candidates.map(c => {
  const gaps = Array.isArray(c.gaps) ? [...c.gaps] : [];
  let market = c.market || null;
  if (!market) {
    market = resolveMarket(c.address);
    if (market) gaps.push(`Market not supplied by the Finder; derived as "${market}" from the address.`);
    else gaps.push('Market could not be determined for this candidate - rental comps and reference data unavailable.');
  }
  if (typeof c.lat !== 'number' || typeof c.lng !== 'number') {
    gaps.push('Candidate has no coordinates - elevation lookup skipped.');
  }
  return { json: { ...c, market, client_goals, gaps } };
});
"""
    distinct = r"""// Rental comps are per market, not per property: fetch each market once.
const markets = [...new Set($input.all().map(i => i.json.market).filter(Boolean))];
if (markets.length === 0) return [{ json: { market: null } }];
return markets.map(market => ({ json: { market } }));
"""
    attach = REFERENCE_TABLES_JS + r"""
// Joins each candidate with its market's rental comps and reference data.
// Get Rental Comps returns one item per market, in the same order as
// Distinct Markets.
const compsRan = $('Get Rental Comps').isExecuted;
const marketItems = compsRan ? $('Distinct Markets').all().filter(i => i.json.market) : [];
const compsItems = compsRan ? $('Get Rental Comps').all() : [];
const compsByMarket = {};
const alignmentGap = compsRan && compsItems.length !== marketItems.length
  ? `Rental comps returned ${compsItems.length} result(s) for ${marketItems.length} market(s) - comps were not attached.`
  : null;
if (!alignmentGap) {
  marketItems.forEach((m, i) => { compsByMarket[m.json.market] = compsItems[i] ? compsItems[i].json : null; });
}

return $('Normalize And Split').all().map(item => {
  const c = item.json;
  const market = c.market;
  const comps = market ? compsByMarket[market] : null;
  const reference_data = {
    snow_reliability: snowReliability[market] || null,
    build_rehab_cost: buildRehabCost[market] || null,
    str_regulatory_status: strRegulatoryStatus[market] || null
  };
  const gaps = [...(c.gaps || [])];
  if (alignmentGap) gaps.push(alignmentGap);
  if (comps && comps.error) gaps.push(`Rental comps lookup failed for market "${market}": ${String(comps.error.message || comps.error).slice(0, 200)}`);
  if (comps && Array.isArray(comps.gaps)) gaps.push(...comps.gaps.map(g => `Rental comps (${market}): ${g}`));
  if (market && (!comps || !Array.isArray(comps.candidates) || comps.candidates.length === 0)) {
    gaps.push(`No STR rental comps found for market "${market}" - revenue model cannot be computed from real data.`);
  }
  if (market && !reference_data.snow_reliability) gaps.push(`No snow reliability data for market "${market}" - not one of the researched markets.`);
  if (market && !reference_data.build_rehab_cost) gaps.push(`No build/rehab cost data for market "${market}".`);
  if (market && !reference_data.str_regulatory_status) gaps.push(`No STR license/regulatory data for market "${market}" - verify locally before relying on STR viability.`);
  gaps.push('Sold comps and detailed price history are not yet wired into this Report Agent version - not available for this report.');

  return {
    json: {
      ...c,
      rental_comps: (comps && Array.isArray(comps.candidates)) ? comps.candidates : [],
      rental_comps_source_count: comps ? (comps.source_count || 0) : 0,
      rental_comps_stay: comps ? { check_in: comps.check_in || null, check_out: comps.check_out || null } : null,
      reference_data,
      gaps
    }
  };
});
"""
    merge_elev = r"""// Get Elevation runs once per candidate (errors continue as items), so its
// outputs line up with Attach Comps And Reference Data by position.
const cands = $('Attach Comps And Reference Data').all().map(i => i.json);
const elev = $input.all().map(i => i.json);
const aligned = elev.length === cands.length;

return cands.map((c, idx) => {
  const gaps = [...(c.gaps || [])];
  const hasCoords = typeof c.lat === 'number' && typeof c.lng === 'number';
  const res = aligned && elev[idx] && Array.isArray(elev[idx].results) ? elev[idx].results[0] : null;
  const elevation_ft = hasCoords && res && typeof res.elevation === 'number'
    ? Math.round(res.elevation * 3.28084)
    : null;
  if (hasCoords && elevation_ft === null) gaps.push('Elevation lookup failed or returned no data for this candidate.');
  return { json: { ...c, elevation_ft, elevation_source: 'Open-Elevation', gaps } };
});
"""
    aggregate = ("const items = $input.all().map(i => i.json);\n"
                 "const client_goals = items.length ? items[0].client_goals : null;\n"
                 "return [{ json: { client_goals, candidates: items, generated_at: $now.toISO() } }];")
    nodes = [
        node("Investor Selection", "n8n-nodes-base.webhook", 2.1, 0, 0,
             {"httpMethod": "POST", "path": "report-agent", "responseMode": "responseNode", "options": {}},
             webhookId="ra-webhook-0000-0000-000000000001"),
        node("Normalize And Split", "n8n-nodes-base.code", 2, 224, 0, {"jsCode": normalize}),
        node("Distinct Markets", "n8n-nodes-base.code", 2, 448, 0, {"jsCode": distinct}),
        node("Has Market?", "n8n-nodes-base.if", 2.3, 672, 0, {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 3},
                           "conditions": [{"id": "market-0001", "leftValue": "={{ $json.market }}", "rightValue": "",
                                           "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}}],
                           "combinator": "and"}, "options": {}}),
        node("Get Rental Comps", "n8n-nodes-base.executeWorkflow", 1.2, 896, -100, {
            "source": "database",
            "workflowId": {"mode": "id", "__rl": True, "value": AIRBNB_WF},
            "mode": "each",
            "workflowInputs": {"mappingMode": "defineBelow", "matchingColumns": [], "schema": [],
                               "value": {"max_results": 8, "num_of_adults": 2, "location": "={{ $json.market }}"}},
            "options": {}}, onError="continueRegularOutput"),
        node("Attach Comps And Reference Data", "n8n-nodes-base.code", 2, 1120, 0, {"jsCode": attach}),
        node("Get Elevation", "n8n-nodes-base.httpRequest", 4.5, 1344, 0, {
            "url": "=https://api.open-elevation.com/api/v1/lookup?locations={{ $json.lat }},{{ $json.lng }}",
            "options": {"timeout": 30000}}, onError="continueRegularOutput", retryOnFail=True, maxTries=2, waitBetweenTries=2000),
        node("Merge Elevation", "n8n-nodes-base.code", 2, 1568, 0, {"jsCode": merge_elev}),
        node("Compute Financial Model", "n8n-nodes-base.code", 2, 1792, 0, {"mode": "runOnceForEachItem", "jsCode": FIN_MODEL_JS}),
        node("Aggregate Candidates", "n8n-nodes-base.code", 2, 2016, 0, {"jsCode": aggregate}),
        node("Report Agent", "@n8n/n8n-nodes-langchain.agent", 3.1, 2240, 0,
             {"promptType": "define", "text": "={{ JSON.stringify($json) }}", "options": {"systemMessage": REPORT_PROMPT}}),
        node("Model - Claude Sonnet", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.5, 2192, 240,
             {"model": {"__rl": True, "mode": "list", "value": "claude-sonnet-4-6", "cachedResultName": "Claude Sonnet 4.6"}, "options": {}},
             credentials=ANTHROPIC_CRED),
        node("Return Report", "n8n-nodes-base.respondToWebhook", 1.5, 2464, 0,
             {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}}),
    ]
    conns = main_conn([
        ("Investor Selection", ["Normalize And Split"]),
        ("Normalize And Split", ["Distinct Markets"]),
        ("Distinct Markets", ["Has Market?"]),
        ("Has Market?", ["Get Rental Comps"], ["Attach Comps And Reference Data"]),
        ("Get Rental Comps", ["Attach Comps And Reference Data"]),
        ("Attach Comps And Reference Data", ["Get Elevation"]),
        ("Get Elevation", ["Merge Elevation"]),
        ("Merge Elevation", ["Compute Financial Model"]),
        ("Compute Financial Model", ["Aggregate Candidates"]),
        ("Aggregate Candidates", ["Report Agent"]),
        ("Report Agent", ["Return Report"]),
    ])
    ai_conn(conns, "Model - Claude Sonnet", "ai_languageModel", "Report Agent")
    return {"name": "Report Agent", "nodes": nodes, "connections": conns, "settings": SETTINGS, "pinData": {}}


FILES = {
    "BrightData - Zillow Search (fixed).json": zillow,
    "BrightData - Airbnb Search (fixed).json": airbnb,
    "Finder Agent (fixed).json": finder,
    "Publish Candidates to Sheet (fixed).json": publisher,
    "Report Agent (fixed).json": report,
}

if __name__ == "__main__":
    for fname, fn in FILES.items():
        wf = fn()
        import uuid
        for n in wf["nodes"]:
            n.setdefault("id", str(uuid.uuid5(uuid.NAMESPACE_URL, "rei-fixed/" + wf["name"] + "/" + n["name"])))
            if n["type"] == "n8n-nodes-base.wait":
                n.setdefault("webhookId", str(uuid.uuid5(uuid.NAMESPACE_URL, "rei-fixed-wait/" + wf["name"] + "/" + n["name"])))
        names = {n["name"] for n in wf["nodes"]}
        assert len(names) == len(wf["nodes"]), fname + ": duplicate node names"
        for src, kinds in wf["connections"].items():
            assert src in names, (fname, src)
            for outs in kinds.values():
                for out in outs:
                    for t in out:
                        assert t["node"] in names, (fname, src, t["node"])
        with open(os.path.join(OUT, fname), "w") as f:
            json.dump(wf, f, ensure_ascii=False, separators=(",", ":"))
        # extract every Code node for syntax checking
        for n in wf["nodes"]:
            code = n["parameters"].get("jsCode")
            if code:
                safe = "".join(ch if ch.isalnum() else "_" for ch in fname.split(" (")[0] + "__" + n["name"])
                with open(os.path.join(OUT, "js", safe + ".js"), "w") as f:
                    f.write("async function __node($input, $, $json, $now) {\n" + code + "\n}\nmodule.exports = __node;\n")
        print("ok", fname, len(wf["nodes"]), "nodes", os.path.getsize(os.path.join(OUT, fname)), "bytes")
