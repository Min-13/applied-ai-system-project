"""
PawPal+ Agent — no external LLM API required.

Architecture:
  1. Rule-based router   — keyword matching decides which module handles the query
  2. Keyword retriever   — searches sample_docs/ + pet profile notes for relevant chunks
  3. Template responder  — formats answers from retrieved text or scheduler output
  4. Guardrail layer     — emergency keywords always route to urgent-care warning
"""

import logging
import re
from pathlib import Path
from pawpal_system import Owner, Scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_DOCS_DIR = Path(__file__).parent / "sample_docs"

_SCHEDULE_KEYWORDS = {
    "schedule", "today", "due", "task", "tasks", "plan", "pending",
    "morning", "evening", "routine", "reminder", "what should i do",
    "what do i need", "upcoming", "next",
}

_EMERGENCY_KEYWORDS = {
    "vomit", "vomiting", "blood", "seizure", "seizures", "collapse", "collapsed",
    "breathing", "choking", "choke", "swallowed", "poison", "poisoning",
    "emergency", "urgent", "unconscious", "dying", "pale gums", "not breathing",
    "accident", "injured", "injury", "bite", "sting", "burn", "diarrhea",
    "lethargic", "lethargy", "straining", "cant urinate", "cannot urinate",
}


# ---------------------------------------------------------------------------
# Document loading and retrieval
# ---------------------------------------------------------------------------

def load_docs(owner: Owner) -> list[dict]:
    """Load text chunks from sample_docs/ files and the owner's pet notes."""
    chunks = []

    if _DOCS_DIR.exists():
        for path in sorted(_DOCS_DIR.glob("*.txt")):
            text = path.read_text(encoding="utf-8").strip()
            for para in re.split(r"\n{2,}", text):
                para = para.strip()
                if len(para) > 20:
                    chunks.append({"text": para, "source": path.name})
        logger.info("Loaded %d chunks from %s", len(chunks), _DOCS_DIR)
    else:
        logger.warning("sample_docs/ directory not found — skipping file retrieval")

    for pet in owner.pets:
        if pet.notes:
            chunks.append({
                "text": f"{pet.name} ({pet.species}, age {pet.age}): {pet.notes}",
                "source": f"{pet.name}'s profile notes",
            })

    return chunks


def retrieve(query: str, chunks: list[dict]) -> dict | None:
    """Return the best-matching chunk using word-overlap scoring.

    The returned dict includes a ``confidence`` key in [0.0, 1.0] representing
    matched words / total query words.  Returns None when no word overlaps.
    """
    query_words = set(re.findall(r"\w+", query.lower()))
    best_score = 0
    best_chunk = None

    for chunk in chunks:
        chunk_words = set(re.findall(r"\w+", chunk["text"].lower()))
        score = len(query_words & chunk_words)
        if score > best_score:
            best_score = score
            best_chunk = chunk

    if best_chunk and best_score > 0:
        confidence = round(best_score / max(len(query_words), 1), 2)
        result = {**best_chunk, "confidence": confidence}
        if confidence < 0.3:
            logger.warning(
                "Low-confidence retrieval from '%s' (score=%d, confidence=%.2f) — answer may be off-topic",
                best_chunk["source"], best_score, confidence,
            )
        else:
            logger.info(
                "Retrieved chunk from '%s' (score=%d, confidence=%.2f)",
                best_chunk["source"], best_score, confidence,
            )
        return result

    logger.info("No matching chunk found for query: %s", query)
    return None


# ---------------------------------------------------------------------------
# Module implementations
# ---------------------------------------------------------------------------

def _run_get_schedule(owner: Owner) -> str:
    scheduler = Scheduler()
    result = scheduler.generate_schedule(owner)
    if not result["schedule"]:
        return "No pending tasks found for today."
    lines = [
        f"Today's schedule — {result['time_used']} min used, "
        f"{result['time_remaining']} min remaining:"
    ]
    for row in result["schedule"]:
        note = f"  ⚠ {row['conflict']}" if row["conflict"] != "No conflict" else ""
        lines.append(
            f"• {row['start_time']}–{row['end_time']}  [{row['pet']}] {row['task']}"
            f"  ({row['category']}, {row['duration_min']} min, P{row['priority']}){note}"
        )
    if result["skipped"]:
        lines.append(f"\nSkipped — not enough time ({len(result['skipped'])} task(s)):")
        for s in result["skipped"]:
            lines.append(f"• [{s['pet']}] {s['task']}")
    return "\n".join(lines)


def _urgent_care_warning(query: str) -> str:
    logger.warning("EMERGENCY route triggered for query: %s", query)
    return (
        "🚨 **Urgent Care Alert**\n\n"
        f"Your message mentions a potentially serious situation.\n\n"
        "**This may require immediate veterinary attention.** Please:\n"
        "1. Contact your vet or the nearest emergency animal hospital now.\n"
        "2. Do not wait to see if symptoms resolve on their own.\n"
        "3. Keep your pet calm and avoid giving food or medications.\n"
        "4. Have your pet's medical history ready when you call.\n\n"
        "**Emergency resources:**\n"
        "• ASPCA Animal Poison Control: (888) 426-4435\n"
        "• Pet Poison Helpline: (855) 764-7661\n\n"
        "*PawPal+ is not a substitute for professional veterinary care.*"
    )


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.5:
        return "high"
    if confidence >= 0.3:
        return "medium"
    return "low"


def _retriever_answer(query: str, owner: Owner) -> str:
    chunks = load_docs(owner)
    match = retrieve(query, chunks)
    if match:
        confidence = match.get("confidence", 0.0)
        label = _confidence_label(confidence)
        caveat = (
            "\n\n⚠️ *Low confidence — the retrieved text may not fully answer your question. "
            "Try adding more detail to your pet's profile notes.*"
            if label == "low" else
            "\n\n*Add more notes to your pet's profile for more personalised answers.*"
        )
        return (
            f"**From {match['source']}** *(confidence: {label} — {confidence:.0%})*\n\n"
            f"{match['text']}"
            f"{caveat}"
        )
    return (
        "No relevant information found in the pet care notes.\n\n"
        "Try rephrasing your question, or add notes to your pet's profile "
        "and check the documents in `sample_docs/`."
    )


# ---------------------------------------------------------------------------
# Rule-based router
# ---------------------------------------------------------------------------

def route(question: str, owner: Owner) -> str:
    """
    Decide which module should handle the question.

    Returns one of: 'urgent_care_warning', 'scheduler', 'retriever'
    """
    words = set(re.findall(r"\w+", question.lower()))

    if words & _EMERGENCY_KEYWORDS:
        logger.info("Router → urgent_care_warning  (matched emergency keywords)")
        return "urgent_care_warning"

    if words & _SCHEDULE_KEYWORDS:
        logger.info("Router → scheduler  (matched schedule keywords)")
        return "scheduler"

    logger.info("Router → retriever  (no special keywords matched)")
    return "retriever"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def chat(user_message: str, owner: Owner, history: list[dict]) -> str:
    """Route the user message and return a response. No LLM API required."""
    logger.info("Received message: %s", user_message)
    module = route(user_message, owner)

    if module == "urgent_care_warning":
        return _urgent_care_warning(user_message)
    if module == "scheduler":
        return _run_get_schedule(owner)
    return _retriever_answer(user_message, owner)
