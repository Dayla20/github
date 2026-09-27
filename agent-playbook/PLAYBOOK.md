# Agent-Building Playbook

Distilled from the `RealEstateInvestor` Google Drive folder (Golden Alchemist "AI Agent Bible", the Diana v5 sales-agent brain + skeleton, and the ski-rental Finder / Report / Tax agent pipeline). Use this as the starting point whenever building a new n8n + LLM agent.

Source files (Drive folder `RealEstateInvestor`, id `1e7FTkt5WlEzASBKTlm_8Yo1KIZg0HE_D`):

| File | What it is |
|---|---|
| `ai_bible_ga/ai_agent_bible` | The methodology (Spanish). Parts 1-9: principles, architecture, prompt sections A-N, tool descriptions, Frankenstein splitter, psychology, anti-patterns, n8n build, templates |
| `ai_bible_ga/prompt_HowToUse_bible` | Meta-prompt for having Claude build an agent: feed Bible → feed reference JSON → discovery (5 question blocks) → architecture summary → node-by-node build |
| `ai_bible_ga/brain_diana_ga.json` | "Cerebro Diana v5": 17-node agent core (agent + 8 tools + memory + splitter) |
| `ai_bible_ga/skeleton_ga.json` | "Esqueleto Agente Builders": 68-node full WhatsApp/Chatwoot pipeline around the same brain |
| `ai_agent_RealEstate/*` | Ski-rental investing pipeline, see [real-estate-pipeline.md](real-estate-pipeline.md) |
| top-level `prompt_investmentUnderwritingAgent`, `intake_system_prompt.md` | Original single-agent underwriting prompt (46 sections) and conversational intake prompt |

---

## 1. Pick the archetype first

Everything else follows from which kind of agent you're building.

| | **Conversational agent** (Diana) | **Structured tool agent** (Finder / Report / Tax) |
|---|---|---|
| Talks to | A human, in real time (WhatsApp via Chatwoot) | Another system (webhook in → JSON/Markdown out) |
| Goal | Move the human to one action (buy, book, qualify) | Produce one well-defined artifact |
| Prompt sections needed | A-N (all of them, L/M optional) | A (identity/scope), F (tool map), J (limits), N (final rules) + an explicit OUTPUT FORMAT |
| Humanization | Critical (Sections B + H) | Irrelevant: output ONLY JSON, no prose |
| Memory | Postgres chat memory, window 8 | None (stateless per request) |
| Post-processing | Splitter → multi-message send with delays | Deterministic Code node: parse + validate + enforce rules |

The Finder build guide says it explicitly: the Bible was written for WhatsApp sales agents; for a data agent you keep A/F/J/N and drop B/C/D/G/H/I/K/L/M.

---

## 2. Twelve principles (from the Bible, Part 1.2)

1. **Objective above all**: every response moves toward the goal.
2. **Modular specialization**: one agent, one job. The orchestrator coordinates, tools hold the data, and sub-agents are added only when needed.
3. **Verifiable information > creativity**: never invent. If you don't know, call a tool, and if the tool doesn't have it, report the gap.
4. **Proven frameworks > intuition** (Voss, Hormozi, Cialdini, Kahneman, Belfort).
5. **Human first** (conversational only): split messages, casual punctuation, no final period.
6. **Direct answer first**, no preamble ("Great question!").
7. **Smart escalation**: know when a human is needed, and never promise contact.
8. **Clear limits**: each limit gets ONE redirect sentence.
9. **Intent detection**: high → close now; medium → nurture then close; low → qualify first.
10. **Outcome > features.**
11. Never disparage the cheaper option.
12. **Data-driven iteration**: improve from real transcripts, not guesses.

The nine fatal errors mirror these principles: a generic prompt, no knowledge base, no objection handling, robotic formatting, never closing, no personality, no limits, disparaging the cheaper plan, and never iterating.

---

## 3. Architecture

