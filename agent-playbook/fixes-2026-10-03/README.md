# Fixed n8n workflows (2026-10-03)

`build.py` generates the five fixed workflow exports (Zillow search, Airbnb search, sheet publisher, Finder Agent, Report Agent) into this folder, plus a `js/` folder with each Code node wrapped for testing. `test.js` runs the changed Code nodes against mock n8n data.

```bash
mkdir -p js && python3 build.py && node test.js
```

The generated JSON files are uploaded to Drive in `RealEstateInvestor/Fixed workflows 2026-10-03`, together with the change notes (`CHANGES.md`). They aren't committed here, because `build.py` reproduces them.
