# ALGO_DSL_V1: Manager-Generated Workflow DSL

> **Status**: Design proposal — for review. No code has been changed.

---

## The Problem: Hardcoded Owner Responsibilities

In `algo_decompose_v2.py`, an owner's entire lifecycle is encoded as a fixed Python state machine:

```
planning → plan_approved → managing → working → work_approved → proof_submitted
```

The `evaluate()` method is a hard `if/elif` chain that dispatches to six private methods:

```python
if status == "planning":
    return self._plan(ctx)
if status == "plan_approved":
    return self._execute_plan(ctx)
if status == "managing":
    return self._manage(ctx)
if status == "working":
    return self._worker_propose(ctx)  # or _worker_execute
if status == "work_approved":
    return self._worker_execute(ctx)
if status == "awaiting_input":
    return self._handle_awaiting_input(ctx)
```

Every "responsibility" an owner has is baked into the Python class. To add a new step (e.g., `testing`, `review`, `security_scan`) you have to modify the algorithm source code.

**The deeper issue**: the algorithm hard-answers the question *"what should an owner do?"* before the owner has even seen the task. For complex, domain-specific tasks, a generic SDLC workflow may not be the right shape.

---

## The Core Idea: Steps as Data, Not Code

`algo_dsl_v1` inverts this. Instead of the framework defining what an owner does, **the owner AI defines it** — at runtime, for each task.

On its first run, the owner agent is prompted to generate a **workflow spec** — a structured description of the steps it plans to take. This spec is stored in the task's `props`. The polling engine reads the spec and executes one step per cycle, advancing through the owner's self-defined workflow.

```
Cycle 1: Owner AI generates workflow spec → stored in props
Cycle 2: Engine reads spec, runs step[0]
Cycle 3: Engine reads spec, runs step[1]
...
Cycle N: Owner done, submits proof
```

The owner's "different responsibilities" are now **data** that lives in the database, not code compiled into the poller binary.

---

## The Workflow Spec Format (JSON in `props`)

When an owner generates its workflow, it writes a structure like this into `props["workflow"]`:

```json
{
  "steps": [
    {
      "name": "research",
      "description": "Explore the codebase, read relevant files, understand the problem.",
      "prompt": "Explore the repository and understand X. Focus on files Y and Z. Write a brief summary of your findings as a proposal.",
      "tools": ["read", "glob", "grep", "bash", "github"],
      "actions": ["propose_work", "request_clarification"],
      "transitions": [
        { "when": "approved_proposals > 0", "next": "implement" }
      ]
    },
    {
      "name": "implement",
      "description": "Write the code based on the approved research proposal.",
      "prompt": "Implement the changes described in your approved research summary. Create a feature branch, write the code, run tests, open a PR.",
      "tools": ["read", "write", "edit", "bash", "git", "github"],
      "actions": ["submit_proof"],
      "transitions": []
    }
  ]
}
```

`aiStatus` encodes the active step as `"step:<name>"` (e.g., `"step:research"`, `"step:implement"`).

The engine finds the active step, builds a `SpawnPlan` from its `prompt`, `tools`, and `actions`, and auto-generates an `on_complete` callback from the `transitions` list — which writes the next `aiStatus` to the database when the agent finishes.

---

## The Algorithm: Four Owner States

`algo_dsl_v1` has four explicit owner responsibilities:

| `aiStatus` | What happens |
|------------|-------------|
| `owner_plan` | Owner AI generates the workflow spec for this task. Creates subtasks (one at a time) and writes a `workflow` spec into each one. |
| `owner_manage` | Manager AI reviews the currently active subtask. Approves/denies proposals. Once the subtask is done, creates the next one. |
| `step:<name>` | Executor AI runs the current workflow step. Prompt and tools come entirely from the generated DSL spec in `props["workflow"]`. |
| `owner_done` | All subtasks complete. Owner submits proof to its parent. |

The distinction from v2:
- In **v2**, the algorithm defines 6 fixed responsibilities for every task.
- In **dsl_v1**, the owner AI defines N task-specific responsibilities at runtime. The algorithm only defines 4 meta-level responsibilities (generate, manage, execute, complete).

---

## Owner Planning Prompt (the key new concept)

The owner's first-cycle prompt is what makes this work. It should:

1. Explain the task
2. Ask the owner to think about what steps are needed
3. Ask the owner to generate a workflow spec (JSON)
4. Ask the owner to create the **first subtask only** (with the generated spec in its props)

Example shape:
```
You are the owner of task: "{title}"
{description}

Your job in this first step is to:
1. Think carefully about how to break this task down.
2. Generate a workflow specification — a list of named steps with prompts and tools.
3. Create the FIRST subtask only. Write its workflow spec into its props.
   (You will create subsequent subtasks one-at-a-time as each finishes.)

The workflow spec should be a JSON object in this format:
  { "steps": [ { "name": ..., "prompt": ..., "tools": [...], "actions": [...], "transitions": [...] } ] }

Do NOT create all subtasks at once. One at a time.
```

---

## Manager-Generated DSL: The Design Choice

Why have the **manager** generate the workflow spec rather than having the developer write it?

| Approach | Flexibility | Domain knowledge | Reusability |
|----------|-------------|-----------------|-------------|
| Developer hardcodes steps in Python | ✗ Fixed per algorithm | ✗ Generic only | ✓ Reused across all tasks |
| Developer writes YAML/JSON per algorithm | ~ One file per algorithm | ✗ Still generic | ~ Slightly more flexible |
| Manager AI generates spec per task | ✓ Unique to each task | ✓ Sees the task context | ✗ Generated fresh each time |

