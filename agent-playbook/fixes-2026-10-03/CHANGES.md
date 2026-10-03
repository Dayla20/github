# Fixed n8n workflows: change notes (2026-10-03)

These fixes are based on the live exports uploaded on 2026-10-03. They fix the four bugs that stop the pipeline from producing results. Design changes are deliberately left out (the client brief, seasonal rental income, and saving the report), since they depend on the target design.

Tax Agent: no changes.

## How to import (keeps workflow IDs, so cross-workflow links keep working)

For each file:

1. Open the **existing** workflow in n8n.
2. Select all nodes and delete them.
3. Use **⋯ → Import from File** to load the fixed file.
4. Save.

Importing as a new workflow instead would give it a new ID and break the links between workflows.

Credentials are referenced by the same IDs as before (Anthropic, Bright Data-Datasets API, Google Sheets). If a node shows "credential not found", re-select it.

Import order:
1. Zillow Search
2. Airbnb Search
3. Publish Candidates to Sheet
4. Finder Agent
5. Report Agent

## 1. BrightData - Zillow Search (fixed)

**Bug:** the workflow calls Bright Data's synchronous `/scrape` endpoint, then always waits for a `snapshot_id`. Bright Data only sends a `snapshot_id` (HTTP 202) when results take longer than about 1 minute. Otherwise it returns the listings directly. On a fast search the loop polled `/progress/undefined` for 15 minutes and reported "no data".

**Changes:**
- New `Got Snapshot ID?` IF node after the search. If there's a snapshot ID, it polls as before. If not, it sends the listings straight to `Normalize Candidates`.
- Search node: retry is back on (3 tries, 2 s apart), and "always output data" is set so an empty result still continues.
- `Normalize Candidates` now adds `lat`, `lng` and `market` to every property. `market` uses the Report Agent's market names ("Park City, UT", "Steamboat Springs, CO", "Jackson Hole, WY", "Vail, CO") and falls back to "City, ST".
- It also adds a `gaps` note when nothing was found or nothing passed the filters.

**Test:** open the workflow, run it with the pinned test input (Park City, budget up to $1.3M), and check that `candidates` have `market`, `lat` and `lng`.

## 2. BrightData - Airbnb Search (fixed)

**Bug:** this is the same synchronous/asynchronous issue as the Zillow search.

**Changes:**
- The same `Got Snapshot ID?` routing, plus retries and "always output data".
- The output now includes the `check_in` and `check_out` dates that were sampled.
- It adds a gap note when Bright Data returns nothing.

The stay is still 3 nights, 30 days out. Sampling peak, summer and shoulder seasons is a design change.

**Test:** execute with `location = "Park City, UT"` and check that `candidates` contains nightly prices.

## 3. Publish Candidates to Sheet (fixed)

**Bugs:**
- The "Get row(s)" node had no sheet selected.
- An empty sheet stopped the flow before anything was written.
- Columns were filled from the wrong fields.
- Nothing split the list of properties into rows.
- There was no reply to the webhook.
- Nothing called this workflow.

**Changes:** the flow is now Webhook *or* call from Finder → split candidates → read existing rows → drop URLs already in the sheet or repeated in the batch → append one row per new property → summary → reply (webhook calls only).
- Columns written: Address, Price, Beds, Baths, SqFt, Market, Distance to resort (mi, 1 decimal), URL, Date Added, Status = "New".
- Report Doc Link is left empty for now.

**Check after import:**
- Both Google Sheets nodes point at tab `gid=0`, which should be "Master List" (the first tab). If it isn't, re-select the tab in both nodes.

**Test:** POST `{"candidates":[{"url":"https://www.zillow.com/test","address":"Test","price":1}]}` to the test webhook URL.
- First run: it should return `appended: 1` and add one row.
- Second run: it should return `skipped_existing: 1`.
- Delete the test row afterwards.

## 4. Finder Agent (fixed)

**Bug:** properties were returned without market or coordinates, and nothing published them to the sheet.

**Changes:**
- **Prompt and tool description:** the output now includes `market`, `lat` and `lng` for every property, copied exactly from `search_listings`. The search tool's gap notes are copied into the output.
- **`Enforce Real-Listing Rule`:** it now strips stray ```` ```json ```` fences before parsing, and notes any property that has no market.
- **New `Publish to Tracker Sheet` node:** it runs after the webhook reply and calls the publisher without waiting for it. If publishing fails, the search result is still returned.

**Test:** POST `{"resort_name":"Park City Mountain Resort","state":"UT"}` to the Finder webhook. Each property should have `market`, `lat` and `lng`, and new rows should appear in the tracker sheet.

## 5. Report Agent (fixed)

**Bug:** `Get Rental Comps` ran once for all items, so only the first property reached the report. It also depended on `market`, `lat` and `lng`, which never arrived.

**Changes:**
- **`Normalize And Split`:** if `market` is missing, it derives it from the address. A missing market or missing coordinates are recorded as gaps.
- **New `Distinct Markets` and `Has Market?` nodes:** rental comps are fetched **once per market** ("Run once for each item"), not once per property. That also saves duplicate Bright Data charges.
- **`Attach Comps And Reference Data`:** this replaces `Load Reference Tables` and `Merge Candidate Data`. The reference tables are unchanged. It attaches comps and reference data to **every** property and passes the comps' own gaps through.
- **`Get Elevation`:** errors no longer stop the run, it now has a timeout and retries, and **`Merge Elevation`** matches results back to each property.
- **Unchanged:** the financial model, aggregation, Report Agent prompt and reply.

**Test:** POST a body containing 2–3 Finder candidates from different markets, plus `client_goals` (`personal_use_weeks_per_year`, `reserve`). The report's comparison table should list **every** property.

## Verified before upload

- All 19 Code nodes pass a JavaScript syntax check.
- The changed nodes were run against mock n8n data:
  - Zillow normalize, on both the direct path and the empty path
  - The fake-URL filter
  - Sheet de-duplication, against an empty sheet and an existing one
  - The full Report chain with 3 properties across 2 markets, including a failed elevation lookup and a property with no market
- Every connection points to an existing node.

## Not yet tested

These can only be checked by running the workflows inside n8n:
- the n8n-specific settings: per-item mode on `Get Rental Comps`, "don't wait" on the publisher call, and the "was this node run" checks in two Code nodes
- the Google Sheets tab selection
- live Bright Data responses

If a node errors after import, copy the error from the right-hand panel and send it back.
