# AI Agent Hierarchy Architecture

## Core Principle

**Task = Agent.** Every task has exactly one agent responsible for it. The task tree IS the agent tree. No separate agent registry, no explicit levels, no manual assignment.

---

## Agent Identity

- An agent's identity is the task ID it's responsible for
- An agent's role is emergent:
  - **Worker** (no subtasks) — writes code, runs tests, raises PRs
  - **Manager** (has subtasks) — delegates, reviews proposals, escalates
- An agent can transition: starts as a worker, creates subtasks, becomes a manager
- Agent hierarchy = task hierarchy. Parent task's agent = parent of child task's agent

---

## Infinite Levels

The system supports arbitrary depth. There are no hardcoded levels or role names.

```
Task: "Build login system"          ← Agent (manager, has children)
  ├── "JWT auth"                    ← Agent (worker, leaf)
  ├── "Login UI"                    ← Agent (manager, created subtasks)
  │     ├── "Form component"        ← Agent (worker)
  │     └── "Validation"            ← Agent (worker)
  └── "Session management"          ← Agent (worker)
```

---

## Agent Limits

### Global Agent Cap

- **Default: 20 agents max** (configurable via `max_agents` in config)
- When the cap is reached, new tasks are set to `QUEUED` status
- Queued tasks are picked up automatically when active agents finish and close
- Priority: tasks with higher priority or earlier creation time are dequeued first

### Per-Agent Task Cap

- Max 3 tasks assigned to a single agent
- If a level has more tasks than one agent can handle, additional agents are spawned automatically
- Example: 9 subtasks at a level → 3 agents (3 tasks each)

### Enforcement

```python
def spawn_agent(task):
    active_count = count_active_agents(tasks)
    if active_count >= config.max_agents:
        task.status = "QUEUED"
        return
    # proceed with spawning...
```

---

## Context Scoping

- An agent sees ONLY its own task and its immediate subtasks
- It does NOT see grandchildren or anything deeper
- If it needs deeper info, it communicates through its direct children via comments
- Max 3 tasks assigned to a single agent. If a task is broken into more, multiple agents are spawned at that level automatically

---

## Auto-Spawning

When an agent creates subtasks, new agents are assigned automatically:

1. Agent creates subtask via `create_task` tool
2. Task exists in DB = agent exists
3. Next poll cycle detects the new task and spawns an agent for it
4. The creating agent becomes a manager (gains manager tools, loses worker tools)

---

## Data Model

### TaskEntity (updated fields)

```python
class TaskEntity(BaseModel):
    id: str
    parent_id: str | None          # task hierarchy = agent hierarchy
    title: str
    description: str
    status: str                     # PENDING, IN_PROGRESS, QUEUED, CLOSED
    priority: int                   # 0-5
    due_date: int | None
    task_date: int | None
    planned_time: int | None
    duration: float | None
    level: int | None               # depth in task tree (auto-calculated)
    created_at: int
    updated_at: int
```

### CommentEntity (updated fields)

```python
class CommentEntity(BaseModel):
    id: str
    task_id: str                    # which task this comment belongs to
    parent_comment_id: str | None   # reply-to (enables threaded comments)
    text: str
    comment_type: str               # COMMENT, PROPOSAL
    created_by: str                 # "user", or agent task ID
    proposal_status: str | None     # PENDING, APPROVED, DENIED (only on PROPOSAL type)
    proposal_feedback: str | None   # reason for denial
    created_at: int
    updated_at: int
```

---

## Threaded Comments

Comments support threading via `parent_comment_id`, same pattern as task hierarchy:

- Root comment: `parent_comment_id = None`
- Reply: `parent_comment_id = <comment being replied to>`
- Supports nested replies (reply to a reply)
- Proposals always start a new thread
- Approvals, denials, and follow-ups are replies to the proposal

### Thread Example

```
PROPOSAL (id: c1, parent: None, type: PROPOSAL, status: PENDING)
  "I plan to refactor auth.py to use JWT"
  └── REPLY (id: c2, parent: c1, type: COMMENT, by: L1-agent)
      "Use python-jose instead of pyjwt"
      └── REPLY (id: c3, parent: c2, type: COMMENT, by: L0-agent)
          "Got it, will switch"
```

---

## Proposal Gate

Every agent must propose before acting. No agent acts unilaterally.

