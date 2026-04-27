import uuid
from datetime import time
import streamlit as st
from pawpal_system import Task, Pet, Owner, Scheduler
from pawpal_agent import chat as agent_chat


st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")
st.caption("A pet care planning assistant — manage pets, tasks, and daily schedules.")

st.divider()

# ----------------------------------------------------
# Owner setup (outside tabs — needed by both)
# ----------------------------------------------------
st.subheader("Owner Setup")

owner_name_input = st.text_input("Your name", value="Jordan")
available_minutes_input = st.number_input(
    "Available minutes today",
    min_value=15,
    max_value=720,
    value=120,
    step=15,
)
prefer_short_input = st.checkbox("Prefer short tasks first")
low_energy_input = st.checkbox("Low-energy mode")

if "owner" not in st.session_state:
    if owner_name_input.strip():
        st.session_state.owner = Owner(
            owner_id=str(uuid.uuid4()),
            name=owner_name_input.strip(),
            available_minutes=int(available_minutes_input),
            prefer_short_tasks_first=prefer_short_input,
            low_energy_mode=low_energy_input,
        )

if "owner" in st.session_state and owner_name_input.strip():
    owner = st.session_state.owner
    owner.name = owner_name_input.strip()
    owner.update_preferences(
        available_minutes=int(available_minutes_input),
        prefer_short_tasks_first=prefer_short_input,
        low_energy_mode=low_energy_input,
    )

if "owner" not in st.session_state:
    st.warning("Please enter your name above to get started.")
    st.stop()

owner: Owner = st.session_state.owner
st.success(f"Welcome, **{owner.name}**! You have {len(owner.pets)} pet(s) registered.")

st.divider()

# ----------------------------------------------------
# Tabs
# ----------------------------------------------------
tab1, tab2 = st.tabs(["Pets & Tasks", "AI Chat"])

