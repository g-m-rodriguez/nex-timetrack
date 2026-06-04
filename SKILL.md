---
name: Nex Timetrack
description: Billable time logger for teams, freelancers and agencies. Multi-user with roles (manager/timekeeper/collaborator), client/project assignments, external ticket references (JIRA/AzureDevOps), configurable settings and categories, rate cascading, billing summaries, full-text search, CSV/JSON export. Python stdlib only, SQLite storage.
version: 2.0.0
metadata:
  author: 
  license: MIT-0
  website: 
  clawdbot:
    keywords:
      - time tracking
      - billable hours
      - timesheet
      - timer
      - stopwatch
      - freelancer
      - agency
      - invoicing
      - billing
      - hourly rate
      - project time
      - client hours
      - multi-user
      - team time tracking
      - JIRA
      - AzureDevOps
      - ticket reference
      - urenregistratie
      - tijdregistratie
      - facturatie
      - freelancer uren
    triggers:
      - track time
      - log hours
      - billable hours
      - time entry
      - how long did I work
      - client billing
      - project hours
      - timesheet
      - invoice summary
      - external ticket
      - JIRA ticket
      - team summary
      - uren bijhouden
      - tijd loggen
      - factureerbare uren
---

# Nex Timetrack

Billable time logger for teams, freelancers and agencies. Multi-user support with role-based permissions. Log time with external ticket references (JIRA, AzureDevOps, GitHub). Manage clients, projects, rates, and settings via DB. Generate billing summaries with configurable rounding.

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
- SQLite (built into Python)

## Setup

```bash
bash setup.sh
```

## User Identification

In multi-user mode, pass `--user <user_id>` or set `HERMES_SESSION_USER_ID` environment variable. The user_id should match the Mattermost user ID.

```bash
# Via flag
nex-timetrack log "Task" 2h --user abc123 --client "Acme" --project "Web" --external-id "JIRA-456"

# Via environment variable (recommended for Mattermost)
export HERMES_SESSION_USER_ID=abc123
nex-timetrack log "Task" 2h --client "Acme" --project "Web" --external-id "JIRA-456"
```

## Commands

### Time Tracking

| Command | What it does |
|---------|-------------|
| `log` | Log time manually (primary command in multi-user) |
| `show` | Show entry details |
| `list` | List entries with filters (client, project, external-id, date range) |
| `edit` | Edit an entry |
| `delete` | Delete an entry |
| `search` | Full-text search entries (includes external IDs) |

### Timer (deprecated in multi-user)

| Command | What it does |
|---------|-------------|
| `start` | Start a live timer (single-user only) |
| `stop` | Stop timer and save entry (single-user only) |
| `status` | Show running timer (single-user only) |
| `cancel` | Cancel timer without saving (single-user only) |

### Client & Project Management (manager only)

| Command | What it does |
|---------|-------------|
| `client-add` | Add a client with rate |
| `client-rename` | Rename a client (manager only) |
| `client-deactivate` | Deactivate client, blocks projects and time logging (manager only, requires --confirm) |
| `client-reactivate` | Reactivate a deactivated client (manager only) |
| `clients` | List all clients |
| `project-add` | Add a project |
| `projects` | List all projects |
| `project-deactivate` | Deactivate project, blocks time logging (manager only, requires --confirm, client must be active) |
| `project-reactivate` | Reactivate a deactivated project (manager only, client must be active) |

### User Management (manager only)

| Command | What it does |
|---------|-------------|
| `user-add` | Register a user |
| `user-list` | List users with roles (manager/timekeeper only) |
| `user-deactivate` | Deactivate a user, requires --confirm (manager only) |
| `role-add` | Assign role to user |
| `role-remove` | Remove role from user |
| `assign` | Assign user to client/project |
| `unassign` | Remove user assignment |
| `assignments` | List assignments |

### Settings (manager only for changes)

| Command | What it does |
|---------|-------------|
| `settings` | List all settings |
| `setting-get` | Get a setting value |
| `setting-set` | Update a setting (manager only) |
| `categories` | List categories |
| `category-add` | Add a category (manager only) |
| `category-remove` | Deactivate a category (manager only) |

### Reporting & Export

| Command | What it does |
|---------|-------------|
| `summary` | Billing summary with totals (`--team` for all users) |
| `stats` | Usage statistics (scoped by role) |
| `export` | Export to JSON or CSV |

## Required Fields in Multi-User

When logging time in multi-user mode, these fields are required for collaborators:
- `--client` — client name
- `--project` — project name
- `--external-id` — external ticket reference (JIRA, AzureDevOps, GitHub issue, etc.)
- `description` — what was done
- `duration` — time spent

## Roles & Permissions

