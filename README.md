# PawPal+: Applied AI Pet Care Assistant

### What it does

PawPal+ is a **no-API, locally-running pet care assistant** that adds three AI-style capabilities on top of the original scheduling engine:

1. **RAG (Retrieval-Augmented Generation)** — retrieves the most relevant paragraph from local `.txt` care guides and the owner's own pet profile notes before composing an answer
2. **Agentic routing** — a rule-based agent router decides which module (scheduler, retriever, or emergency guardrail) should handle each user message
3. **Safety guardrail** — emergency keywords (seizure, vomiting, poison, etc.) are intercepted before any other logic and always return an urgent-care warning with real hotline numbers

### Why it matters

Most AI chat demos require API keys, cloud credits, and a working internet connection — all of which fail unpredictably. This project proves the core ideas of RAG and agentic workflows can be implemented reliably, testably, and with zero external dependencies. Everything runs offline from a plain Python environment.

---

## Architecture Overview

```
User message
      │
      ▼
┌─────────────────────────────┐
│       route()               │  Rule-based router
│  emergency? → guardrail     │  Checks emergency keywords first (safety guardrail)
│  schedule? → scheduler      │  Then checks schedule/task keywords
│  else → retriever           │  Falls through to RAG retriever
└─────────────────────────────┘
      │
      ├──► _urgent_care_warning()   Hardcoded safety response + ASPCA/PPH hotlines
      │
      ├──► _run_get_schedule()      Calls Scheduler.generate_schedule() from pawpal_system.py
      │                             Returns time-blocked plan with conflict notes
      │
      └──► _retriever_answer()
                │
                ▼
          load_docs(owner)          Loads paragraphs from sample_docs/*.txt
                +                   + appends each pet's profile notes as chunks
          retrieve(query, chunks)   Word-overlap scoring → best matching chunk
                │
                ▼
          Template response         "From <source>: <text>"
```

**Key files:**

| File | Role |
|------|------|
| `pawpal_system.py` | Core data layer — `Task`, `Pet`, `Owner` dataclasses + `Scheduler` |
| `pawpal_agent.py` | AI layer — router, RAG retriever, module implementations |
| `app.py` | Streamlit UI — owner setup, Pets & Tasks tab, AI Chat tab |
| `sample_docs/` | Local knowledge base (3 `.txt` files) |
| `test/test_pawpal.py` | pytest suite — routing, retrieval, and system behavior |

---

## Setup Instructions

**Prerequisites:** Python 3.10+ (tested with 3.11)

```bash
# 1. Clone the repository
git clone <repo-url>
cd applied-ai-system-project

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies (only two packages)
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py

# 5. Run the tests
python -m pytest test/ -v
```

No API key. No `.env` file. No internet connection required after install.

---

## Sample Interactions

### 1. Schedule query → Scheduler module

**Input:** `"what tasks are due today?"`

**Output:**
```
Today's schedule — 55 min used, 65 min remaining:
• 08:00–08:20  [Bella] Morning Walk  (exercise, 20 min, P1)
• 08:20–08:30  [Bella] Feed Bella  (feeding, 10 min, P1)
• 19:00–19:15  [Bella] Otomax ear drops  (medication, 15 min, P1)
• 19:15–19:25  [Mochi] Feed Mochi  (feeding, 10 min, P2)
```

---

### 2. Care question → RAG Retriever

**Input:** `"what medication does Bella take?"`

**Output:**
```
From Bella's profile notes:

Bella (dog, age 4): Bella is a Golden Retriever seen by Dr. Chen in March 2026.
She takes Otomax ear drops at 7 PM with food. Vaccinations are up to date.
Weight: 28 kg. Monitor for dental issues — next cleaning due in 6 months.

Add more notes to your pet's profile for more personalised answers.
```

---

### 3. Emergency → Guardrail (always fires first)

**Input:** `"my dog is vomiting blood"`

**Output:**
```
🚨 Urgent Care Alert

Your message mentions a potentially serious situation.

This may require immediate veterinary attention. Please:
1. Contact your vet or the nearest emergency animal hospital now.
2. Do not wait to see if symptoms resolve on their own.
3. Keep your pet calm and avoid giving food or medications.
4. Have your pet's medical history ready when you call.

Emergency resources:
• ASPCA Animal Poison Control: (888) 426-4435
• Pet Poison Helpline: (855) 764-7661

PawPal+ is not a substitute for professional veterinary care.
```

---

## Design Decisions

### Why no external LLM API?

