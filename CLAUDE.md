# Notes for Claude

## Building AI agents

Before designing or building any AI agent (n8n workflows, system prompts, tool descriptions), read `agent-playbook/PLAYBOOK.md`. It holds the methodology this user works with (the Golden Alchemist "AI Agent Bible": prompt sections A-N, dynamic/static tool split, deterministic guardrails, `gaps` output, node-by-node build process), plus a list of practices from the reference material that should not be copied.

- `agent-playbook/real-estate-pipeline.md` covers the ski-rental Finder / Report / Tax agent pipeline: contracts, data sources, assumptions and known issues.
- `agent-playbook/n8n-snippets.md` has reusable Code-node snippets and prompt skeletons.

The source files live in the Google Drive folder `RealEstateInvestor` (id `1e7FTkt5WlEzASBKTlm_8Yo1KIZg0HE_D`). Re-read them with the Google Drive connector if they may have changed. Large n8n JSON exports come back truncated at about 250k characters; parse the saved tool-result file and cut at `"connections"` to recover the nodes.
