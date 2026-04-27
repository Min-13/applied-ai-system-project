from pawpal_system import Task, Pet, Owner
from pawpal_agent import route, retrieve, load_docs, _confidence_label


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------

def test_mark_complete_changes_status():
    task = Task(task_id="t1", title="Morning Walk", category="exercise", duration_min=30, priority=1)
    assert task.completed is False
    task.mark_complete()
    assert task.completed is True


def test_adding_task_increases_pet_task_count():
    pet = Pet(pet_id="p1", name="Buddy", species="dog", age=3)
    task = Task(task_id="t1", title="Feed Buddy", category="feeding", duration_min=5, priority=1)
    assert len(pet.tasks) == 0
    pet.tasks.append(task)
    assert len(pet.tasks) == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_owner(notes=""):
    pet = Pet(pet_id="p1", name="Buddy", species="dog", age=3, notes=notes)
    return Owner(owner_id="o1", name="Alex", available_minutes=120, pets=[pet])


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------

class TestRouting:

    def test_schedule_keyword_routes_to_scheduler(self):
        owner = _make_owner()
        assert route("what tasks are due today?", owner) == "scheduler"

    def test_plan_keyword_routes_to_scheduler(self):
        owner = _make_owner()
        assert route("show me the plan for today", owner) == "scheduler"

    def test_emergency_vomiting_routes_to_urgent_care(self):
        owner = _make_owner()
        assert route("my dog is vomiting blood", owner) == "urgent_care_warning"

    def test_emergency_seizure_routes_to_urgent_care(self):
        owner = _make_owner()
        assert route("Buddy had a seizure", owner) == "urgent_care_warning"

    def test_emergency_poison_routes_to_urgent_care(self):
        owner = _make_owner()
        assert route("I think my cat ate poison", owner) == "urgent_care_warning"

    def test_general_question_routes_to_retriever(self):
        owner = _make_owner()
        assert route("what should I feed my cat?", owner) == "retriever"

    def test_medication_question_routes_to_retriever(self):
        owner = _make_owner()
        assert route("what medication does Bella take?", owner) == "retriever"

    def test_grooming_question_routes_to_retriever(self):
        owner = _make_owner()
        assert route("how often should I brush my dog?", owner) == "retriever"

    def test_emergency_takes_priority_over_schedule(self):
        """A message with both emergency and schedule words should still warn."""
        owner = _make_owner()
        assert route("Buddy collapsed during today's walk", owner) == "urgent_care_warning"


# ---------------------------------------------------------------------------
# Retrieval tests
# ---------------------------------------------------------------------------

class TestRetrieval:

    def test_finds_relevant_chunk_from_pet_notes(self):
        owner = _make_owner(notes="Bella takes Otomax ear drops at 7 PM with food.")
        chunks = load_docs(owner)
        match = retrieve("medication ear drops", chunks)
        assert match is not None
        assert "Otomax" in match["text"] or "ear" in match["text"]

    def test_returns_none_when_no_chunks_match(self):
        result = retrieve("xylophone concert tickets", [])
        assert result is None

    def test_returns_none_for_zero_overlap(self):
        chunks = [{"text": "The sky is blue on a clear day.", "source": "test.txt"}]
        result = retrieve("medication dosage schedule", chunks)
        assert result is None

    def test_pet_notes_included_in_chunks(self):
        owner = _make_owner(notes="Buddy needs insulin twice a day.")
        chunks = load_docs(owner)
        sources = [c["source"] for c in chunks]
        assert any("Buddy" in s for s in sources)

    def test_no_crash_when_owner_has_no_pets(self):
        owner = Owner(owner_id="o1", name="Alex", available_minutes=60, pets=[])
        chunks = load_docs(owner)
        result = retrieve("anything", chunks)
        # Should not raise — result may be None or a file chunk
        assert result is None or isinstance(result, dict)

    def test_higher_overlap_wins(self):
        chunks = [
            {"text": "Feed your dog twice daily with fresh water.", "source": "a.txt"},
            {"text": "Medication should be given at 7 PM with food to Bella.", "source": "b.txt"},
        ]
        match = retrieve("Bella medication food", chunks)
        assert match["source"] == "b.txt"

    def test_confidence_key_present_in_result(self):
        chunks = [{"text": "Feed your dog twice daily with fresh water.", "source": "a.txt"}]
        match = retrieve("feed dog", chunks)
        assert "confidence" in match
        assert 0.0 < match["confidence"] <= 1.0

    def test_full_query_overlap_yields_high_confidence_label(self):
        chunks = [{"text": "medication dosage schedule Bella food", "source": "b.txt"}]
        match = retrieve("medication dosage schedule Bella food", chunks)
        assert _confidence_label(match["confidence"]) == "high"

    def test_single_word_overlap_yields_low_confidence_label(self):
        chunks = [{"text": "The dog went for a walk in the park today.", "source": "c.txt"}]
        match = retrieve("medication", chunks)
        assert match is None or _confidence_label(match["confidence"]) == "low"
