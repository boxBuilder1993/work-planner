# AI Poller

Polls the WorkPlanner backend API for `@ai` comments in tasks, processes them via Claude Agent SDK, and posts AI responses back.

## Setup

```bash
cd ai-poller
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

```
WORKPLANNER_API_URL=http://localhost:8080
WORKPLANNER_JWT=<your JWT token>
ANTHROPIC_API_KEY=<your key>
POLL_INTERVAL_SECONDS=5
```

To get your JWT token, sign in to the WorkPlanner web app and copy the `jwt` value from `localStorage`.

## Run

```bash
cd ai-poller
source .venv/bin/activate
python main.py
```

Single cycle (useful for testing):

```bash
python main.py --once
```

## What it can do

The AI agent has these tools available:

| Tool | Description |
|------|-------------|
| `get_task` | Look up a task by ID |
| `get_subtasks` | Get child tasks of a parent |
| `get_parent_chain` | Get ancestor chain root-to-task |
| `get_task_comments` | Get comment thread for a task |
| `create_task` | Create a new task or subtask |
| `update_task` | Update task fields (title, status, priority, etc.) |
| `delete_task` | Delete a task and all descendants |
| `add_comment` | Add a comment to a task |
| `run_command` | Execute a shell command (with optional timeout, background support) |