For recurring, well-understood workflows (standard SDLC), v2's hardcoded approach is fine. For novel, domain-specific, or user-defined tasks — where the "right" steps depend on what the task actually *is* — letting the AI generate the workflow at runtime is more powerful.

`algo_dsl_v1` is explicitly for the second category.

---

## State Persistence in the DB

Every state transition writes to the database automatically. No manual `on_complete` functions needed.

The workflow spec's `transitions` block:
```json
"transitions": [
  { "when": "approved_proposals > 0", "next": "implement" }
]
```

...generates the equivalent of:
```python
def on_complete(ctx, result_text):
    run_count = ctx.task.props.get("runCount", 0) + 1
    if len(find_approved_proposals(ctx)) > 0:
        return PropsUpdate(self_props={"aiStatus": "step:implement", "runCount": run_count})
    return PropsUpdate(self_props={"runCount": run_count})
```

`spawner.py` calls `update_task` as before. The DB always reflects the current step by name.

---

## Python DSL for Developer-Authored Workflows

For cases where a developer *does* want to hardcode a workflow (like v2 does today), the same runtime can be driven by a Python-native DSL — using operator overloading to make the definition readable without YAML:

```python
from workflow_dsl import workflow, status, has

decompose_v2 = (
    workflow("decompose_and_delegate_v2")
    .step("planning",
        when    = status("planning") & ~has("pending_proposals") & ~has("approved_proposals"),
        prompt  = build_planning_prompt,
        tools   = ["workplanner", "algo", "github"],
        actions = ["propose_plan", "request_clarification"],
    )
    .step("plan_execution",
        when        = status("planning") & has("approved_proposals"),
        prompt      = build_plan_execution_prompt,
        tools       = ["workplanner", "algo"],
        actions     = ["mark_as_planned", "mark_as_worker_ready"],
        transitions = [
            has("children")  >> "managing",
            ~has("children") >> "working",
        ],
    )
    # ... more steps
)
```

The `>>` operator builds a transition rule. `&`, `|`, `~` compose predicates. The workflow builder is fluent (chainable `.step()` calls).

This is the pattern used by SQLAlchemy (`User.age >= 18`), Django Q objects, and similar Python ORMs — no custom parser needed, just Python's operator protocol.

Both the AI-generated JSON workflow and the developer-authored Python DSL workflow feed into the **same runtime engine**.

---

## What Gets Built (Implementation Plan)

### Phase 1: DSL Runtime (`workflow_dsl.py`)

A standalone module:
- `Predicate` base class with `__and__`, `__or__`, `__invert__`, `__rshift__` for Python-native composition
- `StatusPredicate`, `HasPredicate` built-in predicates
- `Transition` dataclass: `condition + next_status`
- `StepDef` dataclass: `name, when, guard, prompt, tools, actions, transitions`
- `WorkflowBuilder` with fluent `.step()` method
- `CompiledWorkflow.evaluate(ctx) -> SpawnPlan | None`
  - Iterates steps, tests `when`, tests `guard`, resolves tools, auto-generates `on_complete`
- `parse_workflow_from_props(props) -> CompiledWorkflow` — for AI-generated JSON workflows

### Phase 2: New Algorithm (`algo_dsl_v1.py`)

- `name = "dsl_v1"`
- `initialize()`: sets `aiStatus = "owner_plan"` for new tasks; inherits `workflow` from parent props for subtasks
- `evaluate()` dispatches on four states:
  - `owner_plan` → spawn owner planning agent (generates DSL, creates first subtask)
  - `owner_manage` → spawn manager agent (review active subtask, create next)
  - `step:*` → delegate to `workflow_dsl.parse_workflow_from_props(ctx.task.props)`
  - `owner_done` → spawn completion agent
- Register in `processor.py` (one line)

### Phase 3: Migration of `algo_decompose_v2` (optional, later)

Reduce the existing algorithm to:
```python
class DecomposeAndDelegateV2(WorkflowAlgorithm):
    name = "decompose_and_delegate_v2"
    workflow = decompose_v2  # the Python DSL definition above
```

This is non-breaking — behavior is identical, just expressed declaratively.

---

## Comparison: v2 vs dsl_v1

| | `algo_decompose_v2` | `algo_dsl_v1` |
|--|---------------------|----------------|
| Steps defined by | Developer (hardcoded in Python) | Owner AI (generated at runtime) |
| Steps live in | Source code | Database (`props["workflow"]`) |
| Step count | Fixed (6) | Dynamic (N, per task) |
| Steps visible to AI | No | Yes (it wrote them) |
| Adding a new step | Edit Python source | Change owner prompt |
| Best for | Known, repeatable workflows | Novel, domain-specific tasks |
| DB persistence | Manual `on_complete` functions | Auto-generated from `transitions` |

---

## Open Questions

1. **Workflow validation**: Should the engine validate the AI-generated spec before executing? (e.g., unknown tool names, missing `name` fields)

2. **Step retries**: If a step fails repeatedly, should the engine allow the owner to regenerate its workflow spec?

3. **Recursive workflows**: Can a step's prompt itself instruct the subtask to use `dsl_v1`? (Nested DSL-driven tasks)

4. **Workflow versioning**: If the owner updates its workflow mid-execution (e.g., inserts a new step), how does the engine handle that?

5. **Visibility**: Should the manager's UI show the current step name from the DSL, or just `aiStatus = "step:research"`?

6. **Tool resolution**: How are tool group names (`"github"`, `"git"`) resolved to actual MCP server configs? Central registry or inline config?

7. **Migration**: When (if ever) do we migrate `DecomposeAndDelegateV2` to the Python workflow DSL? Is that a separate ticket?