Sometimes, external API can introduce a new failure mode: authentication errors, quota exhaustion, model deprecation, or malformed responses. The final architecture eliminates all of these by replacing the LLM with:
- A keyword-based router (deterministic, testable)
- Word-overlap retrieval (no embeddings, no network)
- Hardcoded response templates (reliable, auditable)

This is a deliberate engineering trade-off: less linguistic flexibility in exchange for zero dependencies and 100% reproducibility.

### Why word-overlap retrieval instead of embeddings?

Semantic embeddings (e.g. `sentence-transformers`) would produce better retrieval quality — finding "cardiac issues" as relevant to "heart problems". Word-overlap is simpler and was sufficient for the use case: pet notes and care guides use the same vocabulary as the questions asked about them. Adding an embedding model would require an additional 400 MB+ package download and GPU/CPU inference, which contradicts the "zero dependency" goal.

### Why a rule-based router instead of intent classification?

A trained classifier would generalize better across paraphrases. A rule-based router is transparent — you can read the keyword sets and predict exactly how any message will be routed. For a safety-critical decision (emergency detection), transparency and determinism outweigh flexibility. The emergency guardrail uses a 32-keyword set covering real veterinary emergencies and fires before any other check.

### Why Python logging?

Every routing decision, retrieval result score, and emergency trigger is logged at `INFO` or `WARNING` level. This lets you run the app and watch `stdout` to trace exactly what the agent did for any given message — the same observability pattern used in production AI systems.

---

## Testing Summary

```
python -m pytest test/ -v
# 20 passed in 9.60s
```

**20 out of 20 tests passed.** The AI struggled most when context was missing or the query vocabulary didn't overlap with stored text — confidence scoring now surfaces these cases rather than silently returning a low-relevance answer.

| Test group | Count | What is verified |
|------------|-------|-----------------|
| Original system tests | 2 | `Task.mark_complete()`, pet task list growth |
| `TestRouting` | 9 | Schedule keywords → scheduler; emergency keywords → guardrail; general → retriever; emergency overrides schedule keywords |
| `TestRetrieval` | 9 | Relevant chunk found in pet notes; `None` for empty/zero-overlap; pet notes in chunks; no crash with no pets; higher overlap wins; confidence key present; full-overlap → high label; partial-overlap → low label |

### Confidence scoring

The `retrieve()` function now computes a confidence score: **matched words ÷ total query words**, normalized to [0.0, 1.0]. The score is attached to every returned chunk and shown in the chat response:

| Confidence | Label | UI behaviour |
|-----------|-------|-------------|
| ≥ 0.50 | **high** | Normal answer |
| 0.30–0.49 | **medium** | Normal answer |
| < 0.30 | **low** | ⚠️ caveat shown; `WARNING` logged |

Example chat response header: `From Bella's profile notes (confidence: high — 80%)`

Low-confidence hits also emit a `WARNING`-level log line, so the retriever's uncertainty is visible both to the user and in the terminal:

```
WARNING  pawpal_agent: Low-confidence retrieval from 'pet_care_guide.txt'
         (score=1, confidence=0.14) — answer may be off-topic
```

### What was learned

- Testing the router in isolation caught a priority-ordering bug early: without `if emergency → return` firing before `if schedule → return`, a message like "Buddy collapsed during today's walk" was silently misrouted to the scheduler because "today" and "walk" are schedule keywords.
- The zero-overlap retrieval test initially passed vacuously; an explicit chunk with unrelated vocabulary was required to make it meaningful.
- Adding confidence scoring revealed that single-word queries against long documents reliably produce scores < 0.3 — the threshold that triggers the low-confidence caveat is grounded in actual test observations, not an arbitrary guess.

---

## Reflection

### What this project taught about AI systems

Building PawPal+ AI demonstrated that "AI" in a production system is less about a single powerful model and more about **where intelligence lives in the pipeline**. The most reliable intelligence in this project came from domain knowledge encoded in the emergency keyword set — a list assembled from real veterinary emergency guides — not from any language model. The routing logic, which took 20 lines to write, does something that would take a fine-tuned classifier weeks to reliably replicate.

The repeated API failures also revealed a real engineering constraint that is often glossed over in AI tutorials: **a system that depends on an external API is only as reliable as that API**. Free-tier rate limits, model deprecations, and SDK breaking changes all happened within a single project. The final no-API architecture is more boring but significantly more robust.

### What this project taught about problem-solving

The biggest lesson was knowing when to stop fighting a dependency and change the approach instead. Each API failure triggered a "try a different provider" response before eventually stepping back and asking whether the API was necessary at all. The answer — that RAG and agentic routing are architectural patterns, not features of any specific model — changed the entire design.

