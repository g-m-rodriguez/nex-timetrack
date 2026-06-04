"""
Nex Timetrack - Permission layer for multi-user mode.
All checks are no-ops in single-user mode (when no users exist in DB).
"""
from lib.storage import is_multiuser, get_user, get_roles, has_assignment


ROLES = ("manager", "timekeeper", "collaborator")


class PermissionDenied(Exception):
    """Raised when a user lacks required permissions."""
    pass


def resolve_user(user_id):
    """Resolve and validate user_id. Returns None in single-user mode."""
    if not is_multiuser():
        return None
    if not user_id:
        return None
    user = get_user(user_id)
    if not user:
        raise PermissionDenied(f"Unknown user: {user_id}")
    if not user['active']:
        raise PermissionDenied(f"User {user_id} is deactivated")
    return user_id


def require_user(user_id):
    """Require a valid user in multi-user mode. Raises if missing."""
    if not is_multiuser():
        return None
    if not user_id:
        raise PermissionDenied(
            "User required in multi-user mode. Use --user or set HERMES_SESSION_USER_ID."
        )
    return resolve_user(user_id)


def require_role(user_id, role):
    """Require a specific role. Raises if user lacks it."""
    if not is_multiuser():
        return True
    user_id = resolve_user(user_id)
    if user_id is None:
        return True
    roles = get_roles(user_id)
    if role not in roles:
        raise PermissionDenied(
            f"User {user_id} requires role '{role}'. Has: {', '.join(roles) or 'none'}"
        )
    return True


def check_log_entry(user_id, client_id=None, project_id=None):
    """Check if user can log time. Validates assignment for collaborator.
    In multi-user, requires client_id, project_id."""
    if not is_multiuser():
        return True
    user_id = require_user(user_id)
    roles = get_roles(user_id)

    if 'manager' in roles:
        return True
    if 'timekeeper' in roles:
        raise PermissionDenied("Timekeepers cannot log time entries.")
    if 'collaborator' in roles:
        if not client_id or not project_id:
            raise PermissionDenied(
                "Collaborators must specify --client and --project when logging time."
            )
        if not has_assignment(user_id, client_id, project_id):
            raise PermissionDenied(
                f"Not assigned to client/project. Use 'assignments' to check."
            )
        return True

    raise PermissionDenied(f"User {user_id} has no valid role for logging time.")


def check_view_entries(user_id):
    """Returns 'all' or 'own' depending on user's view scope."""
    if not is_multiuser():
        return 'all'
    if user_id is None:
        return 'all'
    roles = get_roles(user_id)
    if 'manager' in roles or 'timekeeper' in roles:
        return 'all'
    return 'own'


def check_modify_entry(user_id, entry_user_id):
    """Check if user can modify a specific entry. Manager can modify any."""
    if not is_multiuser():
        return True
    user_id = resolve_user(user_id)
    if user_id is None:
        return True
    roles = get_roles(user_id)
    if 'manager' in roles:
        return True
    if 'timekeeper' in roles:
        raise PermissionDenied("Timekeepers cannot modify entries.")
    if 'collaborator' in roles:
        if entry_user_id and entry_user_id != user_id:
            raise PermissionDenied("Can only modify own entries.")
        return True
    return True


def check_manage_clients(user_id):
    """Manager only — creating/editing clients and projects."""
    return require_role(user_id, 'manager')


def check_manage_users(user_id):
    """Manager only — user management operations."""
    return require_role(user_id, 'manager')


def check_manage_settings(user_id):
    """Manager only — settings and categories."""
    return require_role(user_id, 'manager')


def check_view_users(user_id):
    """Manager or timekeeper can view users. Collaborator cannot."""
    if not is_multiuser():
        return True
    user_id = require_user(user_id)
    roles = get_roles(user_id)
    if 'manager' in roles or 'timekeeper' in roles:
        return True
    raise PermissionDenied("No tienes permisos para listar usuarios.")