### Flow

```
1. Agent reads its task
2. Agent thinks about approach
3. Agent calls `propose` tool → creates PROPOSAL comment with status=PENDING
4. Agent run ENDS (nothing more to do until approved)
5. Parent agent (or user) sees the proposal
6. Parent sets proposal_status = APPROVED or DENIED
7. Next poll cycle: system detects approval → spawns agent again
8. Agent checks proposal status:
   - APPROVED → executes the work
   - DENIED → reads feedback, makes a new proposal
9. When done, agent proposes completion → cycle repeats up the chain
```

### User Interaction

Users see proposals as actionable items in the UI:

```
┌─ 🤖 Agent · PROPOSAL · PENDING ────────┐
│ I plan to create auth/jwt.py using      │
│ python-jose with sign/verify/encrypt.   │
│                                         │
│           [ ✓ Approve ]  [ ✗ Deny ]     │
└─────────────────────────────────────────┘
```

- Approve: sets `proposal_status = "APPROVED"` directly on the comment
- Deny: sets `proposal_status = "DENIED"` + prompts for `proposal_feedback`
- No `@ai approve` commands needed. Pure UI action on the comment.

### Agent Approval

Parent agents approve the same way — by calling `approve_proposal` or `deny_proposal` tools, which set the same fields on the comment.

---

## Escalation

When an agent is blocked, it escalates to its parent:

```
Worker: escalate("Which OAuth provider should we use?")
  → Creates PROPOSAL comment with escalation question
  → Parent agent sees it, either resolves or escalates further
  → Chain continues up until someone (or the user) answers
```

---

## Tools

### External MCP Servers

Worker agents use existing MCP servers for git and GitHub operations instead of custom tools:

| MCP Server | Package | Purpose |
|---|---|---|
| **Git** | `cyanheads/git-mcp-server` | Clone, branch, checkout, commit, push, diff, status, log, worktree (28 tools) |
| **GitHub** | `@modelcontextprotocol/server-github` | Create PRs, read PR comments, check CI status, manage issues |

Worker agents also use the Agent SDK's built-in tools for file operations:

| Built-in Tool | Purpose |
|---|---|
| `Read` | Read file contents |
| `Write` | Create/write files |
| `Edit` | Edit existing files |
| `Bash` | Run shell commands |
| `Glob` | Find files by pattern |
| `Grep` | Search file contents |

### Custom MCP Server: WorkPlanner

The only custom MCP server we build. Handles task and comment operations.

#### Universal Tools (All Agents)

| Tool | Description |
|---|---|
| `get_task` | Get any task by ID |
| `get_subtasks` | Immediate children of a task |
| `get_task_comments` | Comments on a task |
| `create_task` | Create subtask (auto-spawns agent) |
| `update_task` | Update task fields |
| `add_comment` | Add a comment |
| `propose` | Submit a PROPOSAL comment (starts new thread) |
| `reply` | Reply in a comment thread |
| `get_my_proposals` | Check status of submitted proposals |
| `submit_for_review` | Notify parent task's agent that work is done |
| `escalate` | Flag blocker, push question to parent |

#### Manager Only (Has Subtasks)

| Tool | Description |
|---|---|
| `get_pending_proposals` | Unreviewed proposals from subtask agents |
| `approve_proposal` | Approve a proposal |
| `deny_proposal` | Deny with feedback |

### Tool Assignment

```python
def get_tools_for_task(task, all_tasks):
    has_children = any(t.parent_id == task.id for t in all_tasks)

    # All agents get workplanner MCP tools
    mcp_servers = {"workplanner": workplanner_mcp_server}

    # All agents get universal workplanner tools
    allowed_tools = ["mcp__workplanner__*"]

    if has_children:
        # Manager — only workplanner tools, no code/git access
        sdk_tools = []
    else:
        # Worker — add git, github MCP servers + SDK built-in tools
        mcp_servers["git"] = {
            "command": "npx", "args": ["-y", "git-mcp-server"]
        }
        mcp_servers["github"] = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": config.github_token}
        }
        allowed_tools += [
            "mcp__git__*", "mcp__github__*",
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
        ]
        sdk_tools = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

    return mcp_servers, allowed_tools, sdk_tools
```

---

## Auto-Generated Prompts

Prompts are generated based on task context and whether the agent has subtasks:

### Worker Prompt (no subtasks)

```
You are responsible for: "{task.title}"
Description: {task.description}
Your parent task is: "{parent.title}"

You are a worker. You write code, run tests, and raise PRs.
If the task is too large, create subtasks and they will be
handled by other agents automatically.

Before taking any action, submit a proposal and wait for approval.

You have access to:
- WorkPlanner tools for task/comment management
- Git MCP server for version control (clone, branch, commit, push, etc.)
- GitHub MCP server for PRs (create PR, check CI, read reviews)
- Built-in tools for file operations (Read, Write, Edit, Bash, Glob, Grep)
```

### Manager Prompt (has subtasks)

```
You are responsible for: "{task.title}"
Your parent task is: "{parent.title}"

Your subtasks:
- {child.title} (status: {child.status})
- ...

You are a manager. Review proposals from subtask agents,
approve or deny them. When all subtasks are complete,
submit your task for review to your parent.

You can only see your immediate subtasks, not deeper.
You do NOT have access to code, git, or file tools.
Communicate with your subtask agents through comments.
```

---

## Poll Cycle Logic

```python
async def run_cycle(self):
    tasks = download_tasks()
    comments = download_comments()
    active_count = count_active_agents(tasks)

    for task in active_tasks:
        if active_count >= config.max_agents:
            break  # cap reached, remaining tasks stay queued

        has_children = any(t.parent_id == task.id for t in tasks)
        pending = get_pending_proposals_for(task, comments)
        approved = get_approved_proposals_for(task, comments)

        if pending:
            # Waiting for approval — skip
            continue

        if approved:
            # Proposal approved — spawn agent to continue work
            role = "manager" if has_children else "worker"
            spawn_agent(task, role)
            active_count += 1

        if is_new_unprocessed_task(task):
            # Fresh task — spawn worker agent to start
            spawn_agent(task, role="worker")
            active_count += 1

        if has_children and has_unreviewed_child_proposals(task, comments):
            # Subtask agents submitted proposals — spawn manager to review
            spawn_agent(task, role="manager")
            active_count += 1

    # Dequeue waiting tasks if slots available
    queued = [t for t in tasks if t.status == "QUEUED"]
    queued.sort(key=lambda t: (-t.priority, t.created_at))
    for task in queued:
        if active_count >= config.max_agents:
            break
        task.status = "PENDING"
        spawn_agent(task, role="worker")
        active_count += 1
```

---

## Workspace Isolation

Each worker agent gets its own git worktree (managed by git MCP server) to avoid conflicts:

```
/workspaces/
  ├── <task-id-1>/  (branch: ai/<task-id-1>/jwt-auth)
  ├── <task-id-2>/  (branch: ai/<task-id-2>/login-form)
  └── <task-id-3>/  (branch: ai/<task-id-3>/session-mgmt)
```

---

## Agent Lifecycle

```
Task created
  → Agent spawns (worker)
  → Agent proposes plan
  → Parent approves/denies
  → Agent executes (or creates subtasks → becomes manager)
  → Agent proposes completion
  → Parent reviews
  → If approved and all sibling tasks done → parent submits up
  → Chain continues until user approves
  → Task CLOSED → Agent terminates
```

---

## Full Example Flow

```
User creates task: "Build a login system"

Poll cycle 1:
  New task detected → spawn worker agent (1/20 agents)
  Agent proposes: "I'll break this into JWT auth, Login UI, Sessions"
  Agent run ends

User approves the proposal in the UI

Poll cycle 2:
  Approved proposal detected → spawn agent (1/20)
  Agent creates 3 subtasks → becomes manager
  Agent run ends

Poll cycle 3:
  3 new tasks detected → spawn 3 worker agents (4/20 agents)
  Worker-1 proposes: "JWT plan: python-jose, sign/verify..."
  Worker-2 proposes: "Login UI plan: React form component..."
  Worker-3 proposes: "Session plan: Redis store..."
  All 3 agent runs end

Poll cycle 4:
  3 pending proposals detected on children → spawn manager agent (4/20)
  Manager reviews all 3 proposals
  Manager approves Worker-1 and Worker-3
  Manager denies Worker-2: "Use our design system components"
  Manager run ends

Poll cycle 5:
  Worker-1: approved → writes code, raises PR, proposes completion
  Worker-2: denied → reads feedback, makes new proposal
  Worker-3: approved → writes code, raises PR, proposes completion

... cycle continues until all done → flows up to user → user approves
```