```
Trigger (webhook / WhatsApp)
  → Normalize (Set/Code: typed fields + defaults)
  → [conversational only] media → text, Redis debounce buffer
  → AI Agent node (system prompt) ── Model
        ├─ tool: DYNAMIC data   (single source of truth, wins over prompt)
        ├─ tool: STATIC data    (deep reference)
        ├─ tool: specialized    (objections, success stories, calculators)
        ├─ tool: escalate_to_human   (Telegram, notify only)
        └─ tool: report_knowledge_gap (Telegram, continuous improvement)
  → Deterministic Code node (parse output, enforce hard rules, fail-safe)
  → Respond / send
```

Key decisions:
- **Dynamic vs static data separation is critical.** Anything that changes (prices, dates, links, quotas) lives in ONE tool. If the prompt and the tool disagree, **the tool wins**, so say that in the prompt.
- **Knowledge tools = Google Docs (<50 docs, structured, precision-critical) vs RAG (100+ docs, semantic search).** Diana has since moved from Google Docs tools to `toolCode` nodes that `return` a big Markdown string, which is the same idea with lower latency and no Docs API calls.
- **Sub-agents only if iteration proves tools aren't enough.** In the Bible's estimate, 90% of cases are handled with well-written doc tools.
- **Memory:** Postgres (Supabase) chat memory, `contextWindowLength: 8` (4 exchanges). Raise it to 12 for long qualification flows. Use a custom session key with a fallback: `sessionid || sender || 'unknown_' + Date.now()`.
- **Models seen in use:** GPT-5.2 is the Bible's recommended orchestrator (tool calling). The real-estate agents run Claude Sonnet 4.6 (`claude-sonnet-4-6`) via `lmChatAnthropic`. The splitter uses the Bible's Sonnet 4.6 at temperature 0.2 and 500 max tokens (Diana v5 actually uses GPT-5.2). For new builds, default to the latest Claude models.

---

## 4. System prompt: sections A-N (Bible Part 3)

Section headers use `=== SECTION X: NAME ===` so the model (and you) can navigate.

| § | Name | Purpose / must include |
|---|---|---|
| A | Identity | "You are [NAME] of [COMPANY]. [ROLE]. Your job: [OBJECTIVE]. Period." + current datetime via `{{$now.setZone('TZ').toFormat(...)}}` + who you are (3-5 traits) + who you are NOT |
| B | Anti-bot format | Zero markdown, max N chars (250-350), max 2 line breaks, no lists, no document structure, vary length |
| C | Conversation flow | **MASTER RULE first**: on any signal of the desired action, execute immediately. Then phases: Opening (0-2 msgs) → Discovery (2-5) → Presentation (5-8) → Objections (label first, loop ≤2-3) → Close (rotate variations). **Anti-consultant rule:** 8+ messages without the main action → stop explaining and close |
| D | Post-action | Mode switch once the user completes the action: zero selling, next step, support redirect. List trigger phrases (explicit + implicit, e.g. screenshots) |
| E | Escalation | Trigger words → one redirect sentence → call escalation tool → STOP. **Never** "we'll contact you" |
| F | Tool map | Each tool: name → contents → when to use. Priority rules. "Never write a tool name in the reply to the user" |
| G | Repetition limiter | Counters: max links, max price mentions, max social proof (2), never the same closing line twice |
| H | Tone | Personality, expressions, allowed emojis, bridge phrases, **banned phrases list**, punctuation rules |
| I | Psychology | Outcome > features, loss aversion, reference-point anchoring, straight line, with ready-made phrases |
| J | Limits | "YOUR JOB IS X. Everything else → [channel]". Per category: don't / reply / if they insist |
| K | Product philosophy | One sentence that defines the product's essence, used to answer "does it work for my case?" |
| L/M | Upgrades / plan philosophy | Optional |
| N | Final rules | 10-15 condensed critical rules + closing philosophy |