| Action | Manager | Timekeeper | Collaborator |
|--------|---------|------------|--------------|
| Log time | ✅ any client/project | ❌ | ✅ assigned only |
| View entries | ✅ all | ✅ all | ✅ own only |
| Edit/delete entries | ✅ any | ❌ | ✅ own only |
| Summary (team) | ✅ | ✅ | ❌ |
| Summary (own) | ✅ | ✅ | ✅ |
| Search | ✅ all | ✅ all | ✅ own only |
| Export | ✅ all | ✅ all | ✅ own only |
| Add clients/projects | ✅ | ❌ | ❌ |
| Manage users/roles | ✅ | ❌ | ❌ |
| Manage settings/categories | ✅ | ❌ | ❌ |
| View clients/projects | ✅ | ✅ | ✅ |

## Rate Cascade

Rates resolve in this order: entry rate > project rate > client rate > default rate (configurable via `setting-set default_rate`). Set rates at whatever level makes sense for your billing.

## Duration Format

When logging manually, use any of these:
- `2h` = 2 hours
- `90m` = 90 minutes
- `1h30m` = 1 hour 30 minutes
- `1.5` = 1.5 hours

## Configurable Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `default_rate` | 85.00 | Default hourly rate (EUR) |
| `currency` | EUR | Currency code |
| `currency_symbol` | € | Display symbol |
| `round_to_minutes` | 15 | Rounding block for invoicing |

## Tone Guide

This skill responds to natural language through ClawdBot. Example interactions:

**Bootstrap (first user setup):**
> "Set up timetrack for the team"
```bash
nex-timetrack user-add mm-alice --name "Alice Manager"
nex-timetrack role-add mm-alice manager
nex-timetrack user-add mm-bob --name "Bob Dev" --user mm-alice
nex-timetrack role-add mm-bob collaborator --user mm-alice
nex-timetrack client-add "Acme Corp" --rate 90 --user mm-alice
nex-timetrack project-add "Website" --client "Acme Corp" --user mm-alice
nex-timetrack assign mm-bob --client "Acme Corp" --project "Website" --user mm-alice
```

**Logging time with ticket reference:**
> "Log 2 hours of development work on JIRA-1234 for Acme's website"
```bash
nex-timetrack log "API integration" 2h --client "Acme Corp" --project "Website" --external-id "JIRA-1234" --category development --user $HERMES_SESSION_USER_ID
```

**Billing summary for team:**
> "How many hours did the team bill this month?"
```bash
nex-timetrack summary --team --date-from 2026-06-01 --user $HERMES_SESSION_USER_ID
```

**Looking up a ticket:**
> "Show me all time logged against JIRA-1234"
```bash
nex-timetrack list --external-id "JIRA-1234" --user $HERMES_SESSION_USER_ID
```

**Weekly overview:**
> "Show me this week's time entries"
```bash
nex-timetrack list --date-from 2026-06-01 --date-to 2026-06-07 --user $HERMES_SESSION_USER_ID
```

**Export for invoicing:**
> "Export all billable hours for Acme as CSV"
```bash
nex-timetrack export csv --client "Acme Corp" --user $HERMES_SESSION_USER_ID
```

**Adding a client:**
> "Add Acme Corp as a client at 90 per hour"
```bash
nex-timetrack client-add "Acme Corp" --rate 90 --user $HERMES_SESSION_USER_ID
```

**Updating settings:**
> "Change the default rate to 95 euros"
```bash
nex-timetrack setting-set default_rate 95 --user $HERMES_SESSION_USER_ID
```

## Storage

All data stored locally in `~/.nex-timetrack/timetrack.db` (SQLite). No cloud, no telemetry.

Override with: `export NEX_TIMETRACK_DIR=/custom/path`

## Security Rules (MANDATORY for agents)

When executing commands on behalf of a user, follow these rules strictly:

### 1. Never expose commands or terminal output
- Do NOT show the raw command, terminal output, or shell snippets to the user.
- Do NOT reveal how results were obtained (command path, flags, env vars).
- Only show the **result** in natural language or formatted tables.
- ❌ BAD: "I ran `nex-timetrack categories` and got..."
- ✅ GOOD: "These are the available categories: ..."

### 2. Never expose sensitive configuration values
- `HERMES_SESSION_USER_ID` — NEVER show this value in chat. It is a credential.
- `NEX_TIMETRACK_DIR` — do not reveal filesystem paths.
- Database paths, file locations, or internal URLs — do not disclose.
- When showing settings values, only show business-relevant data (rates, currency). Never show internal/system settings.

### 3. Pass credentials only when needed
These commands are **public** (no `--user` required, no credentials passed):
`clients`, `projects`, `categories`, `settings`

All other commands require `--user $HERMES_SESSION_USER_ID` in multi-user mode. Pass it silently via env var — never echo it.

### 4. Error messages
- If a command fails with "Permission denied", report it as: "You don't have permission to do that." Do NOT include the user ID, role details, or the command that was run.
- If a command fails with "User required", report: "You need to be registered as a user first. Ask a manager to add you."

## Error Handling

- **Exit code 1**: General error (missing args, not found)
- **Exit code 3**: Permission denied (wrong role, unassigned client)
- **Exit code 130**: Interrupted (Ctrl+C)

## License

MIT-0 on ClawHub (free for any use).
AGPL-3.0 on GitHub (commercial licenses via info@nex-ai.be).