---

## Knowledge Base (Vector DB)

Agents document their work in a shared vector database so future agents can learn from past decisions, patterns, and failures.

### Infrastructure

- **ChromaDB hosted on Railway** (~$5-10/month)
- AI poller connects via HTTP client over Railway private network
- When backend migration to Postgres is complete, may migrate to pgvector

### What Agents Document

| Type | Example | When |
|---|---|---|
| `decision` | "Chose python-jose over pyjwt for JWE support" | After making a technical choice |
| `pattern` | "API endpoints use FastAPI + Pydantic, see /api/routes/" | After implementing something |
| `failure` | "Tried SQLite for sessions, too slow under load" | After hitting a dead end |
| `completion` | "Implemented JWT auth: sign/verify/refresh in auth/jwt.py" | After finishing a task |
| `context` | "The auth module depends on the user service at /api/users" | After discovering dependencies |
| `rework` | "Manager requested OAuth instead of plain JWT, reason: security policy" | After receiving rework feedback |

### When Agents Query

- **Task start** — "What do I need to know before working on this area?"
- **Before proposing** — "Has anyone tried this approach before?"
- **When stuck** — "How did other agents handle similar problems?"

### Tools

Added to the WorkPlanner MCP server (available to all agents):

| Tool | Description |
|---|---|
| `document_work` | Record work done, decisions made, patterns discovered |
| `query_knowledge` | Semantic search over past agent documentation |

```python
@tool("document_work")
async def document_work(args):
    """Record work for future agents to reference."""
    collection.add(
        documents=[args["content"]],
        metadatas=[{
            "task_id": args["task_id"],
            "agent_id": current_agent_id,
            "work_type": args["type"],  # decision, pattern, failure, etc.
        }],
        ids=[new_uuid()],
    )

@tool("query_knowledge")
async def query_knowledge(args):
    """Semantic search over past agent work."""
    results = collection.query(
        query_texts=[args["query"]],
        n_results=args.get("limit", 5),
        where=args.get("filter"),  # e.g., {"work_type": "decision"}
    )
    return results
```

### Connection

```python
import chromadb

client = chromadb.HttpClient(
    host=config.vector_db_host,       # Railway private network
    port=config.vector_db_port,
    headers={"Authorization": f"Bearer {config.vector_db_token}"}
)
collection = client.get_or_create_collection("workplanner-knowledge")
```

### Agent Prompt Addition

All agents include in their prompt:

```
You have access to a shared knowledge base via query_knowledge and document_work.
- Before starting work, query the knowledge base for relevant context.
- After making decisions, discovering patterns, or completing work, document it.
- If something fails, document why so future agents don't repeat the mistake.
```

### Future Migration Path

When the backend Postgres migration is complete:
- Option A: Migrate to pgvector (one less service, data co-located with tasks)
- Option B: Keep ChromaDB (simpler embedding API, dedicated vector service)

---

## Configuration

Minimal project config (not agent config):

```json
{
    "repo_url": "git@github.com:user/project.git",
    "base_branch": "main",
    "workspace_root": "/tmp/workplanner-workspaces",
    "test_command": "pytest",
    "build_command": "make build",
    "max_tasks_per_agent": 3,
    "max_agents": 20,
    "github_token": "ghp_...",
    "vector_db": {
        "host": "chromadb.railway.internal",
        "port": 8000,
        "auth_token": "...",
        "collection": "workplanner-knowledge"
    }
}
```

---

## Files to Build/Modify

| File | Purpose |
|---|---|
| `models.py` | Add new fields to CommentEntity (parent_comment_id, comment_type, created_by, proposal_status, proposal_feedback). Add level field to TaskEntity. |
| `hierarchy.py` (new) | Agent spawning, prompt generation, role detection, poll cycle orchestration |
| `task_tools.py` | Universal + manager tools (propose, approve, deny, escalate, etc.) + knowledge base tools (document_work, query_knowledge) |
| `processor.py` | Updated orchestration with hierarchy-aware poll cycle |
| `config.py` (new) | Project configuration (repo, workspace, commands, agent limits, vector DB connection) |
| `knowledge.py` (new) | ChromaDB client wrapper, document/query helpers |
