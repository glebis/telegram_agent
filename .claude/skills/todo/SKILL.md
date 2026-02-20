## /todo - Manage Todos in Obsidian Vault

Manage personal todos stored in Obsidian vault via task_manager.py CLI.

### Usage

- `/todo` — list active todos
- `/todo add <title>` — create new todo
- `/todo done <id>` — mark complete
- `/todo list [status]` — filter by status (inbox/active/completed)

### Steps

**List active todos:**

```bash
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py list --status active --format json
```

Parse JSON output and present to user in readable format with:
- Task ID
- Title
- Status (inbox/active/completed)
- Priority (low/medium/high)
- Due date (if present)
- Tags (if present)

**List all todos by status:**

```bash
# List inbox todos
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py list --status inbox --format json

# List completed todos
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py list --status completed --format json
```

**Create todo:**

```bash
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py create --title "Task title here" --source claude --priority medium
```

Optional parameters:
- `--context "Description text"` - Add task description/context
- `--due "YYYY-MM-DD"` - Set due date
- `--tags tag1 tag2` - Add tags
- `--priority low|medium|high` - Set priority (default: medium)

**Complete todo:**

```bash
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py complete <task-id>
```

Replace `<task-id>` with the task filename (e.g., `2026-02-12-buy-milk`).

**Update task status:**

```bash
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py update <task-id> --status active
```

Possible statuses: `inbox`, `active`, `completed`

### Examples

**Example 1: List active todos**

```bash
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py list --status active --format json
```

Output:
```json
[
  {
    "id": "2026-02-12-review-pr",
    "title": "Review PR #123",
    "status": "active",
    "priority": "high",
    "due": "2026-02-15",
    "tags": ["code", "review"],
    "created": "2026-02-12T10:30:00"
  }
]
```

Present to user:
```
Active Todos (1):

#2026-02-12-review-pr
Title: Review PR #123
Status: active
Priority: high
Due: 2026-02-15
Tags: code, review
Created: 2026-02-12 10:30
```

**Example 2: Create todo with details**

```bash
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py create \
  --title "Review security audit findings" \
  --context "Review P1 security findings from pentest report" \
  --due "2026-02-20" \
  --tags security audit \
  --priority high \
  --source claude
```

**Example 3: Complete a todo**

```bash
/opt/homebrew/bin/python3.11 /Users/server/ai_projects/telegram_agent/scripts/task_manager.py complete 2026-02-12-review-pr
```

### Notes

- Tasks are stored in `~/Research/vault/Tasks/` with subdirectories:
  - `inbox/` - New tasks (default)
  - `active/` - In progress
  - `completed/` - Finished tasks
- Each task is a markdown file with YAML frontmatter
- Task IDs are filenames without `.md` extension
- Task files can be viewed/edited directly in Obsidian
- The task manager is also accessible via Telegram bot with `/todo` command
