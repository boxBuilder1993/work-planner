# Anti-patterns — do not do these

These are concrete failure modes drawn from real cleanup work on this repo.
Each one has a reason. Follow them regardless of how the task is phrased.

## File naming

❌ **Do not create** `*_IMPLEMENTATION.md`, `*_COMPLETION_REPORT.md`,
`*_GUIDE.md`, `*_TEST_COMPLETE.md`, `PROJECT_COMPLETION_REPORT.md`, or
similar AI-victory-lap files.
**Why:** they obscure what was actually built and don't survive review.
Implementation status belongs in commit messages and PR descriptions.
Real docs go in `docs/`.

❌ **Do not name milestones "Phase 3B.2", "Phase 4A", etc.**
**Why:** AI-generated milestone naming is a tell that the milestone was
fictitious. Use specific, descriptive names ("Add JWT validation
middleware") or no name at all.

## Scope

❌ **Do not expand scope** beyond what the user asked for. If the user
says "add caching to the user lookup," don't also refactor the auth
middleware, don't add a "while I'm here" rename, don't introduce a new
dependency.
**Why:** scope creep makes diffs unreviewable and introduces unrelated
risk. If you see adjacent work that needs doing, *say so in the reply* and
let the user create a separate task.

❌ **Do not declare a feature "complete" if it's not reachable from the
app's entry point.** Code that isn't imported is dead.
**Why:** half-wired features look done in markdown but aren't done in
reality.

## Cross-project contamination

❌ **Do not introduce code from unrelated projects.** This is the
WorkPlanner repo. Anything about "financial profiles", "ESPP", "tax
refund", "temperature conversion", "mutation testing on `time_varying.py`",
etc. is contamination — investigate before adding.
**Why:** this repo has been cleaned of those once. Don't reintroduce them.

❌ **Do not paste large blocks of code from prior conversations or from
other repos.** Read the file you intend to modify first.
**Why:** stale paste loses context (different versions, different style)
and produces subtle bugs.

## Honesty

❌ **Do not claim work is done until you've verified it.** "I added the
function" is fine. "I added the function and the tests pass" requires
that you actually ran the tests.
**Why:** unverified completion is worse than incompleteness — the user
moves on while the code is broken.

❌ **Do not hide uncertainty.** Confident-wrong is the worst failure mode.
If you're unsure, say so in `reply_text` and either ask a clarifying
question or take a more conservative action.

## Memory

❌ **Do not trust `ai_context` over the current code.** Memory entries are
hints from past turns; the code is the source of truth. Before recommending
"function X is in file Y" because `ai_context` says so, verify with a
read/grep.
**Why:** state drifts. Code gets renamed; memories don't auto-update.

## Output

❌ **Do not return more than one JSON object as your final message.**
❌ **Do not wrap the JSON in code fences.**
❌ **Do not include prose before or after the JSON.**
The dispatcher parses your final assistant message as JSON, period. See
`output_format.md` for full rules.
