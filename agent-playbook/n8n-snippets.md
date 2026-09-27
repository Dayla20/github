# Reusable n8n Snippets

Patterns lifted from the reference workflows, cleaned up for reuse. All are for n8n Code nodes (JS) unless noted.

## Structured-agent system prompt skeleton

```
=== IDENTITY & SCOPE ===
You are the <Name> Agent, <one-line role> for <system>. Your ONLY job: <job>.
You are NOT the <other agent>. You do not <out-of-scope things>. You do not talk to
the end user directly: your only output is the structured JSON below, consumed by
another system.

=== NON-NEGOTIABLE RULE: NEVER INVENT <THING> ===
Every <item> you return MUST come from a real tool call result and MUST carry the
exact <source field> that call returned. You may never:
- Invent <fields>
- "Complete" a partial result with a plausible-sounding value
- Round, estimate, or paraphrase <source field>
If tools return nothing usable, say so in `gaps`. A missing answer is always better
than a fabricated one.

=== TOOL MAP ===
<tool_a> -> <what>. ALWAYS call FIRST. Does NOT <confusable job>.
<tool_b> -> the ONLY source of <data>. NEVER answer about <data> without it. If it
  returns nothing, try at most ONE labeled relaxation - never relax silently.

=== OUTPUT FORMAT ===
Respond with ONLY a single JSON object, no prose, no markdown, no code fences:
{ ...exact shape..., "gaps": [<string>], "generated_at": <ISO-8601> }
Unavailable field -> null, never a guess.

=== LIMITS ===
<out-of-scope request> -> NOT your job. <what to return instead>.

=== FINAL RULES ===
- Call order / max calls per request
- Never fabricate or silently modify <key fields>
- Output ONLY the JSON object
- If unsure a value came from a tool result, use null
```

The agent node: `promptType: define`, `text: {{ JSON.stringify($json) }}`, system message = the above.

## Parse LLM JSON output with a fail-safe

```js
const raw = $input.first().json.output ?? $input.first().json.text ?? '';
const cleaned = String(raw).replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/i, '').trim();
try {
  const parsed = JSON.parse(cleaned);
  parsed.generated_at = new Date().toISOString();
  return [{ json: parsed }];
} catch (e) {
  return [{ json: {
    /* same top-level shape as success, emptied */
    gaps: ['Agent did not return valid JSON. Raw output logged for debugging.'],
    raw_output: String(raw).slice(0, 2000),
    generated_at: new Date().toISOString()
  } }];
}
```

## Enforce real-source URLs (allow-list)

```js
const ALLOWED = ['zillow.com', 'realtor.com', 'redfin.com' /* ... */];
function ok(url) {
  try {
    const u = new URL(url);
    if (!['http:', 'https:'].includes(u.protocol)) return false;
    return ALLOWED.some(d => u.hostname === d || u.hostname.endsWith('.' + d));
  } catch { return false; }
}
const items = Array.isArray(parsed.candidates) ? parsed.candidates : [];
const kept = items.filter(c => ok(c && c.url));
const gaps = [...(parsed.gaps || [])];
if (items.length > kept.length) gaps.push(`${items.length - kept.length} candidate(s) dropped for missing/invalid source URLs.`);
```

## Haversine distance (miles)

```js
function haversineMiles(lat1, lon1, lat2, lon2) {
  if ([lat1, lon1, lat2, lon2].some(v => v === null || v === undefined || v === '')) return null;
  const R = 3958.8, r = d => d * Math.PI / 180;
  const a = Math.sin(r(lat2 - lat1) / 2) ** 2 +
            Math.cos(r(lat1)) * Math.cos(r(lat2)) * Math.sin(r(lon2 - lon1) / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}
```

## Client-side filtering when the API can't filter

```js
.filter(c => c.price === null || (c.price >= budgetMin && c.price <= budgetMax))
.filter(c => minBeds === 0 || (c.beds !== null && c.beds >= minBeds))
.filter(c => radius === null || c.distance === null || c.distance <= radius)
.slice(0, maxResults)
```

Note the policy: unknown values (null) pass the filter rather than being silently excluded, except when a minimum was requested.

## Tolerant field picker (for scraped data with unstable keys)

```js
function pick(obj, keys) {
  for (const k of keys) if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k];
  return null;
}
// pick(r, ['url', 'final_url'])
```

Also: when a response has records but no mappable fields, push the raw key sample into `gaps` so the mapping can be fixed.

## Async API polling with a deadline (Bright Data snapshot pattern)

```
HTTP POST (trigger) → Code: {snapshot_id, deadline: Date.now() + N}
→ Wait 20s → HTTP GET /progress/{id} → IF status == 'ready'
     yes → HTTP GET /snapshot/{id}?format=json → IF status != 'building' → normalize
                                                     else → back to Wait
     no  → IF Date.now() > deadline → Code: return {candidates: [], gaps: ['timed out']}
                                    else → back to Wait
```

Prefer a synchronous endpoint when one exists: set a 120 s HTTP timeout plus `retryOnFail`, maxTries 3 and waitBetweenTries 2000.

## WhatsApp debounce buffer (Redis)

```
Redis push  list=<sender>  {message, sessionId, date_time}
Wait 1s (Seguridad) → Wait 23s (Espera) → Redis get <sender>
Switch:
  last.sessionId != this.sessionId           → Ignore (a newer execution owns it)
  last.date_time before now - 23s            → Continue: concat all, delete key, call agent
  else (fallback)                            → Wait again
```

## Message-length evaluator (before the splitter)

```js
const out = $input.first().json.output;
const len = out.replace(/\[PAUSA_(NATURAL|TEMA|ESPERA)\]/g, '').length;
const markers = /\[PAUSA_/.test(out);
if (!markers && len < 250) return { texto: out, necesitaDivision: false,
  partes: { parte_1: out.trim(), parte_2: '', parte_3: '' } };
return { texto: out, necesitaDivision: true, tipoProcesamiento: len < 500 && !markers ? 'simple' : 'completo' };
```

## Telegram escalation tool text

```
={{ $fromAI('mensaje', 'Structured: customer name if known, CLEAR reason human attention is needed, BRIEF conversation summary, detected interest level (high/medium/low)', 'string') }}
\n\n☎️ WhatsApp: {{ $json.sessionid }}
\n🔗 https://wa.me/{{ $json.sessionid.replace('+', '') }}
```

## Postgres chat memory

`sessionIdType: customKey`, `sessionKey: {{ $json.sessionid || $('Organizer').item.json.sender || 'unknown_' + Date.now() }}`, `tableName: conversations_<agent>`, `contextWindowLength: 8`.