# ====================================================
# TAB 1 — Pets & Tasks
# ====================================================
with tab1:

    # --------------------------------------------------
    # Add a pet
    # --------------------------------------------------
    st.subheader("Add a Pet")

    with st.form("add_pet_form", clear_on_submit=True):
        pet_name = st.text_input("Pet name", placeholder="e.g. Mochi")
        species = st.selectbox("Species", ["dog", "cat", "other"])
        age = st.number_input("Age (years)", min_value=0, max_value=50, value=1, step=1)
        notes = st.text_area("Notes", placeholder="Health info, behaviour reminders, etc.")
        submitted_pet = st.form_submit_button("Add Pet")

    if submitted_pet:
        if pet_name.strip():
            new_pet = Pet(
                pet_id=str(uuid.uuid4()),
                name=pet_name.strip(),
                species=species,
                age=int(age),
                notes=notes.strip(),
            )
            owner.pets.append(new_pet)
            st.success(f"Added **{new_pet.name}**.")
        else:
            st.error("Pet name cannot be empty.")

    st.divider()

    # --------------------------------------------------
    # Add a task
    # --------------------------------------------------
    st.subheader("Add a Task")

    if not owner.pets:
        st.info("Add at least one pet before creating tasks.")
    else:
        pet_names = [p.name for p in owner.pets]

        with st.form("add_task_form", clear_on_submit=True):
            selected_pet_name = st.selectbox("Select pet", pet_names)
            task_title = st.text_input("Task title", placeholder="e.g. Morning Walk")
            category = st.selectbox(
                "Category",
                ["feeding", "exercise", "medication", "grooming", "enrichment", "general"],
            )
            duration = st.number_input("Duration (minutes)", min_value=1, max_value=480, value=20)
            priority = st.selectbox("Priority (1 = highest, 3 = lowest)", [1, 2, 3], index=1)
            mandatory = st.checkbox("Mandatory task")
            recurrence = st.selectbox("Recurrence", ["none", "daily", "weekly"])
            use_preferred_time = st.checkbox("Set preferred time")
            preferred_time_value = st.time_input("Preferred time", value=time(8, 0))
            submitted_task = st.form_submit_button("Add Task")

        if submitted_task:
            if task_title.strip():
                target_pet = next((p for p in owner.pets if p.name == selected_pet_name), None)
                if target_pet:
                    preferred_time = preferred_time_value.strftime("%H:%M") if use_preferred_time else None
                    new_task = Task(
                        task_id=str(uuid.uuid4()),
                        title=task_title.strip(),
                        category=category,
                        duration_min=int(duration),
                        priority=int(priority),
                        mandatory=mandatory,
                        recurrence=recurrence,
                        preferred_time=preferred_time,
                    )
                    target_pet.tasks.append(new_task)
                    st.success(f"Added **{new_task.title}** to **{target_pet.name}**.")
            else:
                st.error("Task title cannot be empty.")

    st.divider()

    # --------------------------------------------------
    # Display pets and tasks
    # --------------------------------------------------
    st.subheader("Your Pets & Tasks")

    if not owner.pets:
        st.info("No pets registered yet.")
    else:
        _scheduler = Scheduler()

        all_task_items = _scheduler.filter_by(owner, status="all")
        conflicts = _scheduler.detect_conflicts(all_task_items)

        if conflicts:
            st.warning(
                f"⚠️ **{len(conflicts)} scheduling conflict(s) detected** — "
                "two or more tasks are scheduled at overlapping times. "
                "Review the details below and adjust preferred times."
            )
            for c in conflicts:
                st.error(
                    f"**Conflict:** {c['task_a']}  \n"
                    f"overlaps with {c['task_b']}  \n"
                    f"**Overlapping window:** {c['overlap']}"
                )

        for pet in owner.pets:
            with st.expander(f"**{pet.name}** — {pet.species.capitalize()}, age {pet.age}", expanded=True):
                if pet.notes:
                    st.caption(f"Notes: {pet.notes}")

                if not pet.tasks:
                    st.info("No tasks yet for this pet.")
                else:
                    pet_task_items = [(pet.name, t) for t in pet.tasks]
                    sorted_items = _scheduler.sort_by_time(pet_task_items)

                    for _, task in sorted_items:
                        col1, col2 = st.columns([5, 1])

                        with col1:
                            time_badge = f"`{task.preferred_time}`" if task.preferred_time else "`--:--`"
                            mandatory_badge = "🔴 Mandatory" if task.mandatory else "⚪ Optional"
                            recurrence_badge = f"🔁 {task.recurrence}" if task.recurrence != "none" else ""
                            st.markdown(
                                f"{time_badge} **{task.title}** — {task.category} | "
                                f"{task.duration_min} min | P{task.priority} | "
                                f"{mandatory_badge} {recurrence_badge}"
                            )

                        with col2:
                            if not task.completed:
                                if st.button("Complete", key=f"complete_{task.task_id}"):
                                    _scheduler.complete_task(pet, task)
                                    st.rerun()
                            else:
                                st.success("Done")
                                if st.button("Reset", key=f"reset_{task.task_id}"):
                                    task.reset_status()
                                    st.rerun()

    st.divider()

    # --------------------------------------------------
    # Generate schedule
    # --------------------------------------------------
    st.subheader("Generate Schedule")

    pet_filter_options = ["All"] + [p.name for p in owner.pets]
    selected_pet_filter = st.selectbox("Filter by pet", pet_filter_options)
    status_filter = st.selectbox("Filter by status", ["pending", "completed", "all"])
    day_start_input = st.time_input("Schedule start time", value=time(8, 0))

    if st.button("Generate Schedule", type="primary"):
        if not owner.pets or all(len(p.tasks) == 0 for p in owner.pets):
            st.warning("Add at least one pet with tasks before generating a schedule.")
        else:
            scheduler = Scheduler()
            result = scheduler.generate_schedule(
                owner=owner,
                pet_name=selected_pet_filter,
                status=status_filter,
                day_start=day_start_input.strftime("%H:%M"),
            )

            schedule_rows = result["schedule"]

            if not schedule_rows:
                st.info("No tasks matched the current filters.")
            else:
                st.success(
                    f"✅ Schedule generated — **{len(schedule_rows)} task(s)**, "
                    f"**{result['time_used']} min used**, "
                    f"**{result['time_remaining']} min remaining**."
                )

                display_rows = [
                    {
                        "Time": f"{row['start_time']} – {row['end_time']}",
                        "Pet": row["pet"],
                        "Task": row["task"],
                        "Category": row["category"],
                        "Duration": f"{row['duration_min']} min",
                        "Priority": row["priority"],
                        "Mandatory": "Yes" if row["mandatory"] else "No",
                        "Recurrence": row["recurrence"],
                        "Conflict Note": row["conflict"],
                    }
                    for row in schedule_rows
                ]
                st.table(display_rows)

            if result["skipped"]:
                st.warning(f"⏭️ **{len(result['skipped'])} task(s) could not be scheduled** (not enough time remaining):")
                for item in result["skipped"]:
                    st.write(f"- **{item['pet']}** — {item['task']}: {item['reason']}")


# ====================================================
# TAB 2 — AI Chat
# ====================================================
with tab2:
    st.subheader("PawPal+ AI Chat")
    st.caption(
        "Ask about today's schedule, get care advice retrieved from pet notes, "
        "or get urgent-care guidance — no API required."
    )

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "api_history" not in st.session_state:
        st.session_state.api_history = []

    if st.button("Clear chat", key="clear_chat"):
        st.session_state.chat_messages = []
        st.session_state.api_history = []
        st.rerun()

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask PawPal+ anything about your pets…"):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.chat_messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                reply = agent_chat(prompt, owner, st.session_state.api_history)
            st.markdown(reply)

        st.session_state.chat_messages.append({"role": "assistant", "content": reply})
        st.session_state.api_history.append({"role": "user", "content": prompt})
        st.session_state.api_history.append({"role": "assistant", "content": reply})
