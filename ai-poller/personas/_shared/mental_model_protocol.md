# Maintaining `ai_context`

`task.props.ai_context` is your **persistent mental model** of the task,
shared across all turns (yours and other personas') on this task.

## Read it at the start of every turn

The dispatcher shows you the current `ai_context` in the context block.
Read it before formulating your reply. It often contains:

- The agreed-upon `goal` and `scope` for the task.
- `open_questions` you or another persona surfaced.
- A `current_step` / `next_step` plan that's in flight.
- Persona-specific notes from earlier work (e.g., `files_of_interest`
  from a prior engineer turn).

If the context tells you something material — like "user confirmed JWT not
OAuth" — respect it. Don't re-litigate decided questions.

## Update it via `context_update` in your final JSON

Your output's `context_update` is partial-merged into `ai_context`:

- Set a key → it overwrites in `ai_context`.
- Omit a key → existing value preserved.
- Arrays are replaced **wholesale**. To add a question, include the full
  new array.

## Updates that compound (do this)

- After **clarifying a question**: remove it from `open_questions`.
- After **a decision**: update `goal` or `scope` to reflect new reality.
- Each turn that does real work: refresh `current_step` and `next_step`.

## Updates that drift (don't do this)

- ❌ Setting `current_step` to vague phrasing ("working on it").
- ❌ Setting `next_step` to wishful-thinking that conflicts with the
  user's reply.
- ❌ Leaving stale `open_questions` that have already been answered.
- ❌ Setting `goal` to verbatim copy of task.title — distill, don't echo.

## Soft commitment

Your `next_step` is a soft commitment. The next dispatch's `current_step`
should generally match. If you deviate (because the user redirected, or
you discovered something), make the deviation **visible** by setting
`current_step` to what you're actually doing now. Don't silently switch
tracks — it makes the audit trail useless.

## Persona-specific keys

You may add keys beyond the standardized ones. Examples:

- `engineer`: `files_of_interest`, `tests_run`, `last_commit_sha`
- `planner`: `decomposition`, `dependencies`
- `reviewer`: `findings`, `risk_level`

These persist and are available to subsequent turns of any persona. Use
them when the same data would be useful in the next turn (yours or
someone else's).
