#!/usr/bin/env python3
"""
Nex Timetrack - Billable time logger for freelancers and agencies.
Copyright 2026 Nex AI (Kevin Blancaflor)
"""
import sys
import os
import json
import argparse
import datetime as dt
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.storage import (
    init_db, start_timer, stop_timer, get_active_timer, cancel_timer,
    save_entry, get_entry, list_entries, update_entry, delete_entry,
    search_entries, save_client, get_client, find_client_by_name,
    list_clients, rename_client, deactivate_client, reactivate_client, is_client_active,
    save_project, get_project, find_project_by_name,
    list_projects, get_summary, get_stats, export_entries,
    get_setting, set_setting, list_settings,
    get_categories, add_category, deactivate_category,
    is_multiuser, has_managers, save_user, get_user, list_users, deactivate_user,
    add_role, remove_role, get_roles,
    add_assignment, remove_assignment, get_assignments, has_assignment,
    get_entry_by_external_id,
)
from lib.permissions import (
    PermissionDenied,
    resolve_user, require_user, require_role,
    check_log_entry, check_view_entries, check_modify_entry,
    check_manage_clients, check_manage_users, check_manage_settings,
)

FOOTER = "[Timetrack by Nex AI | nex-ai.be]"
SEPARATOR = "=" * 60
SUBSEPARATOR = "-" * 60


# --- Helpers ---

