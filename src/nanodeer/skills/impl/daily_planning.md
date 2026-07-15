---
name: daily_planning
description: Turn everyday requests into dated, persistent, and reviewable next actions.
disable-model-invocation: true
compatibility: tasks save_memory search_memory
---

# Daily planning workflow

1. Separate durable tasks from conversational suggestions. Add a task only when the user asks to
   remember, schedule, track, or complete an action.
2. Use ISO dates in `due`; if a relative date is unambiguous, resolve it against the current date.
   If it is materially ambiguous, use `wait` for the missing date or timezone.
3. Use `tasks` for actionable items. Use `save_memory` only for stable preferences and facts, not
   for reminders or transient status.
4. List open tasks when reviewing the day, order them by deadline, and propose a short realistic
   sequence without changing task data unless asked.
5. Complete or delete tasks by their stable task id so similarly named items are not confused.