**Diana v5 evolved beyond A-N** (the prompt reaches 138k characters). It shows what production iteration looks like:
- A **"CORE: 23 rules that never break"** block goes *before* Section A.
- **Gating rules**: no price before at least one discovery answer, except when the purchase detector fires.
- **N: intent classifier** (HIGH / MEDIUM / LOW) with a different behaviour for each tier, and "accelerate when intent rises, soften when it falls".
- **P: conversion killers**, each with a measured cost. There is also a "3-filter rule": every message must (a) advance the funnel, (b) build trust, or (c) create *real* urgency.
- **α meta-rules: precedence between sections** (Z > T > F), **industry latching** (keep the user's industry as the anchor for 3+ messages), **freshness** (vary a phrase after 3 uses), and **tone mirroring**.
- **EE: tool enforcement**, derived from transcript analysis ("calculate_roi fired 0% in 3 days"). This is proof that tools get under-used unless the prompt makes each trigger an obligation.
- **Operational rules for downstream systems**, e.g. "single quotes only, double quotes break the Chatwoot JSON" and "never use an em-dash (reads as AI)".
- Sections are versioned (v7.3, v9.2, and so on), and each one says which transcript analysis produced it.

Lesson: **start with A-N; add numbered, versioned sections only as transcript analysis finds specific failures.** Give each change a measured reason. Keep a precedence rule once sections overlap.

---

## 5. Tool descriptions (Bible Part 4)

Every tool description has four parts. The post-use instructions are what stop the agent from breaking promises (for example "don't say we'll contact you").

```
[What it does in 1-2 sentences]

USE OBLIGATORILY when:
- [trigger 1]
- [trigger 2]

NEVER use for:
- [anti-trigger 1]

AFTER using this tool:
- [post-use instruction]
```

Tool types:
- **Dynamic data tool**: "ALL data that CHANGES. SINGLE SOURCE OF TRUTH. Call BEFORE answering about prices/dates/links… If data can change, ALWAYS call this."
- **Static data tool**: depth on syllabus/structure/guarantees; "do NOT use for data that changes".
- **Escalation (Telegram)**: notify only. The post-use rule is to give the support channel, promise nothing, and stop selling. Message via `$fromAI('mensaje', '<structured: name, reason, summary, interest level>')`.
- **Knowledge-gap report (Telegram)**: exact question, what's missing, and which doc to update. After use: "let me confirm with the team, meanwhile here's what I do know…"
- **Calculator tools** (`toolCode`): deterministic JS that returns text plus usage instructions for the agent (Diana's `calculate_roi`).

In n8n, use `$fromAI('name', 'description incl. example', 'type')` for every model-filled parameter, and write the description as carefully as the tool description.

---

## 6. Deterministic guardrails (the part that actually enforces rules)

The real-estate pipeline adds a principle the Bible only implies: **prompts are not guarantees; enforce hard rules in Code nodes after the model.**

- **Parse-or-fail-safe**: strip ```` ```json ```` fences, `JSON.parse`, and on failure return a valid empty-shaped object with a `gaps` entry and `raw_output` (truncated), never a crash.
- **Real-source enforcement**: drop any candidate whose `url` isn't on an allow-listed domain, and record the count dropped in `gaps`.
- **`gaps` as a first-class output field**: an honest "nothing found / data missing" beats a fabricated result. Every agent in the pipeline carries and appends to `gaps`.
- **Compute numbers in code, narrate with the LLM**: the Report Agent's financial model is a Code node, and the LLM is told "never recalculate or override any number in `financial_model`".
- **Filter in code when the API can't**: Bright Data's Zillow endpoint has no price/bed filters, so fetch broadly and filter client-side (with Haversine distance).
- **Bounded retries**: "call search at most twice (original + one labeled relaxation)" in the prompt, plus HTTP timeout 120 s and `retryOnFail`, maxTries 3, 2 s wait on the node.
- **Data-quality labels**: VERIFIED / REPORTED / ESTIMATED / UNKNOWN (from the underwriting prompt), and `confidence` + `sources` on every reference-table entry.
- **Defer to licensed professionals**: the Tax Agent may only apply treatments that are explicitly in the client's CPA/attorney document, must cite the excerpt, and lists everything else as questions for the CPA.

Snippets for all of these are in [n8n-snippets.md](n8n-snippets.md).

---

## 7. Conversational delivery pipeline (Diana skeleton)

1. **Chatwoot webhook** → `¿Es mensaje entrante?` (`message_type == incoming`) → `Humano?` (skip if the conversation label contains `humano`, i.e. a human took over).
2. **Organizador (Set)**: conversation_id, sender phone, attachment `data_url`, text, timestamp, session id, Chatwoot token.
3. **Identificador_formato (Switch)**: audio/image vs text; PDF branch too.
   - Audio → download → OpenAI transcribe (`language: es`).
   - Image → GPT-4o analyze with the prompt "describe it in first person as if the customer wrote it in WhatsApp".
   - PDF → `extractFromFile`.
4. **Redis debounce buffer**: push `{message, sessionId, date_time}` to a list keyed by sender, then wait 23 s and read the list. A switch then decides:
   - **Ignore** if the last entry belongs to a different execution.
   - **Continue** if the last message is more than 23 s old.
   - **Wait** otherwise.
   On continue: concatenate the messages and delete the buffer. This merges rapid-fire WhatsApp messages into one agent turn.
5. **Agent** with Postgres memory.
6. **Evaluación (Code)**: under 250 chars with no `[PAUSA_*]` markers → send direct; 250-500 chars → simple split; 500+ chars or markers → full split.
7. **Frankenstein "Partidor"**: an LLM that only splits text into `{"parte_1".."parte_5"}` JSON. It never rewrites. Links go in their own part. Cut after answering and before a new question, link, topic change or price; never split a price from its context.
8. **Procesamiento final (Code)**: normalizes OpenAI Chat / Responses / Anthropic output shapes, strips fences, and has a regex fallback to the first `{...}` block.
9. **Parteado → Chatwoot POST part 1 → wait → `¿Hay parte N?` → POST part N …**

Humanization is in the prompt (B + H), **not** in the splitter. The v1 splitter also rewrote text, which made the tone inconsistent.

---

## 8. Build process (the "HowToUse" meta-prompt)

When asked to build an agent for someone:

1. **Discovery**: 5-7 questions per message, in 5 blocks:
   - Identity & objective: name, specific role, tone, measurable one-line goal.
   - Product/service: offer, prices, payment methods, differentiators.
   - Customers & objections: ideal customer, 3-5 success cases with numbers, frequent objections and questions.
   - Limits, escalation & post-sale: does / doesn't, redirect targets, when to escalate, what happens after the action.
   - Operations & tools: hours, key dates, links, support contacts, which data changes (→ dynamic tool) and which is fixed (→ static tool).
2. **Architecture summary** before building: project, objective, orchestrator model, tools (dynamic/static/action), memory table, limits → redirects, docs list.
3. **Build node by node**: at most 2 nodes per message, `snake_case` names, and for each node: NODE / TYPE / CONFIG / full prompt in a code block / CONNECTION / ✅ verification ("Execute Step → expected output, or paste the error"). Don't advance until the current node works ("Pasta de Dientes": one surgical improvement at a time).
4. **Test**: 10+ conversations, objections, escalation, limits; verify no markdown, no banned phrases, and the repetition limits.
5. **Weekly after deploy**: read 20-30 transcripts, pick ONE pattern, make one surgical fix, and measure it.

Deviations we've made in practice: the real-estate build shipped importable n8n JSON plus a build guide instead of manual-only instructions (the meta-prompt says "never exported JSON"). That works if you note that **credentials and cross-workflow IDs must be re-linked after import** and import sub-workflows first.

For structured agents, also define an **input/output contract** (example JSON in and out) before writing the prompt, and a **testing checklist** that includes adversarial cases: a budget that's too low, a misspelled location, an unknown type, a record with a missing URL, a tampered fake URL, and a slow API.

---

## 9. Things NOT to copy from the reference material

The Diana brain converts well, but some tactics are deceptive and shouldn't be reproduced without a deliberate decision by the owner:

- **Denying being an AI** ("NEVER confirm you're a bot"; scripted deflections). Several jurisdictions require bots to disclose that they're bots in sales and political contexts, for example California's B.O.T. Act. Default for new agents: don't claim to be human, and answer honestly if asked directly.
- **Simulated scarcity**: `check_quota` computes "~N spots left" from a date heuristic, not from real enrollment data, then feeds it to the agent as an urgency frame. Principle 3 ("verifiable info > creativity") should apply to urgency too: only cite real numbers.
- **Fabricated-looking precision** in the benchmark stats (for example "ROI average 7,925% first month") unless it's backed by real data.

The psychology frameworks themselves (labeling, mirroring, outcome framing, anchoring against *real* reference prices, binary CTAs) are fine to use honestly.