The system diagram also clarified something that was implicit before: the three modules (scheduler, retriever, guardrail) are not interchangeable — they have different inputs, different outputs, and different reliability requirements. Drawing the flow made this explicit and informed the test structure: the router tests verify dispatch, the retrieval tests verify the RAG component independently, and the system tests verify end-to-end behavior.

---

## Responsible AI

### Limitations and biases

**Vocabulary bias.** Word-overlap retrieval rewards exact word matches, not meaning. A user asking about "heart problems" will not match a chunk that says "cardiac issues" — the system returns nothing rather than a close answer. Owners who write detailed, specific pet notes get meaningfully better answers than owners who write vague ones, which creates an implicit bias toward more literate or time-rich users.

**Emergency keyword gaps.** The 32-word emergency keyword set was assembled by one developer. It covers obvious crises (seizure, poisoning, collapse) but will miss subtler descriptions: "my dog has been acting strange all day" or "she won't eat and keeps hiding" are real warning signs that bypass the guardrail entirely and get routed to the retriever instead.

**English only.** The regex tokenizer (`\w+`) does not handle accented characters or non-Latin scripts correctly. Non-English speakers using the app in their first language will get degraded or no retrieval.

**No learning.** The system has no memory across sessions. Correcting a wrong answer once does nothing — the same wrong answer will be given again to the next identical question.

**Small knowledge base.** The three sample documents cover dogs and cats. Owners of rabbits, birds, reptiles, or other pets will consistently get low-confidence or no-match responses, with no indication that the knowledge base simply does not cover their situation.

---

### Could this system be misused?

**False medical confidence.** The retriever can return a plausible-sounding answer at "medium" confidence that is actually pulled from a general care guide not specific to the user's pet. An owner might act on it as if it were professional advice. Mitigation: every retriever response ends with a disclaimer, and low-confidence answers include an explicit caveat. The system never fabricates — if nothing matches, it says so.

**Guardrail bypass.** The emergency detection is trivially bypassed by rephrasing: "my dog is not doing great" triggers no keywords. A user who does not know the right vocabulary may miss the guardrail entirely. Mitigation: the emergency keyword set intentionally casts a wide net (32 words) and errs toward false positives — it is better to show an unnecessary urgent-care warning than to miss a real emergency.

**Real hotline numbers.** The urgent-care response includes ASPCA and Pet Poison Helpline numbers. If those numbers change, the hardcoded response becomes harmful misinformation. Mitigation: these are among the most stable phone numbers in veterinary emergency care, but they should be verified before any public deployment.

---

### What surprised me during reliability testing

The most surprising finding was the **routing priority bug** uncovered by `test_emergency_takes_priority_over_schedule`. The message "Buddy collapsed during today's walk" contains both an emergency word ("collapsed") and two schedule words ("today", "walk"). Without an explicit test, this would have silently routed to the scheduler — returning a task list instead of an emergency warning. The bug was invisible during manual testing because no one typed exactly that combination by hand. Only a dedicated test for the overlap case caught it.

The second surprise was how **confident the system appeared** before confidence scoring was added. A query with only one matching word would return a chunk and format it as a definitive answer. Adding the confidence score revealed that many responses I would have called "working" were actually 14–20% matches — technically correct about the source but barely connected to the question.

---

### Collaboration with AI during this project

This project was built with Claude (Anthropic) as a coding assistant throughout development.

**One instance where the AI gave a helpful suggestion:**
After the sixth API provider failed — OpenRouter returned a 404 for the last free model we tried — Claude suggested stepping back entirely and asking whether an external LLM was architecturally necessary at all. It reframed RAG and agentic routing as *patterns* that can be implemented without a model, and proposed the keyword router + word-overlap retriever design. That suggestion changed the entire direction of the project and produced a more reliable, testable, and dependency-free system than any of the API-backed versions.

**One instance where the AI's suggestion was flawed:**
Each time an API failed, Claude's first instinct was to suggest switching to a different provider — Anthropic → Gemini → Groq → OpenRouter — rather than recognizing the pattern earlier. This happened five or six times in a row. Every provider had the same underlying problem: free-tier rate limits, model deprecations, or SDK breaking changes. Claude kept treating each failure as a one-off problem to route around instead of as evidence of a systemic issue with external API dependency. A better suggestion earlier would have been: "free-tier APIs are unreliable by design — consider whether you need one at all." The pattern recognition only happened after the user explicitly asked for a no-API alternative.

### Loom Link
https://www.loom.com/share/4f11e7f270794891b20e3c3c8551766d


