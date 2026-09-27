# Real-Estate Investment Agent Pipeline (ski-rental use case)

State of the `RealEstateInvestor/ai_agent_RealEstate` build as of 2026-09-10 (folder owned by a collaborator). Client profile: about $1.5M of total capital, $1.3M purchase budget (about 13% held back for closing, repairs and reserves), a short-term-rental strategy near a US ski resort, and some personal-use weeks.

## Evolution

1. **Aug 22: a single-agent design.** `prompt_investmentUnderwritingAgent` (46 sections: discovery → comps → FMV → location → rental/STR → opex → NOI → financing → cash flow / cap rate / CoC → break-even → flip/BRRRR → creative financing → appreciation → risk → scenarios → stress test → exit A/B/C → 0-100 deal score → STRONG BUY / BUY IF / NEGOTIATE / MONITOR / PASS). There was also a separate `intake_system_prompt.md` conversational intake agent that outputs JSON with `"unknown"` for anything missing.
2. **Sep 7-10: split into single-responsibility agents** using the Bible's methodology. The intake agent was dropped because this client's goals were already known, so a structured webhook input replaces the conversation.

## Agents and contracts

```
POST /finder-agent  {resort_name, state, max_distance_miles=15, budget_min=0, budget_max=1300000,
                     property_type='single_family', min_beds=0, min_baths=0, strategy, max_results=10}
   Finder Agent (Claude Sonnet 4.6)
     tools: geocode_location (Nominatim, US only, 1 req/s, identifying User-Agent)
            search_listings → sub-workflow "BrightData - Zillow Search"
     → Enforce Real-Listing Rule (URL allow-list: zillow, realtor, redfin, trulia, homes,
       coldwellbanker, century21, compass)
   ← {search_criteria, resolved_location{lat,lng,radius_miles}, candidates_found,
      candidates[{address, price, url, source, beds, baths, sqft, property_type,
                  listing_status, distance_miles_from_resort}], gaps[], generated_at}

      (human / client picks candidates)

POST /report-agent  {client_goals{personal_use_weeks_per_year, reserve,...}, candidates[...]}
   Normalize And Split (one item per candidate)
   → Get Rental Comps: sub-workflow "BrightData - Airbnb Search" (location = candidate.market,
     8 results, 2 adults)
   → Load Reference Tables (hard-coded, sourced, per-market): snow_reliability,
     build_rehab_cost, str_regulatory_status for Park City UT, Steamboat Springs CO,
     Jackson Hole WY, Vail CO
   → Get Elevation (Open-Elevation API, candidate lat/lng)
   → Merge Candidate Data → Compute Financial Model (Code) → Aggregate
   → Report Agent (Claude Sonnet 4.6): Markdown report
       1 comparison table (score 1-10) · 2 deep dive of the top candidate · 3 condensed summaries
       4 final recommendation · 5 data gaps & caveats · 6 disclaimer

POST /tax-agent  {chosen_property (with financial_model), cpa_document_text, client_notes}
   Tax Agent (Claude Sonnet 4.6): applies ONLY what the CPA/attorney document says, quotes it,
   and lists everything else as unanswered_questions_for_cpa. document_received=false if the
   document is empty or not real guidance. Output is JSON with a fixed disclaimer.
```

## Data sources

| Source | Use | Notes |
|---|---|---|
| Bright Data Scrapers Library, Zillow `gd_lfqkr8wm13ixtbd8f5` | For-sale listings | `POST https://api.brightdata.com/datasets/v3/scrape?dataset_id=…&type=discover_new&discover_by=input_filters`, **synchronous**, pay-per-use at $1.50 per 1k records with no minimum. The Datasets Marketplace alternative has a $250 minimum. Input is only `location, listingCategory:'House for sale', HomeType (Houses/Condos/Townhomes/Lots/Land/Multi-family), days_on_zillow, exact_address`, with **no price/bed filters and no lat/lng**. Auth: HTTP Header `Authorization: Bearer <key>` |
| Bright Data, Airbnb `gd_ld7ll037kqy322v05` | STR rental comps | `discover_by=location`, check-in/out as full ISO datetimes (default 30 days out, 3 nights). Implemented as **async polling** (snapshot_id → wait 20 s → progress → download, 25-min deadline). No discrete bed/bath/rating fields: they're parsed out of the title (`"Home in Park City · ★4.8 · 5 bedrooms · 11 beds · 4 baths"`). `price` = `pricing_details.initial_price_per_night` (confirmed 2026-09-09) |
| Nominatim (OSM) | Geocoding | Free and rate-limited. Swap for Google/Mapbox at volume |
| Open-Elevation | Elevation (ft = m × 3.28084) | |
| Hand-researched tables | Snow, build cost, STR regulation | Each entry carries `confidence` and `sources`. Conflicting source values are **flagged, not resolved** |