def _fmt_duration(minutes):
    if not minutes:
        return "0m"
    h = int(minutes // 60)
    m = int(minutes % 60)
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    if h > 0:
        return f"{h}h"
    return f"{m}m"


def _fmt_date(iso_str):
    if not iso_str:
        return "N/A"
    try:
        return dt.date.fromisoformat(iso_str[:10]).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_str


def _fmt_time(iso_str):
    if not iso_str:
        return ""
    try:
        return dt.datetime.fromisoformat(iso_str).strftime("%H:%M")
    except (ValueError, TypeError):
        return ""


def _fmt_money(amount):
    return f"{get_setting('currency_symbol')}{amount:,.2f}"


def _parse_duration(raw):
    raw = raw.strip().lower()
    if 'h' in raw and 'm' in raw:
        parts = raw.replace('m', '').split('h')
        return float(parts[0]) * 60 + float(parts[1])
    if raw.endswith('h'):
        return float(raw[:-1]) * 60
    if raw.endswith('m'):
        return float(raw[:-1])
    return float(raw) * 60


def _resolve_client(name):
    if not name:
        return None
    clients = find_client_by_name(name)
    if clients:
        return clients[0]['id']
    return None


def _resolve_project(name):
    if not name:
        return None
    projects = find_project_by_name(name)
    if projects:
        return projects[0]['id']
    return None


def _resolve_user_id(args):
    user = getattr(args, 'user', None)
    if not user:
        user = os.environ.get('HERMES_SESSION_USER_ID')
    if is_multiuser() and not user:
        print("Error: --user or HERMES_SESSION_USER_ID required in multi-user mode.")
        sys.exit(1)
    return user


# --- Timer commands (deprecated in multi-user) ---

def cmd_start(args):
    init_db()

    if is_multiuser():
        print("Warning: 'start' is deprecated in multi-user mode. Use 'log' to record time.")
        print(FOOTER)
        return

    client_id = _resolve_client(args.client)
    project_id = _resolve_project(args.project)
    billable = not args.non_billable
    tags = args.tags

    started, existing = start_timer(
        description=args.description,
        project_id=project_id,
        client_id=client_id,
        category=args.category,
        billable=billable,
        tags=tags,
    )

    if existing:
        elapsed = dt.datetime.now() - dt.datetime.fromisoformat(existing['started_at'])
        mins = elapsed.total_seconds() / 60.0
        print(f"Timer already running: {existing['description']} ({_fmt_duration(mins)})")
        print(f"Stop it first: nex-timetrack stop")
    else:
        print(f"Timer started: {args.description}")
        print(f"  Started: {_fmt_time(started)}")
        if args.client:
            print(f"  Client: {args.client}")
        if args.project:
            print(f"  Project: {args.project}")
        print(f"  Category: {args.category}")
        print(f"  Billable: {'yes' if billable else 'no'}")
    print(FOOTER)


def cmd_stop(args):
    init_db()

    if is_multiuser():
        print("Warning: 'stop' is deprecated in multi-user mode. Use 'log' to record time.")
        print(FOOTER)
        return

    result = stop_timer(notes=args.notes)
    if not result:
        print("No active timer.")
        print(FOOTER)
        return

    print(f"Timer stopped (Entry #{result['entry_id']})")
    print(f"  Task: {result['description']}")
    print(f"  Duration: {_fmt_duration(result['duration_minutes'])}")
    print(f"  From: {_fmt_time(result['started_at'])} to {_fmt_time(result['ended_at'])}")
    print(FOOTER)


def cmd_status(args):
    init_db()

    if is_multiuser():
        print("Warning: 'status' is deprecated in multi-user mode. Use 'log' to record time.")
        print(FOOTER)
        return

    timer = get_active_timer()
    if not timer:
        print("No active timer.")
        print(FOOTER)
        return

    print(f"Active timer: {timer['description']}")
    print(f"  Running: {_fmt_duration(timer['elapsed_minutes'])}")
    print(f"  Started: {_fmt_time(timer['started_at'])}")
    print(f"  Category: {timer['category']}")
    print(f"  Billable: {'yes' if timer['billable'] else 'no'}")
    print(FOOTER)


def cmd_cancel(args):
    init_db()

    if is_multiuser():
        print("Warning: 'cancel' is deprecated in multi-user mode.")
        print(FOOTER)
        return

    timer = cancel_timer()
    if not timer:
        print("No active timer.")
    else:
        print(f"Timer cancelled: {timer['description']}")
        print("No entry saved.")
    print(FOOTER)


# --- Entries CRUD ---

def cmd_log(args):
    init_db()
    user_id = _resolve_user_id(args)

    duration = _parse_duration(args.duration)
    client_id = _resolve_client(args.client)
    project_id = _resolve_project(args.project)
    billable = not args.non_billable

    if client_id and not is_client_active(client_id):
        print(f"Error: Client is deactivated. Time logging not allowed.")
        sys.exit(1)

    try:
        check_log_entry(user_id, client_id, project_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    entry_id = save_entry(
        description=args.description,
        duration_minutes=duration,
        project_id=project_id,
        client_id=client_id,
        category=args.category,
        billable=billable,
        tags=args.tags,
        notes=args.notes,
        entry_date=args.date,
        rate=args.rate,
        user_id=user_id,
        external_id=args.external_id,
    )

    print(f"Entry logged (ID: {entry_id})")
    print(f"  Task: {args.description}")
    print(f"  Duration: {_fmt_duration(duration)}")
    if args.client:
        print(f"  Client: {args.client}")
    if args.project:
        print(f"  Project: {args.project}")
    if args.external_id:
        print(f"  External ID: {args.external_id}")
    print(f"  Billable: {'yes' if billable else 'no'}")
    print(FOOTER)


def cmd_show(args):
    init_db()

    entry = get_entry(args.id)
    if not entry:
        print(f"Entry {args.id} not found.")
        print(FOOTER)
        return

    print(f"\n{SEPARATOR}")
    print(f"ENTRY #{entry['id']}: {entry['description']}")
    print(f"{SEPARATOR}\n")

    print(f"Date: {_fmt_date(entry['started_at'])}")
    if entry['started_at'] and entry['ended_at']:
        print(f"Time: {_fmt_time(entry['started_at'])} - {_fmt_time(entry['ended_at'])}")
    print(f"Duration: {_fmt_duration(entry['duration_minutes'])}")
    print(f"Category: {entry['category']}")
    print(f"Billable: {'yes' if entry['billable'] else 'no'}")

    if entry['client_name']:
        print(f"Client: {entry['client_name']}")
    if entry['project_name']:
        print(f"Project: {entry['project_name']}")
    if entry['rate']:
        amount = (entry['duration_minutes'] / 60.0) * entry['rate']
        print(f"Rate: {_fmt_money(entry['rate'])}/h = {_fmt_money(amount)}")
    if entry.get('external_id'):
        print(f"External ID: {entry['external_id']}")
    if entry['tags']:
        print(f"Tags: {entry['tags']}")
    if entry['notes']:
        print(f"Notes: {entry['notes']}")

    print(f"\n{FOOTER}")


def cmd_list(args):
    init_db()
    user_id = _resolve_user_id(args)

    client_id = _resolve_client(args.client) if args.client else None
    project_id = _resolve_project(args.project) if args.project else None
    billable = None
    if args.billable:
        billable = True
    elif args.non_billable:
        billable = False

    scope = check_view_entries(user_id)
    filter_user = user_id if scope == 'own' else None

    entries = list_entries(
        project_id=project_id,
        client_id=client_id,
        category=args.category,
        billable=billable,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit or 50,
        user_id=filter_user,
        external_id=args.external_id if hasattr(args, 'external_id') and args.external_id else None,
    )

    if not entries:
        print("No entries found.")
        print(FOOTER)
        return

    print(f"\n{'ID':<5} {'Date':<12} {'Duration':<10} {'Description':<30} {'Client':<16} {'Bill':<5}")
    print("-" * 78)

    total_mins = 0
    for e in entries:
        desc = e['description'][:29]
        client = (e['client_name'] or "")[:15]
        date = _fmt_date(e['started_at'])
        dur = _fmt_duration(e['duration_minutes'])
        bill = "yes" if e['billable'] else "no"
        total_mins += e['duration_minutes'] or 0
        print(f"{e['id']:<5} {date:<12} {dur:<10} {desc:<30} {client:<16} {bill:<5}")

    print(f"\nTotal: {len(entries)} entries | {_fmt_duration(total_mins)}")
    print(FOOTER)


def cmd_edit(args):
    init_db()
    user_id = _resolve_user_id(args)

    entry = get_entry(args.id)
    if not entry:
        print(f"Entry {args.id} not found.")
        print(FOOTER)
        return

    try:
        check_modify_entry(user_id, entry.get('user_id'))
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Check client active status
    current_client = entry.get('client_id')
    if current_client and not is_client_active(current_client):
        print(f"Error: Client is deactivated. Cannot edit entries.")
        sys.exit(1)

    updates = {}
    if args.description:
        updates['description'] = args.description
    if args.duration:
        updates['duration_minutes'] = _parse_duration(args.duration)
    if args.category:
        updates['category'] = args.category
    if args.notes:
        updates['notes'] = args.notes
    if args.tags:
        updates['tags'] = args.tags
    if args.rate is not None:
        updates['rate'] = args.rate
    if getattr(args, 'external_id', None):
        updates['external_id'] = args.external_id
    if args.billable:
        updates['billable'] = True
    elif args.non_billable:
        updates['billable'] = False
    if args.client:
        cid = _resolve_client(args.client)
        if cid:
            updates['client_id'] = cid
    if args.project:
        pid = _resolve_project(args.project)
        if pid:
            updates['project_id'] = pid

    if not updates:
        print("No updates specified.")
        return

    success = update_entry(args.id, **updates)
    if success:
        print(f"Entry #{args.id} updated.")
        for k, v in updates.items():
            print(f"  {k}: {v}")
    else:
        print(f"Entry {args.id} not found.")
    print(FOOTER)


def cmd_delete(args):
    init_db()
    user_id = _resolve_user_id(args)

    entry = get_entry(args.id)
    if not entry:
        print(f"Entry {args.id} not found.")
        print(FOOTER)
        return

    try:
        check_modify_entry(user_id, entry.get('user_id'))
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    if not args.confirm:
        print(f"Delete entry #{args.id}: {entry['description']} ({_fmt_duration(entry['duration_minutes'])})?")
        print(f"Run again with --confirm to delete.")
        print(FOOTER)
        return

    delete_entry(args.id)
    print(f"Entry #{args.id} deleted.")
    print(FOOTER)


def cmd_search(args):
    init_db()
    user_id = _resolve_user_id(args)

    scope = check_view_entries(user_id)
    filter_user = user_id if scope == 'own' else None

    results = search_entries(args.query, user_id=filter_user)
    if not results:
        print(f"No entries matching '{args.query}'")
        print(FOOTER)
        return

    print(f"\nSearch: '{args.query}' ({len(results)} found)\n")
    for e in results:
        print(f"  [{e['id']}] {e['description']}")
        print(f"       {_fmt_date(e['started_at'])} | {_fmt_duration(e['duration_minutes'])}", end="")
        if e['client_name']:
            print(f" | {e['client_name']}", end="")
        if e.get('external_id'):
            print(f" | {e['external_id']}", end="")
        print()

    print(f"\n{FOOTER}")


# --- Client/Project commands ---

def cmd_client_add(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_clients(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    cid = save_client(
        name=args.name,
        rate=args.rate,
        contact_email=args.email,
        notes=args.notes,
    )

    print(f"Client added (ID: {cid})")
    print(f"  Name: {args.name}")
    if args.rate:
        print(f"  Rate: {_fmt_money(args.rate)}/h")
    if args.email:
        print(f"  Email: {args.email}")
    print(FOOTER)


def cmd_clients(args):
    init_db()

    clients = list_clients()
    if not clients:
        print("No clients.")
        print(FOOTER)
        return

    print(f"\n{'ID':<5} {'Name':<25} {'Active':<8} {'Rate':<12} {'Email':<30}")
    print("-" * 80)

    for c in clients:
        active = "yes" if c.get('active', 1) else "no"
        rate = _fmt_money(c['rate']) + "/h" if c['rate'] else "-"
        email = (c['contact_email'] or "")[:29]
        print(f"{c['id']:<5} {c['name'][:24]:<25} {active:<8} {rate:<12} {email:<30}")

    print(f"\nTotal: {len(clients)} clients")
    print(FOOTER)


def cmd_client_rename(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_clients(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    client_id = _resolve_client(args.client)
    if not client_id:
        print(f"Client '{args.client}' not found.")
        sys.exit(1)

    success = rename_client(client_id, args.new_name)
    if success:
        print(f"Client renamed: {args.client} → {args.new_name}")
    else:
        print(f"Failed to rename client.")
    print(FOOTER)


def cmd_client_deactivate(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_clients(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    client_id = _resolve_client(args.client)
    if not client_id:
        print(f"Client '{args.client}' not found.")
        sys.exit(1)

    if not args.confirm:
        client = get_client(client_id)
        print(f"Deactivate client '{client['name']}'? All projects and time logging will be blocked.")
        print(f"Run again with --confirm to deactivate.")
        print(FOOTER)
        return

    success = deactivate_client(client_id)
    if success:
        print(f"Client deactivated. Projects and time logging blocked.")
    else:
        print(f"Failed to deactivate client.")
    print(FOOTER)


def cmd_client_reactivate(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_clients(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    client_id = _resolve_client(args.client)
    if not client_id:
        print(f"Client '{args.client}' not found.")
        sys.exit(1)

    success = reactivate_client(client_id)
    if success:
        print(f"Client reactivated. Projects and time logging enabled.")
    else:
        print(f"Failed to reactivate client.")
    print(FOOTER)


def cmd_project_add(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_clients(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    client_id = _resolve_client(args.client) if args.client else None

    if client_id and not is_client_active(client_id):
        print(f"Error: Client is deactivated. Cannot add projects.")
        sys.exit(1)

    pid = save_project(
        name=args.name,
        client_id=client_id,
        rate=args.rate,
        budget_hours=args.budget,
        notes=args.notes,
    )

    print(f"Project added (ID: {pid})")
    print(f"  Name: {args.name}")
    if args.client:
        print(f"  Client: {args.client}")
    if args.rate:
        print(f"  Rate: {_fmt_money(args.rate)}/h")
    if args.budget:
        print(f"  Budget: {args.budget}h")
    print(FOOTER)


def cmd_projects(args):
    init_db()

    projects = list_projects(active_only=not args.all)
    if not projects:
        print("No projects.")
        print(FOOTER)
        return

    print(f"\n{'ID':<5} {'Project':<25} {'Client':<20} {'Rate':<12} {'Budget':<8}")
    print("-" * 70)

    for p in projects:
        client = (p['client_name'] or "")[:19]
        rate = _fmt_money(p['rate']) + "/h" if p['rate'] else "-"
        budget = f"{p['budget_hours']}h" if p['budget_hours'] else "-"
        print(f"{p['id']:<5} {p['name'][:24]:<25} {client:<20} {rate:<12} {budget:<8}")

    print(f"\nTotal: {len(projects)} projects")
    print(FOOTER)


# --- Reporting ---

def cmd_summary(args):
    init_db()
    user_id = _resolve_user_id(args)

    client_id = _resolve_client(args.client) if args.client else None
    project_id = _resolve_project(args.project) if args.project else None

    team = getattr(args, 'team', False)

    summary = get_summary(
        client_id=client_id,
        project_id=project_id,
        date_from=args.date_from,
        date_to=args.date_to,
        billable_only=args.billable,
        round_up=args.round_up,
        user_id=user_id,
        team=team,
    )

    round_to = get_setting('round_to_minutes')

    print(f"\n{SEPARATOR}")
    print(f"TIME SUMMARY")
    if args.date_from or args.date_to:
        period = f"{args.date_from or '...'} to {args.date_to or '...'}"
        print(f"Period: {period}")
    print(f"{SEPARATOR}\n")

    print(f"Total entries: {summary['total_entries']}")
    print(f"Total time: {_fmt_duration(summary['total_minutes'])} ({summary['total_hours']}h)")
    print(f"Billable time: {_fmt_duration(summary['billable_minutes'])} ({summary['billable_hours']}h)")
    print(f"Total billable: {_fmt_money(summary['total_amount'])}")

    if args.round_up:
        print(f"  (rounded up to {round_to}min blocks)")

    if summary['by_client']:
        print(f"\nBy Client:")
        for name, data in summary['by_client'].items():
            print(f"  {name:<25} {_fmt_duration(data['minutes']):<10} {_fmt_money(data['amount'])}")

    if summary['by_project']:
        print(f"\nBy Project:")
        for name, data in summary['by_project'].items():
            print(f"  {name:<25} {_fmt_duration(data['minutes']):<10} {_fmt_money(data['amount'])}")

    if summary['by_category']:
        print(f"\nBy Category:")
        for cat, mins in summary['by_category'].items():
            print(f"  {cat:<20} {_fmt_duration(mins)}")

    print(f"\n{FOOTER}")


def cmd_stats(args):
    init_db()
    user_id = _resolve_user_id(args)

    scope = check_view_entries(user_id)

    stats = get_stats(user_id=user_id, scope=scope)

    print(f"\n{SEPARATOR}")
    print(f"TIMETRACK STATISTICS")
    print(f"{SEPARATOR}\n")

    print(f"Total entries: {stats['total_entries']}")
    print(f"Total clients: {stats['total_clients']}")
    print(f"Active projects: {stats['total_projects']}")
    print(f"Total time: {_fmt_duration(stats['total_minutes'])} ({stats['total_hours']}h)")
    print(f"Billable time: {_fmt_duration(stats['billable_minutes'])} ({stats['billable_hours']}h)")
    print(f"Total revenue: {_fmt_money(stats['total_revenue'])}")

    if stats['total_minutes'] > 0:
        ratio = (stats['billable_minutes'] / stats['total_minutes']) * 100
        print(f"Billable ratio: {ratio:.0f}%")

    if stats['by_category']:
        print(f"\nTime by Category:")
        for cat, mins in stats['by_category'].items():
            bar = '#' * max(1, int(mins / 30))
            print(f"  {cat:<16} {bar} {_fmt_duration(mins)}")

    if stats['top_clients']:
        print(f"\nTop Clients:")
        for name, mins in stats['top_clients'].items():
            print(f"  {name:<25} {_fmt_duration(mins)}")

    if stats['by_month']:
        print(f"\nTime per Month:")
        for month, mins in stats['by_month'].items():
            bar = '#' * max(1, int(mins / 60))
            print(f"  {month} {bar} {_fmt_duration(mins)}")

    print(f"\n{FOOTER}")


def cmd_export(args):
    init_db()
    user_id = _resolve_user_id(args)

    client_id = _resolve_client(args.client) if args.client else None
    project_id = _resolve_project(args.project) if args.project else None

    data = export_entries(
        format_type=args.format,
        client_id=client_id,
        project_id=project_id,
        date_from=args.date_from,
        date_to=args.date_to,
        user_id=user_id,
    )

    if not data:
        print("No entries to export.")
        return

    from lib.storage import EXPORT_DIR
    output_file = args.output or f"timetrack_export.{args.format}"
    output_path = EXPORT_DIR / output_file

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(data)

    print(f"Exported to {output_path}")
    print(FOOTER)


# --- Multi-user commands (manager only) ---

def cmd_user_add(args):
    init_db()

    # Bootstrap: if no managers exist, anyone can add users
    if has_managers():
        user_id = _resolve_user_id(args)
        try:
            check_manage_users(user_id)
        except PermissionDenied as e:
            print(f"Error: {e}")
            sys.exit(1)

    save_user(args.user_id, args.name)
    print(f"User added: {args.name} ({args.user_id})")
    print(FOOTER)


def cmd_user_list(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        from lib.permissions import check_view_users
        check_view_users(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(3)

    users = list_users()
    if not users:
        print("No users.")
        print(FOOTER)
        return

    print(f"\n{'User ID':<20} {'Name':<25} {'Active':<8} {'Roles':<30}")
    print("-" * 83)

    for u in users:
        roles = ', '.join(sorted(get_roles(u['user_id'])))
        active = "yes" if u['active'] else "no"
        print(f"{u['user_id']:<20} {u['name'][:24]:<25} {active:<8} {roles:<30}")

    print(f"\nTotal: {len(users)} users")
    print(FOOTER)


def cmd_user_deactivate(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_users(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    target = get_user(args.user_id)
    if not target:
        print(f"User '{args.user_id}' not found.")
        print(FOOTER)
        return

    if not args.confirm:
        print(f"Deactivate user '{target['name']}' ({args.user_id})?")
        print(f"Run again with --confirm to deactivate.")
        print(FOOTER)
        return

    deactivate_user(args.user_id)
    print(f"User '{target['name']}' ({args.user_id}) deactivated.")
    print(FOOTER)


def cmd_role_add(args):
    init_db()

    # Bootstrap: allow self-assigning manager role if no managers exist
    if has_managers():
        user_id = _resolve_user_id(args)
        try:
            check_manage_users(user_id)
        except PermissionDenied as e:
            print(f"Error: {e}")
            sys.exit(1)

    add_role(args.user_id, args.role)
    print(f"Role '{args.role}' added to {args.user_id}")
    print(FOOTER)


def cmd_role_remove(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_users(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    remove_role(args.user_id, args.role)
    print(f"Role '{args.role}' removed from {args.user_id}")
    print(FOOTER)


def cmd_assign(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_users(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    client_id = _resolve_client(args.client)
    if not client_id:
        print(f"Client '{args.client}' not found.")
        sys.exit(1)
    project_id = _resolve_project(args.project) if args.project else None

    add_assignment(args.user_id, client_id, project_id)
    print(f"Assigned {args.user_id} to {args.client}", end="")
    if args.project:
        print(f" / {args.project}", end="")
    print()
    print(FOOTER)


def cmd_unassign(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_users(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    client_id = _resolve_client(args.client)
    project_id = _resolve_project(args.project) if args.project else None

    remove_assignment(args.user_id, client_id, project_id)
    print(f"Unassigned {args.user_id} from {args.client}", end="")
    if args.project:
        print(f" / {args.project}", end="")
    print()
    print(FOOTER)


def cmd_assignments(args):
    init_db()

    target_user = getattr(args, 'user_id', None)
    assignments = get_assignments(user_id=target_user)

    if not assignments:
        print("No assignments.")
        print(FOOTER)
        return

    print(f"\n{'User':<20} {'Client':<20} {'Project':<25}")
    print("-" * 65)

    for a in assignments:
        user = a.get('user_name', a['user_id'])
        client = (a.get('client_name') or "")[:19]
        project = (a.get('project_name') or "* (all)")[:24]
        print(f"{user:<20} {client:<20} {project:<25}")

    print(f"\nTotal: {len(assignments)} assignments")
    print(FOOTER)


# --- Settings commands (manager only) ---

def cmd_setting_get(args):
    init_db()
    value = get_setting(args.key)
    if value is not None:
        print(f"{args.key} = {value}")
    else:
        print(f"Setting '{args.key}' not found.")
    print(FOOTER)


def cmd_setting_set(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_settings(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    set_setting(args.key, args.value)
    print(f"Setting '{args.key}' updated to '{args.value}'")
    print(FOOTER)


def cmd_settings(args):
    init_db()

    settings = list_settings()
    print(f"\n{'Key':<20} {'Value':<20} {'Updated':<20}")
    print("-" * 60)

    for s in settings:
        print(f"{s['key']:<20} {s['value']:<20} {s['updated_at'] or '-':<20}")

    print(FOOTER)


def cmd_category_add(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_settings(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    add_category(args.name)
    print(f"Category '{args.name}' added.")
    print(FOOTER)


def cmd_category_remove(args):
    init_db()
    user_id = _resolve_user_id(args)

    try:
        check_manage_settings(user_id)
    except PermissionDenied as e:
        print(f"Error: {e}")
        sys.exit(1)

    deactivate_category(args.name)
    print(f"Category '{args.name}' deactivated.")
    print(FOOTER)


def cmd_categories(args):
    init_db()

    cats = get_categories()
    print("\nCategories:")
    for c in cats:
        print(f"  - {c}")
    print(f"\nTotal: {len(cats)}")
    print(FOOTER)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Nex Timetrack - Billable time logger.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Common user arg helper
    def add_user_arg(p):
        p.add_argument('--user', help='User ID (or set HERMES_SESSION_USER_ID)')

    # START (deprecated in multi-user)
    p = subparsers.add_parser('start', help='Start a timer (deprecated in multi-user)')
    p.add_argument('description', help='What you are working on')
    p.add_argument('--client', help='Client name')
    p.add_argument('--project', help='Project name')
    p.add_argument('--category', default='other', help='Activity category')
    p.add_argument('--tags', help='Comma-separated tags')
    p.add_argument('--non-billable', action='store_true', help='Mark as non-billable')
    add_user_arg(p)
    p.set_defaults(func=cmd_start)

    # STOP (deprecated in multi-user)
    p = subparsers.add_parser('stop', help='Stop the active timer (deprecated in multi-user)')
    p.add_argument('--notes', help='Notes about the work done')
    add_user_arg(p)
    p.set_defaults(func=cmd_stop)

    # STATUS (deprecated in multi-user)
    p = subparsers.add_parser('status', help='Show active timer (deprecated in multi-user)')
    add_user_arg(p)
    p.set_defaults(func=cmd_status)

    # CANCEL (deprecated in multi-user)
    p = subparsers.add_parser('cancel', help='Cancel active timer (deprecated in multi-user)')
    add_user_arg(p)
    p.set_defaults(func=cmd_cancel)

    # LOG
    p = subparsers.add_parser('log', help='Log time manually')
    p.add_argument('description', help='What you worked on')
    p.add_argument('duration', help='Duration (e.g., 2h, 90m, 1h30m)')
    p.add_argument('--client', help='Client name (required in multi-user)')
    p.add_argument('--project', help='Project name (required in multi-user)')
    p.add_argument('--category', default='other', help='Activity category')
    p.add_argument('--tags', help='Comma-separated tags')
    p.add_argument('--notes', help='Additional notes')
    p.add_argument('--date', help='Date (YYYY-MM-DD, default: today)')
    p.add_argument('--rate', type=float, help='Override hourly rate')
    p.add_argument('--non-billable', action='store_true', help='Mark as non-billable')
    p.add_argument('--external-id', help='External reference (JIRA ticket, etc.)')
    add_user_arg(p)
    p.set_defaults(func=cmd_log)

    # SHOW
    p = subparsers.add_parser('show', help='Show entry details')
    p.add_argument('id', type=int, help='Entry ID')
    add_user_arg(p)
    p.set_defaults(func=cmd_show)

    # LIST
    p = subparsers.add_parser('list', help='List time entries')
    p.add_argument('--client', help='Filter by client')
    p.add_argument('--project', help='Filter by project')
    p.add_argument('--category', help='Filter by category')
    p.add_argument('--billable', action='store_true', help='Only billable')
    p.add_argument('--non-billable', action='store_true', help='Only non-billable')
    p.add_argument('--date-from', help='From date (YYYY-MM-DD)')
    p.add_argument('--date-to', help='To date (YYYY-MM-DD)')
    p.add_argument('--external-id', help='Filter by external ID')
    p.add_argument('--limit', type=int, default=50, help='Max results')
    add_user_arg(p)
    p.set_defaults(func=cmd_list)

    # EDIT
    p = subparsers.add_parser('edit', help='Edit an entry')
    p.add_argument('id', type=int, help='Entry ID')
    p.add_argument('--description', help='New description')
    p.add_argument('--duration', help='New duration')
    p.add_argument('--category', help='New category')
    p.add_argument('--client', help='New client')
    p.add_argument('--project', help='New project')
    p.add_argument('--notes', help='New notes')
    p.add_argument('--tags', help='New tags')
    p.add_argument('--rate', type=float, help='New rate')
    p.add_argument('--external-id', help='New external ID')
    p.add_argument('--billable', action='store_true', help='Mark billable')
    p.add_argument('--non-billable', action='store_true', help='Mark non-billable')
    add_user_arg(p)
    p.set_defaults(func=cmd_edit)

    # DELETE
    p = subparsers.add_parser('delete', help='Delete an entry')
    p.add_argument('id', type=int, help='Entry ID')
    p.add_argument('--confirm', action='store_true', help='Confirm deletion')
    add_user_arg(p)
    p.set_defaults(func=cmd_delete)

    # SEARCH
    p = subparsers.add_parser('search', help='Search entries')
    p.add_argument('query', help='Search query')
    add_user_arg(p)
    p.set_defaults(func=cmd_search)

    # CLIENT ADD
    p = subparsers.add_parser('client-add', help='Add a client (manager only)')
    p.add_argument('name', help='Client name')
    p.add_argument('--rate', type=float, help='Default hourly rate')
    p.add_argument('--email', help='Contact email')
    p.add_argument('--notes', help='Notes')
    add_user_arg(p)
    p.set_defaults(func=cmd_client_add)

    # CLIENTS
    p = subparsers.add_parser('clients', help='List clients')
    p.set_defaults(func=cmd_clients)

    # CLIENT RENAME
    p = subparsers.add_parser('client-rename', help='Rename a client (manager only)')
    p.add_argument('client', help='Current client name')
    p.add_argument('new_name', help='New client name')
    add_user_arg(p)
    p.set_defaults(func=cmd_client_rename)

    # CLIENT DEACTIVATE
    p = subparsers.add_parser('client-deactivate', help='Deactivate a client (manager only)')
    p.add_argument('client', help='Client name')
    p.add_argument('--confirm', action='store_true', help='Confirm deactivation')
    add_user_arg(p)
    p.set_defaults(func=cmd_client_deactivate)

    # CLIENT REACTIVATE
    p = subparsers.add_parser('client-reactivate', help='Reactivate a deactivated client (manager only)')
    p.add_argument('client', help='Client name')
    add_user_arg(p)
    p.set_defaults(func=cmd_client_reactivate)

    # PROJECT ADD
    p = subparsers.add_parser('project-add', help='Add a project (manager only)')
    p.add_argument('name', help='Project name')
    p.add_argument('--client', help='Client name')
    p.add_argument('--rate', type=float, help='Project hourly rate')
    p.add_argument('--budget', type=float, help='Budget in hours')
    p.add_argument('--notes', help='Notes')
    add_user_arg(p)
    p.set_defaults(func=cmd_project_add)

    # PROJECTS
    p = subparsers.add_parser('projects', help='List projects')
    p.add_argument('--all', action='store_true', help='Include inactive projects')
    p.set_defaults(func=cmd_projects)

    # SUMMARY
    p = subparsers.add_parser('summary', help='Billing summary')
    p.add_argument('--client', help='Filter by client')
    p.add_argument('--project', help='Filter by project')
    p.add_argument('--date-from', help='From date (YYYY-MM-DD)')
    p.add_argument('--date-to', help='To date (YYYY-MM-DD)')
    p.add_argument('--billable', action='store_true', help='Only billable entries')
    p.add_argument('--round-up', action='store_true', help='Round to configured minutes')
    p.add_argument('--team', action='store_true', help='Show team-wide summary')
    add_user_arg(p)
    p.set_defaults(func=cmd_summary)

    # STATS
    p = subparsers.add_parser('stats', help='Show statistics')
    add_user_arg(p)
    p.set_defaults(func=cmd_stats)

    # EXPORT
    p = subparsers.add_parser('export', help='Export entries')
    p.add_argument('format', choices=['json', 'csv'], help='Export format')
    p.add_argument('--client', help='Filter by client')
    p.add_argument('--project', help='Filter by project')
    p.add_argument('--date-from', help='From date')
    p.add_argument('--date-to', help='To date')
    p.add_argument('--output', help='Output filename')
    add_user_arg(p)
    p.set_defaults(func=cmd_export)

    # --- Multi-user commands ---

    # USER ADD
    p = subparsers.add_parser('user-add', help='Register a user')
    p.add_argument('user_id', help='User ID (e.g., Mattermost ID)')
    p.add_argument('--name', required=True, help='Display name')
    add_user_arg(p)
    p.set_defaults(func=cmd_user_add)

    # USER LIST
    p = subparsers.add_parser('user-list', help='List users and roles (manager/timekeeper only)')
    add_user_arg(p)
    p.set_defaults(func=cmd_user_list)

    # USER DEACTIVATE
    p = subparsers.add_parser('user-deactivate', help='Deactivate a user (manager only)')
    p.add_argument('user_id', help='User ID to deactivate')
    p.add_argument('--confirm', action='store_true', help='Confirm deactivation')
    add_user_arg(p)
    p.set_defaults(func=cmd_user_deactivate)

    # ROLE ADD
    p = subparsers.add_parser('role-add', help='Assign a role to a user (manager only)')
    p.add_argument('user_id', help='User ID')
    p.add_argument('role', choices=['manager', 'timekeeper', 'collaborator'], help='Role')
    add_user_arg(p)
    p.set_defaults(func=cmd_role_add)

    # ROLE REMOVE
    p = subparsers.add_parser('role-remove', help='Remove a role from a user (manager only)')
    p.add_argument('user_id', help='User ID')
    p.add_argument('role', choices=['manager', 'timekeeper', 'collaborator'], help='Role')
    add_user_arg(p)
    p.set_defaults(func=cmd_role_remove)

    # ASSIGN
    p = subparsers.add_parser('assign', help='Assign user to client/project (manager only)')
    p.add_argument('user_id', help='User ID')
    p.add_argument('--client', required=True, help='Client name')
    p.add_argument('--project', help='Project name (omit for all projects)')
    add_user_arg(p)
    p.set_defaults(func=cmd_assign)

    # UNASSIGN
    p = subparsers.add_parser('unassign', help='Remove user assignment (manager only)')
    p.add_argument('user_id', help='User ID')
    p.add_argument('--client', required=True, help='Client name')
    p.add_argument('--project', help='Project name')
    add_user_arg(p)
    p.set_defaults(func=cmd_unassign)

    # ASSIGNMENTS
    p = subparsers.add_parser('assignments', help='List assignments')
    p.add_argument('user_id', nargs='?', help='User ID (omit for all)')
    p.set_defaults(func=cmd_assignments)

    # SETTING GET
    p = subparsers.add_parser('setting-get', help='Get a setting value')
    p.add_argument('key', help='Setting key')
    p.set_defaults(func=cmd_setting_get)

    # SETTING SET
    p = subparsers.add_parser('setting-set', help='Set a setting value (manager only)')
    p.add_argument('key', help='Setting key')
    p.add_argument('value', help='Setting value')
    add_user_arg(p)
    p.set_defaults(func=cmd_setting_set)

    # SETTINGS
    p = subparsers.add_parser('settings', help='List all settings')
    p.set_defaults(func=cmd_settings)

    # CATEGORY ADD
    p = subparsers.add_parser('category-add', help='Add a category (manager only)')
    p.add_argument('name', help='Category name')
    add_user_arg(p)
    p.set_defaults(func=cmd_category_add)

    # CATEGORY REMOVE
    p = subparsers.add_parser('category-remove', help='Deactivate a category (manager only)')
    p.add_argument('name', help='Category name')
    add_user_arg(p)
    p.set_defaults(func=cmd_category_remove)

    # CATEGORIES
    p = subparsers.add_parser('categories', help='List categories')
    p.set_defaults(func=cmd_categories)

    args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_help()
        return

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except PermissionDenied as e:
        print(f"Permission denied: {e}")
        sys.exit(3)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
