const assert = require('assert');
const load = f => require('./js/' + f + '.js');
const items = arr => arr.map(j => ({ json: j }));
const mkInput = arr => { const it = items(arr); return { all: () => it, first: () => it[0], item: it[0] }; };
const mkCtx = nodes => name => { const n = nodes[name]; return n ? { ...mkInput(n), isExecuted: true } : { all: () => [], first: () => undefined, isExecuted: false }; };
const run = async (f, input, nodes = {}) => load(f)(mkInput(input), mkCtx(nodes), input[0], { toISO: () => '2026-10-03T00:00:00Z' });

(async () => {
  // Zillow normalize, direct (sync) path
  const crit = { location: 'Park City, UT', lat: 40.6514, lng: -111.508, budget_max: 1300000, min_beds: 2, radius_miles: 15, max_results: 10 };
  const recs = [
    { url: 'https://www.zillow.com/homedetails/a', streetAddress: '1 A St', city: 'Park City', state: 'UT', zipcode: '84098', price: 999000, bedrooms: 4, bathrooms: 3, livingArea: 2000, latitude: 40.70, longitude: -111.55, homeType: 'SINGLE_FAMILY', homeStatus: 'FOR_SALE' },
    { url: 'https://www.zillow.com/homedetails/b', city: 'Park City', state: 'UT', price: 2500000, bedrooms: 5, latitude: 40.66, longitude: -111.50 },
    { streetAddress: 'no url' }];
  let out = await run('BrightData___Zillow_Search__Normalize_Candidates', recs, { 'Build Bright Data Query': [crit] });
  let r = out[0].json;
  assert.equal(r.candidates.length, 1); assert.equal(r.candidates[0].market, 'Park City, UT');
  assert.equal(r.candidates[0].lat, 40.70); assert.equal(r.source_count, 2);
  out = await run('BrightData___Zillow_Search__Normalize_Candidates', [{}], { 'Build Bright Data Query': [crit] });
  assert.equal(out[0].json.candidates.length, 0); assert.match(out[0].json.gaps[0], /no listings/);
  console.log('zillow normalize ok');

  // Finder enforce: fenced JSON, fake URL dropped
  out = await run('Finder_Agent__Enforce_Real_Listing_Rule', [{ output: '```json\n{"candidates":[{"url":"https://www.zillow.com/x","market":"Vail, CO"},{"url":"https://fake.example.com/1"}],"gaps":[]}\n```' }]);
  assert.equal(out[0].json.candidates_found, 1); assert.match(out[0].json.gaps[0], /dropped/);
  console.log('finder enforce ok');

  // Publisher: dedupe against sheet + within batch
  const split = await run('Publish_Candidates_to_Sheet__Split_Candidates', [{ body: { candidates: [
    { url: 'https://www.zillow.com/x', address: 'X', price: 1, market: 'Vail, CO', distance_miles_from_resort: 3.456 },
    { url: 'https://www.zillow.com/x' }, { url: 'https://www.zillow.com/old' }, { address: 'nourl' }] } }]);
  out = await run('Publish_Candidates_to_Sheet__Keep_New_Only', [{}], { 'Read Existing Rows': [{ URL: 'https://www.zillow.com/old' }], 'Split Candidates': [split[0].json] });
  r = out[0].json; assert.equal(r.appended, 1); assert.equal(r.skipped_existing, 2); assert.equal(r.skipped_no_url, 1);
  assert.equal(r.rows[0]['Distance to resort (mi)'], 3.5);
  // empty sheet: Read Existing Rows emits one empty item (alwaysOutputData)
  out = await run('Publish_Candidates_to_Sheet__Keep_New_Only', [{}], { 'Read Existing Rows': [{}], 'Split Candidates': [split[0].json] });
  assert.equal(out[0].json.appended, 2);
  console.log('publisher ok');

  // Report chain: 3 candidates, 2 markets (one derived from address), one no-market
  const body = { client_goals: { personal_use_weeks_per_year: 3, reserve: 100000 }, candidates: [
    { address: '1 A St, Park City, UT, 84098', price: 999000, url: 'u1', market: 'Park City, UT', lat: 40.7, lng: -111.55, distance_miles_from_resort: 6.5 },
    { address: '2 B Rd, Vail, CO, 81657', price: 1200000, url: 'u2', lat: 39.64, lng: -106.37, distance_miles_from_resort: 3 },
    { address: '9 Z Ln, Boise, ID', price: 800000, url: 'u3' }] };
  const norm = (await run('Report_Agent__Normalize_And_Split', [{ body }])).map(i => i.json);
  assert.equal(norm[1].market, 'Vail, CO'); assert.equal(norm[2].market, null);
  const dm = (await run('Report_Agent__Distinct_Markets', norm)).map(i => i.json);
  assert.deepEqual(dm.map(m => m.market), ['Park City, UT', 'Vail, CO']);
  const comps = [ { candidates: [{ nightly_price: 400 }, { nightly_price: 600 }], source_count: 2, gaps: [] },
                  { candidates: [{ nightly_price: 900 }], source_count: 1, gaps: ['sample note'] } ];
  const att = (await run('Report_Agent__Attach_Comps_And_Reference_Data', [{}], { 'Get Rental Comps': comps, 'Distinct Markets': dm, 'Normalize And Split': norm })).map(i => i.json);
  assert.equal(att.length, 3); assert.equal(att[0].rental_comps.length, 2); assert.equal(att[1].rental_comps[0].nightly_price, 900);
  assert.ok(att[0].reference_data.snow_reliability); assert.equal(att[2].rental_comps.length, 0);
  const elev = [{ results: [{ elevation: 2100 }] }, { error: { message: 'timeout' } }, { error: { message: 'bad request' } }];
  const merged = (await run('Report_Agent__Merge_Elevation', elev, { 'Attach Comps And Reference Data': att })).map(i => i.json);
  assert.equal(merged[0].elevation_ft, 6890); assert.equal(merged[1].elevation_ft, null);
  assert.ok(merged[1].gaps.some(g => /Elevation lookup failed/.test(g)));
  assert.ok(!merged[2].gaps.some(g => /Elevation lookup failed/.test(g)));
  const fm = load('Report_Agent__Compute_Financial_Model');
  const fin = await fm({ item: { json: merged[0] } }, null, merged[0]);
  assert.equal(fin.json.financial_model.adr_from_real_comps, 500); assert.equal(fin.json.financial_model.rentable_nights_per_year, 344);
  const fin3 = await fm({ item: { json: merged[2] } }, null, merged[2]);
  assert.equal(fin3.json.financial_model, null);
  console.log('report chain ok', JSON.stringify(fin.json.financial_model.financed_20pct_down_5_88pct_15yr));
})().catch(e => { console.error('FAIL', e); process.exit(1); });