Confirmed Zillow record fields: `url, streetAddress, city, state, zipcode, price, bedrooms, bathrooms, livingArea/livingAreaValue, latitude, longitude, homeType, homeStatus`.

## Financial model assumptions (Report Agent `Compute Financial Model`)

ADR is the mean nightly price of the real Airbnb comps. Occupancy is 55% within 10 miles of the resort and 40% beyond that. Rentable nights = 365 − 7 × personal-use weeks. Opex = 40% of gross, closing = 3%, appreciation = 3.5%/yr, land = 20% of price. Depreciation is over 27.5 years at a placeholder 32% marginal tax rate. Two scenarios: all-cash, and financed with 20% down at 5.88% over 15 years. Outputs: gross revenue, NOI, cap rate, cash-on-cash and total return (cash flow + appreciation + depreciation tax shield) for each scenario. All of these are labeled as assumptions, and the Tax Agent refines the tax part.

## Market reference highlights (from the Report Agent tables; verify before relying on them)

- **Snow:** Jackson Hole is the deepest and most consistent (414-465" average). Steamboat has the widest year-to-year swing (174"-428"). Vail's sources disagree by about 40% (250" vs 354"). Park City/Deer Valley run about 255-277"; in 2025-26 openings were delayed and a drought emergency was declared.
- **STR rules:**
  - Park City: nightly rental license, not transferable, and zoning limits which districts qualify.
  - Steamboat: green / yellow / red overlay zones (no cap / capped / prohibited).
  - Jackson: Town of Jackson allows 60 nights and 3 stays a year outside the Lodging Overlay. Unincorporated Teton County is mostly banned outside approved developments, and that entry is **unverified**.
  - Vail: annual license, with a $1,200 per bedroom fee pending (passed first reading only).
- **Build cost ($/sqft, luxury-tier ceilings only):** Park City $500-1,000, Steamboat $500-800, Jackson $800-1,500, Vail $600-1,200.

## Output so far

`Ski Rental Candidates_-09082026.pdf` lists 15 listings under $1.3M: 10 in Park City (all in ZIP 84098, 6.4-8.8 miles from the resort), 3 in Steamboat (2.0-3.8 mi), 1 in Jackson and 1 in Vail. None of them has been underwritten. The `Ski Rental Investment - Candidate Tracker` sheet has headers only (Address, Price, Beds, Baths, SqFt, Market, Distance, URL, Date Added, Status, Report Doc Link), and no workflow writes to it yet.

About 15.5 hours had been logged by Sep 8 (per `Finder_Agent_Time_Log.md`).

## Known issues / next steps (found while reviewing the exports)

1. **Finder → Report contract mismatch.** The Report Agent reads `candidate.market`, `candidate.lat` and `candidate.lng`, but Finder candidates carry none of them. Without a mapping step, rental comps get `location: undefined`, the reference tables come back null, and the elevation lookup fails. Fix: have Zillow `Normalize Candidates` emit `lat`, `lng` and `market` (e.g. `${city}, ${state}` mapped to the four market keys), or add a mapping node in front of the Report Agent.
2. **Rental comps are fetched once per candidate**, even when several candidates share a market. That's duplicate paid Bright Data calls; cache per market.
3. **ADR comes from a single 3-night stay 30 days out**, with 2 adults and no size matching. For ski STR this misses seasonality entirely: peak winter vs shoulder vs summer. Sample several stay windows and filter comps by bedroom count against the candidate.
4. **Sold comps and price history are not wired in yet.** The Report Agent says this in its gaps, so a fair-market-value analysis (sections 10-13 of the underwriting prompt) isn't possible yet.
5. The candidate tracker sheet isn't written to by any workflow; add a Google Sheets append after the Finder.
6. `Finder_Agent_Build_Guide.md` still says GPT-5.1 for the Finder, but the live export (`Finder Agent.json`) uses Claude Sonnet 4.6. `Finder_Agent.json` is the older Sep 8 version (GPT-5.1, placeholder sub-workflow ID).
7. Tax treatment beyond the placeholder is deliberately deferred to the Tax Agent and the client's CPA document. Keep it that way.
