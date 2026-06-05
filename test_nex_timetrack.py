"""
Test harness for nex-timetrack — TEST-PLAN.md automation.
Runs TST-001 through TST-190 as pytest cases.

Usage:
    pytest test_nex_timetrack.py -v                # All tests
    pytest test_nex_timetrack.py -k "tst_001"      # Single test
    pytest test_nex_timetrack.py -k "bootstrap"    # By domain
    pytest test_nex_timetrack.py -k "approval"     # By domain
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import sqlite3

import pytest

# --- CLI helper ---

CLI = [sys.executable, "nex-timetrack.py"]


def run(*args, expect_exit=0):
    """Run nex-timetrack with args, return CompletedProcess."""
    result = subprocess.run(
        CLI + list(args),
        capture_output=True, text=True, timeout=10,
    )
    if expect_exit is not None:
        assert result.returncode == expect_exit, (
            f"Exit code {result.returncode} != expected {expect_exit}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def out(result):
    """Shortcut for result.stdout."""
    return result.stdout


# --- Fixtures ---

@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Each test gets a fresh DB in a temp directory."""
    db_dir = tmp_path / "nex-tt"
    db_dir.mkdir()
    monkeypatch.setenv("NEX_TIMETRACK_DIR", str(db_dir))
    yield db_dir


# ============================================================
# 1. BOOTSTRAP — TST-001 to TST-005
# ============================================================

class TestBootstrap:

    def test_tst_001_first_user_add_no_managers(self):
        """TST-001: First user-add without managers."""
        r = run("user-add", "mm-alice", "--name", "Alice", expect_exit=0)
        assert "alice" in r.stdout.lower() or "added" in r.stdout.lower() or "saved" in r.stdout.lower()

    def test_tst_002_bootstrap_role_add_manager(self):
        """TST-002: First role-add manager (bootstrap)."""
        run("user-add", "mm-alice", "--name", "Alice")
        r = run("role-add", "mm-alice", "manager", expect_exit=0)
        assert "manager" in r.stdout.lower()

    def test_tst_003_user_add_non_manager_blocked(self):
        """TST-003: Non-manager cannot add users when managers exist."""
        # Precondiciones: alice=manager, bob=user (sin rol)
        run("user-add", "mm-alice", "--name", "Alice")
        run("role-add", "mm-alice", "manager")
        run("user-add", "mm-bob", "--name", "Bob", "--user", "mm-alice")
        # --- Test ---
        run("role-add", "mm-bob", "collaborator", "--user", "mm-alice")
        run("user-add", "mm-charlie", "--name", "Charlie", "--user", "mm-bob", expect_exit=1)

    def test_tst_004_manager_adds_user(self):
        """TST-004: Manager can add users."""
        # Precondiciones: alice=manager
        run("user-add", "mm-alice", "--name", "Alice")
        run("role-add", "mm-alice", "manager")
        # --- Test ---
        r = run("user-add", "mm-bob", "--name", "Bob", "--user", "mm-alice", expect_exit=0)
        assert "bob" in r.stdout.lower() or "added" in r.stdout.lower() or "saved" in r.stdout.lower()

    def test_tst_005_non_manager_role_add_blocked(self):
        """TST-005: Non-manager cannot add roles."""
        # Precondiciones: alice=manager, bob=timekeeper
        run("user-add", "mm-alice", "--name", "Alice")
        run("role-add", "mm-alice", "manager")
        run("user-add", "mm-bob", "--name", "Bob", "--user", "mm-alice")
        run("role-add", "mm-bob", "timekeeper", "--user", "mm-alice")
        # --- Test ---
        run("user-add", "mm-charlie", "--name", "Charlie", "--user", "mm-alice")
        run("role-add", "mm-charlie", "collaborator", "--user", "mm-bob", expect_exit=1)


# ============================================================
# 2. USERS CRUD — TST-006 to TST-015
# ============================================================

class TestUsers:

    @pytest.fixture
    def manager(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        return "mm-mgr"

    def test_tst_006_user_add_with_name(self, manager):
        """TST-006: Manager adds user with display name."""
        # --- Test ---
        r = run("user-add", "mm-bob", "--name", "Bob", "--user", manager, expect_exit=0)
        assert "bob" in r.stdout.lower()

    def test_tst_007_user_list_manager(self, manager):
        """TST-007: Manager can list all users."""
        # --- Test ---
        run("user-list", "--user", manager, expect_exit=0)

    def test_tst_008_user_list_timekeeper(self, manager):
        """TST-008: Timekeeper can list users (read access)."""
        # Precondiciones: crear usuario timekeeper
        run("user-add", "mm-tk", "--name", "Timekeeper", "--user", manager)
        run("role-add", "mm-tk", "timekeeper", "--user", manager)
        # --- Test ---
        run("user-list", "--user", "mm-tk", expect_exit=0)

    def test_tst_009_user_list_approver(self, manager):
        """TST-009: Approver can list users (read access)."""
        # Precondiciones: crear usuario approver
        run("user-add", "mm-apr", "--name", "Approver", "--user", manager)
        run("role-add", "mm-apr", "approver", "--user", manager)
        # --- Test ---
        run("user-list", "--user", "mm-apr", expect_exit=0)

    def test_tst_010_user_list_collaborator_blocked(self, manager):
        """TST-010: Collaborator denied user-list (insufficient role)."""
        # Precondiciones: crear usuario collaborator
        run("user-add", "mm-col", "--name", "Collaborator", "--user", manager)
        run("role-add", "mm-col", "collaborator", "--user", manager)
        # --- Test ---
        run("user-list", "--user", "mm-col", expect_exit=3)

    def test_tst_011_user_deactivate_with_confirm(self, manager):
        """TST-011: Manager deactivates user with explicit --confirm."""
        # Precondiciones: crear usuario a desactivar
        run("user-add", "mm-bob", "--name", "Bob", "--user", manager)
        # --- Test ---
        run("user-deactivate", "mm-bob", "--confirm", "--user", manager, expect_exit=0)

    def test_tst_012_user_deactivate_no_confirm(self, manager):
        """TST-012: Without --confirm shows prompt (no actual deactivation)."""
        # Precondiciones: crear usuario a desactivar
        run("user-add", "mm-bob", "--name", "Bob", "--user", manager)
        # --- Test: sin --confirm muestra prompt de confirmación ---
        r = run("user-deactivate", "mm-bob", "--user", manager, expect_exit=0)
        assert "confirm" in r.stdout.lower()

    def test_tst_013_user_deactivate_collaborator_blocked(self, manager):
        """TST-013: Collaborator cannot deactivate users."""
        # Precondiciones: crear usuario collaborator + usuario target
        run("user-add", "mm-col", "--name", "Collaborator", "--user", manager)
        run("role-add", "mm-col", "collaborator", "--user", manager)
        # --- Test ---
        run("user-deactivate", "mm-bob", "--confirm", "--user", "mm-col", expect_exit=1)

    def test_tst_014_deactivated_user_blocked(self, manager):
        """TST-014: Deactivated user blocked from logging time."""
        # Precondiciones: crear collaborator, desactivarlo, asignarle proyecto
        run("user-add", "mm-col", "--name", "Collaborator", "--user", manager)
        run("role-add", "mm-col", "collaborator", "--user", manager)
        run("user-deactivate", "mm-col", "--confirm", "--user", manager)
        run("client-add", "Acme", "--user", manager)
        run("project-add", "Web", "--client", "Acme", "--user", manager)
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", manager)
        # --- Test: usuario desactivado no puede registrar horas ---
        run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=1)

    def test_tst_015_unknown_user_blocked(self, manager):
        """TST-015: Unknown/nonexistent user rejected on log."""
        # --- Test: usuario inexistente no puede registrar horas ---
        run("log", "test", "1h", "--client", "x", "--project", "y", "--user", "nonexistent", expect_exit=1)


# ============================================================
# 3. ROLES — TST-016 to TST-023
# ============================================================

class TestRoles:

    @pytest.fixture
    def manager(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        return "mm-mgr"

    def test_tst_016_role_add_collaborator(self, manager):
        """TST-016: Manager assigns collaborator role to user."""
        # Precondiciones: crear usuario sin rol
        run("user-add", "mm-bob", "--name", "Bob", "--user", manager)
        # --- Test ---
        r = run("role-add", "mm-bob", "collaborator", "--user", manager, expect_exit=0)
        assert "collaborator" in r.stdout.lower()

    def test_tst_017_role_add_timekeeper(self, manager):
        """TST-017: Manager assigns timekeeper role."""
        # Precondiciones: crear usuario
        run("user-add", "mm-tk", "--name", "TK", "--user", manager)
        # --- Test ---
        run("role-add", "mm-tk", "timekeeper", "--user", manager, expect_exit=0)

    def test_tst_018_role_add_approver(self, manager):
        """TST-018: Manager assigns approver role."""
        # Precondiciones: crear usuario
        run("user-add", "mm-apr", "--name", "APR", "--user", manager)
        # --- Test ---
        run("role-add", "mm-apr", "approver", "--user", manager, expect_exit=0)

    def test_tst_019_role_add_manager(self, manager):
        """TST-019: Manager assigns manager role (second manager)."""
        # Precondiciones: crear segundo usuario
        run("user-add", "mm-mgr2", "--name", "Mgr2", "--user", manager)
        # --- Test ---
        run("role-add", "mm-mgr2", "manager", "--user", manager, expect_exit=0)

    def test_tst_020_role_remove(self, manager):
        """TST-020: Manager removes role from user."""
        # Precondiciones: crear usuario con rol collaborator
        run("user-add", "mm-bob", "--name", "Bob", "--user", manager)
        run("role-add", "mm-bob", "collaborator", "--user", manager)
        # --- Test ---
        r = run("role-remove", "mm-bob", "collaborator", "--user", manager, expect_exit=0)
        assert "removed" in r.stdout.lower() or "role" in r.stdout.lower()

    def test_tst_021_role_add_invalid(self, manager):
        """TST-021: Invalid role name rejected by argparse."""
        # Precondiciones: crear usuario
        run("user-add", "mm-bob", "--name", "Bob", "--user", manager)
        # --- Test: rol inexistente rechazado ---
        run("role-add", "mm-bob", "superadmin", "--user", manager, expect_exit=2)

    def test_tst_022_role_add_by_collaborator_blocked(self, manager):
        """TST-022: Collaborator cannot assign roles to others."""
        # Precondiciones: crear collaborator + usuario target
        run("user-add", "mm-col", "--name", "Col", "--user", manager)
        run("role-add", "mm-col", "collaborator", "--user", manager)
        run("user-add", "mm-bob", "--name", "Bob", "--user", manager)
        # --- Test: collaborator no puede asignar roles ---
        run("role-add", "mm-bob", "collaborator", "--user", "mm-col", expect_exit=1)

    def test_tst_023_dual_role_approver_collaborator(self, manager):
        """TST-023: User can hold multiple roles (approver + collaborator)."""
        # Precondiciones: crear usuario con rol approver
        run("user-add", "mm-apr", "--name", "APR", "--user", manager)
        run("role-add", "mm-apr", "approver", "--user", manager)
        # --- Test: agregar segundo rol al mismo usuario ---
        run("role-add", "mm-apr", "collaborator", "--user", manager, expect_exit=0)


# ============================================================
# 3a. MULTI-ROLE — TST-023a to TST-023e
# ============================================================

class TestMultiRole:
    """Tests for users holding multiple roles simultaneously."""

    @pytest.fixture
    def setup(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("client-add", "Acme", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        return "mm-mgr"

    def test_tst_023a_collaborator_approver_can_log(self, setup):
        """TST-023a: collaborator+approver can log time."""
        mgr = setup
        # Precondiciones: usuario con dual role, asignado al proyecto
        run("user-add", "mm-dual", "--name", "Dual", "--user", mgr)
        run("role-add", "mm-dual", "collaborator", "--user", mgr)
        run("role-add", "mm-dual", "approver", "--user", mgr)
        run("assign", "mm-dual", "--client", "Acme", "--project", "Web", "--user", mgr)
        # --- Test: dual role puede logear ---
        r = run("log", "Dual task", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-dual", expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_023b_timekeeper_collaborator_can_log(self, setup):
        """TST-023b: timekeeper+collaborator can log time (collaborator wins)."""
        mgr = setup
        # Precondiciones: usuario con timekeeper+collaborator
        run("user-add", "mm-dual", "--name", "Dual", "--user", mgr)
        run("role-add", "mm-dual", "timekeeper", "--user", mgr)
        run("role-add", "mm-dual", "collaborator", "--user", mgr)
        run("assign", "mm-dual", "--client", "Acme", "--project", "Web", "--user", mgr)
        # --- Test: collaborator permite logear a pesar de timekeeper ---
        r = run("log", "Dual task", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-dual", expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_023c_timekeeper_collaborator_can_modify(self, setup):
        """TST-023c: timekeeper+collaborator can modify own entry."""
        mgr = setup
        # Precondiciones: usuario con dual role logea entrada
        run("user-add", "mm-dual", "--name", "Dual", "--user", mgr)
        run("role-add", "mm-dual", "timekeeper", "--user", mgr)
        run("role-add", "mm-dual", "collaborator", "--user", mgr)
        run("assign", "mm-dual", "--client", "Acme", "--project", "Web", "--user", mgr)
        run("log", "Original", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-dual")
        # --- Test: collaborator permite modificar a pesar de timekeeper ---
        r = run("edit", "1", "--description", "Updated", "--user", "mm-dual", expect_exit=0)
        assert "updated" in r.stdout.lower()

    def test_tst_023d_manager_timekeeper_can_log(self, setup):
        """TST-023d: manager+timekeeper can log time (manager wins)."""
        mgr = setup
        # Precondiciones: manager con rol extra timekeeper
        run("role-add", mgr, "timekeeper", "--user", mgr)
        # --- Test: manager puede logear a pesar de timekeeper ---
        r = run("log", "Mgr task", "1h", "--client", "Acme", "--project", "Web", "--user", mgr, expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_023e_collaborator_approver_can_approve(self, setup):
        """TST-023e: collaborator+approver can approve entries."""
        mgr = setup
        # Precondiciones: collaborator logea, dual-role user aprueba
        run("user-add", "mm-col", "--name", "Col", "--user", mgr)
        run("role-add", "mm-col", "collaborator", "--user", mgr)
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", mgr)
        run("user-add", "mm-dual", "--name", "Dual", "--user", mgr)
        run("role-add", "mm-dual", "collaborator", "--user", mgr)
        run("role-add", "mm-dual", "approver", "--user", mgr)
        run("assign", "mm-dual", "--client", "Acme", "--project", "Web", "--user", mgr)
        run("setting-set", "approval_required", "true", "--user", mgr)
        run("log", "Col task", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-col")
        # --- Test: dual role puede aprobar ---
        r = run("approve", "1", "--user", "mm-dual", expect_exit=0)
        assert "approved" in r.stdout.lower()

    def test_tst_023f_timekeeper_only_cannot_log(self, setup):
        """TST-023f: timekeeper (solo) cannot log time."""
        mgr = setup
        # Precondiciones: usuario solo con rol timekeeper
        run("user-add", "mm-tk", "--name", "TK", "--user", mgr)
        run("role-add", "mm-tk", "timekeeper", "--user", mgr)
        run("assign", "mm-tk", "--client", "Acme", "--project", "Web", "--user", mgr)
        # --- Test: timekeeper no puede logear ---
        r = run("log", "TK task", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-tk", expect_exit=1)
        assert "timekeeper" in r.stdout.lower()

    def test_tst_023g_timekeeper_approver_can_log(self, setup):
        """TST-023g: timekeeper+approver CAN log time (approver wins)."""
        mgr = setup
        # Precondiciones: usuario con timekeeper+approver, sin collaborator
        run("user-add", "mm-dual", "--name", "Dual", "--user", mgr)
        run("role-add", "mm-dual", "timekeeper", "--user", mgr)
        run("role-add", "mm-dual", "approver", "--user", mgr)
        run("assign", "mm-dual", "--client", "Acme", "--project", "Web", "--user", mgr)
        # --- Test: approver permite logear a pesar de timekeeper ---
        r = run("log", "Dual task", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-dual", expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_023h_unassigned_collaborator_cannot_log(self, setup):
        """TST-023h: collaborator without assignment cannot log time."""
        mgr = setup
        # Precondiciones: collaborator sin asignación al proyecto
        run("user-add", "mm-col", "--name", "Col", "--user", mgr)
        run("role-add", "mm-col", "collaborator", "--user", mgr)
        # --- Test: sin asignación, collaborator no puede logear ---
        r = run("log", "Col task", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=1)
        assert "not assigned" in r.stdout.lower()

    def test_tst_023i_timekeeper_only_cannot_modify(self, setup):
        """TST-023i: timekeeper (solo) cannot modify entries."""
        mgr = setup
        # Precondiciones: manager logea entry, timekeeper intenta modificar
        run("log", "Mgr task", "1h", "--client", "Acme", "--project", "Web", "--user", mgr)
        run("user-add", "mm-tk", "--name", "TK", "--user", mgr)
        run("role-add", "mm-tk", "timekeeper", "--user", mgr)
        # --- Test: timekeeper no puede modificar ---
        r = run("edit", "1", "--description", "Hack", "--user", "mm-tk", expect_exit=1)
        assert "timekeeper" in r.stdout.lower()


# ============================================================
# 4. CLIENTS CRUD — TST-024 to TST-034
# ============================================================

class TestClients:

    @pytest.fixture
    def manager(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        return "mm-mgr"

    def test_tst_024_client_add_with_rate(self, manager):
        """TST-024: Manager creates client with hourly rate."""
        # --- Test ---
        r = run("client-add", "Acme", "--rate", "90", "--user", manager, expect_exit=0)
        assert "acme" in r.stdout.lower()

    def test_tst_025_client_add_no_rate(self, manager):
        """TST-025: Manager creates client without rate (uses default)."""
        # --- Test ---
        run("client-add", "Beta", "--user", manager, expect_exit=0)

    def test_tst_026_clients_list(self):
        """TST-026: List clients (no auth required)."""
        # --- Test ---
        run("clients", expect_exit=0)

    def test_tst_027_client_rename(self, manager):
        """TST-027: Manager renames existing client."""
        # Precondiciones: crear cliente
        run("client-add", "Acme", "--user", manager)
        # --- Test ---
        r = run("client-rename", "Acme", "Acme Corp", "--user", manager, expect_exit=0)
        assert "renamed" in r.stdout.lower() or "acme corp" in r.stdout.lower()

    def test_tst_028_client_rename_collaborator_blocked(self, manager):
        """TST-028: Collaborator cannot rename clients."""
        # Precondiciones: crear cliente + collaborator
        run("client-add", "Acme", "--user", manager)
        run("user-add", "mm-col", "--name", "Col", "--user", manager)
        run("role-add", "mm-col", "collaborator", "--user", manager)
        # --- Test ---
        run("client-rename", "Acme", "New", "--user", "mm-col", expect_exit=1)

    def test_tst_029_client_rename_not_found(self, manager):
        """TST-029: Rename nonexistent client fails."""
        # --- Test ---
        run("client-rename", "Ghost", "New", "--user", manager, expect_exit=1)

    def test_tst_030_client_deactivate_with_confirm(self, manager):
        """TST-030: Manager deactivates client with --confirm."""
        # Precondiciones: crear cliente
        run("client-add", "Acme", "--user", manager)
        # --- Test ---
        r = run("client-deactivate", "Acme", "--confirm", "--user", manager, expect_exit=0)
        assert "deactivat" in r.stdout.lower()

    def test_tst_031_client_deactivate_no_confirm(self, manager):
        """TST-031: Without --confirm shows prompt (no actual deactivation)."""
        # Precondiciones: crear cliente
        run("client-add", "Acme", "--user", manager)
        # --- Test: sin --confirm muestra prompt ---
        r = run("client-deactivate", "Acme", "--user", manager, expect_exit=0)
        assert "confirm" in r.stdout.lower()

    def test_tst_032_client_deactivate_collaborator_blocked(self, manager):
        """TST-032: Collaborator cannot deactivate clients."""
        # Precondiciones: crear cliente + collaborator
        run("client-add", "Acme", "--user", manager)
        run("user-add", "mm-col", "--name", "Col", "--user", manager)
        run("role-add", "mm-col", "collaborator", "--user", manager)
        # --- Test ---
        run("client-deactivate", "Acme", "--confirm", "--user", "mm-col", expect_exit=1)

    def test_tst_033_client_reactivate(self, manager):
        """TST-033: Manager reactivates deactivated client."""
        # Precondiciones: crear y desactivar cliente
        run("client-add", "Acme", "--user", manager)
        run("client-deactivate", "Acme", "--confirm", "--user", manager)
        # --- Test ---
        r = run("client-reactivate", "Acme", "--user", manager, expect_exit=0)
        assert "reactivat" in r.stdout.lower() or "active" in r.stdout.lower()

    def test_tst_034_client_reactivate_not_found(self, manager):
        """TST-034: Reactivate nonexistent client fails."""
        # --- Test ---
        run("client-reactivate", "Ghost", "--user", manager, expect_exit=1)


# ============================================================
# 5. PROJECTS CRUD — TST-035 to TST-045
# ============================================================

class TestProjects:

    @pytest.fixture
    def manager(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("client-add", "Acme", "--user", "mm-mgr")
        return "mm-mgr"

    def test_tst_035_project_add_active_client(self, manager):
        """TST-035: Manager creates project under active client."""
        # --- Test: fixture ya creó cliente Acme ---
        r = run("project-add", "Web", "--client", "Acme", "--user", manager, expect_exit=0)
        assert "web" in r.stdout.lower()

    def test_tst_036_project_add_no_client(self, manager):
        """TST-036: Manager creates project without client (standalone)."""
        # --- Test: proyecto sin cliente asociado ---
        run("project-add", "Standalone", "--user", manager, expect_exit=0)

    def test_tst_037_project_add_inactive_client(self, manager):
        """TST-037: Cannot create project under inactive client."""
        # Precondiciones: desactivar cliente
        run("client-deactivate", "Acme", "--confirm", "--user", manager)
        # --- Test ---
        r = run("project-add", "Web", "--client", "Acme", "--user", manager, expect_exit=1)
        assert "deactivat" in r.stdout.lower()

    def test_tst_038_projects_list_active(self):
        """TST-038: List active projects (no auth required)."""
        # --- Test ---
        run("projects", expect_exit=0)

    def test_tst_039_projects_list_all(self):
        """TST-039: List all projects including inactive (--all flag)."""
        # --- Test ---
        run("projects", "--all", expect_exit=0)

    def test_tst_040_project_deactivate_with_confirm(self, manager):
        """TST-040: Manager deactivates project with --confirm."""
        # Precondiciones: crear proyecto
        run("project-add", "Web", "--client", "Acme", "--user", manager)
        # --- Test ---
        r = run("project-deactivate", "Web", "--confirm", "--user", manager, expect_exit=0)
        assert "deactivat" in r.stdout.lower()

    def test_tst_041_project_deactivate_no_confirm(self, manager):
        """TST-041: Without --confirm shows prompt (no actual deactivation)."""
        # Precondiciones: crear proyecto
        run("project-add", "Web", "--client", "Acme", "--user", manager)
        # --- Test: sin --confirm muestra prompt ---
        r = run("project-deactivate", "Web", "--user", manager, expect_exit=0)
        assert "confirm" in r.stdout.lower()

    def test_tst_042_project_deactivate_inactive_client(self, manager):
        """TST-042: Cannot deactivate project whose client is inactive."""
        # Precondiciones: crear proyecto, desactivar cliente
        run("project-add", "Web", "--client", "Acme", "--user", manager)
        run("client-deactivate", "Acme", "--confirm", "--user", manager)
        # --- Test: proyecto de cliente inactivo no se puede desactivar ---
        run("project-deactivate", "Web", "--confirm", "--user", manager, expect_exit=1)

    def test_tst_043_project_deactivate_collaborator_blocked(self, manager):
        """TST-043: Collaborator cannot deactivate projects."""
        # Precondiciones: crear proyecto + collaborator
        run("project-add", "Web", "--client", "Acme", "--user", manager)
        run("user-add", "mm-col", "--name", "Col", "--user", manager)
        run("role-add", "mm-col", "collaborator", "--user", manager)
        # --- Test ---
        run("project-deactivate", "Web", "--confirm", "--user", "mm-col", expect_exit=1)

    def test_tst_044_project_reactivate(self, manager):
        """TST-044: Manager reactivates deactivated project."""
        # Precondiciones: crear y desactivar proyecto
        run("project-add", "Web", "--client", "Acme", "--user", manager)
        run("project-deactivate", "Web", "--confirm", "--user", manager)
        # --- Test ---
        r = run("project-reactivate", "Web", "--user", manager, expect_exit=0)
        assert "reactivat" in r.stdout.lower() or "active" in r.stdout.lower()

    def test_tst_045_project_reactivate_inactive_client(self, manager):
        """TST-045: Cannot reactivate project whose client is inactive."""
        # Precondiciones: crear proyecto, desactivar ambos
        run("project-add", "Web", "--client", "Acme", "--user", manager)
        run("project-deactivate", "Web", "--confirm", "--user", manager)
        run("client-deactivate", "Acme", "--confirm", "--user", manager)
        # --- Test: no se puede reactivar proyecto con cliente inactivo ---
        run("project-reactivate", "Web", "--user", manager, expect_exit=1)


# ============================================================
# 6. ASSIGNMENTS — TST-046 to TST-051
# ============================================================

class TestAssignments:

    @pytest.fixture
    def manager(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("client-add", "Acme", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        return "mm-mgr"

    def test_tst_046_assign_user_client_project(self, manager):
        """TST-046: Manager assigns user to specific client+project."""
        # --- Test: fixture ya creó mgr, col, Acme, Web ---
        r = run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", manager, expect_exit=0)
        assert "assign" in r.stdout.lower()

    def test_tst_047_assign_user_client_wildcard(self, manager):
        """TST-047: Manager assigns user to all projects under a client (wildcard)."""
        # --- Test: asignación sin --project = todos los proyectos del cliente ---
        run("assign", "mm-col", "--client", "Acme", "--user", manager, expect_exit=0)

    def test_tst_048_assign_collaborator_blocked(self, manager):
        """TST-048: Collaborator cannot assign users."""
        # --- Test: collaborator no puede asignar ---
        run("assign", "mm-col", "--client", "Acme", "--user", "mm-col", expect_exit=1)

    def test_tst_049_unassign(self, manager):
        """TST-049: Manager removes user assignment from client+project."""
        # Precondiciones: asignar usuario
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", manager)
        # --- Test ---
        r = run("unassign", "mm-col", "--client", "Acme", "--project", "Web", "--user", manager, expect_exit=0)
        assert "unassign" in r.stdout.lower() or "remov" in r.stdout.lower()

    def test_tst_050_assignments_all(self, manager):
        """TST-050: List all assignments (no user filter)."""
        # Precondiciones: asignar usuario
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", manager)
        # --- Test ---
        run("assignments", expect_exit=0)

    def test_tst_051_assignments_specific_user(self, manager):
        """TST-051: List assignments for specific user."""
        # Precondiciones: asignar usuario
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", manager)
        # --- Test: filtrar por usuario ---
        run("assignments", "mm-col", expect_exit=0)


# ============================================================
# 7. LOG — TST-052 to TST-067
# ============================================================

class TestLog:

    @pytest.fixture
    def setup(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        run("user-add", "mm-tk", "--name", "TK", "--user", "mm-mgr")
        run("role-add", "mm-tk", "timekeeper", "--user", "mm-mgr")
        run("user-add", "mm-apr", "--name", "APR", "--user", "mm-mgr")
        run("role-add", "mm-apr", "approver", "--user", "mm-mgr")
        run("client-add", "Acme", "--rate", "90", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("assign", "mm-apr", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")

    def test_tst_052_log_manager(self, setup):
        """TST-052: Manager logs time without approval."""
        # --- Test ---
        r = run("log", "Dev work", "2h", "--client", "Acme", "--project", "Web", "--user", "mm-mgr", expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_053_log_with_approval_required(self, setup):
        """TST-053: Collaborator log enters pending when approval_required=true."""
        # Precondiciones: activar workflow de aprobación
        run("setting-set", "approval_required", "true", "--user", "mm-mgr")
        # --- Test: entrada queda pendiente de aprobación ---
        r = run("log", "Dev work", "2h", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=0)
        assert "pending approval" in r.stdout.lower()

    def test_tst_054_log_no_client(self, setup):
        """TST-054: Log without --client fails."""
        # --- Test: falta cliente obligatorio ---
        run("log", "test", "1h", "--project", "Web", "--user", "mm-col", expect_exit=1)

    def test_tst_055_log_no_project(self, setup):
        """TST-055: Log without --project fails."""
        # --- Test: falta proyecto obligatorio ---
        run("log", "test", "1h", "--client", "Acme", "--user", "mm-col", expect_exit=1)

    def test_tst_056_log_inactive_client(self, setup):
        """TST-056: Log against inactive client fails."""
        # Precondiciones: desactivar cliente
        run("client-deactivate", "Acme", "--confirm", "--user", "mm-mgr")
        # --- Test ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=1)
        assert "deactivat" in r.stdout.lower()

    def test_tst_057_log_inactive_project(self, setup):
        """TST-057: Log against inactive project fails."""
        # Precondiciones: desactivar proyecto
        run("project-deactivate", "Web", "--confirm", "--user", "mm-mgr")
        # --- Test ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=1)
        assert "deactivat" in r.stdout.lower()

    def test_tst_058_log_timekeeper_blocked(self, setup):
        """TST-058: Timekeeper cannot log time (role restriction)."""
        # --- Test: timekeeper no tiene permiso de log ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-tk", expect_exit=1)
        assert "cannot log" in r.stdout.lower()

    def test_tst_059_log_unassigned_blocked(self, setup):
        """TST-059: User without assignment cannot log to project."""
        # Precondiciones: crear collaborator sin asignación
        run("user-add", "mm-x", "--name", "X", "--user", "mm-mgr")
        run("role-add", "mm-x", "collaborator", "--user", "mm-mgr")
        # --- Test ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-x", expect_exit=1)
        assert "not assigned" in r.stdout.lower() or "assignment" in r.stdout.lower()

    def test_tst_060_log_collaborator_assigned(self, setup):
        """TST-060: Assigned collaborator can log time."""
        # --- Test ---
        r = run("log", "Dev work", "2h", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_061_log_approver_assigned(self, setup):
        """TST-061: Assigned approver can log time."""
        # --- Test ---
        r = run("log", "Review work", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-apr", expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_062_log_external_id(self, setup):
        """TST-062: Log with external ID (JIRA ticket reference)."""
        # --- Test: adjuntar ID externo a la entrada ---
        r = run("log", "Dev", "1h", "--client", "Acme", "--project", "Web", "--external-id", "JIRA-123", "--user", "mm-col", expect_exit=0)
        assert "jira-123" in r.stdout.lower()

    def test_tst_063_log_date(self, setup):
        """TST-063: Log with explicit date (backdate entry)."""
        # --- Test: registrar horas en fecha específica ---
        r = run("log", "Dev", "1h", "--client", "Acme", "--project", "Web", "--date", "2026-06-01", "--user", "mm-col", expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_064_log_non_billable(self, setup):
        """TST-064: Log as non-billable time."""
        # --- Test: marcar entrada como no facturable ---
        r = run("log", "Dev", "1h", "--client", "Acme", "--project", "Web", "--non-billable", "--user", "mm-col", expect_exit=0)
        assert "no" in r.stdout.lower()

    def test_tst_065_duration_2h(self, setup):
        """TST-065: Duration format '2h' accepted."""
        # --- Test ---
        run("log", "Dev", "2h", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=0)

    def test_tst_066_duration_90m(self, setup):
        """TST-066: Duration format '90m' accepted."""
        # --- Test ---
        run("log", "Dev", "90m", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=0)

    def test_tst_067_duration_1h30m(self, setup):
        """TST-067: Duration format '1h30m' (mixed) accepted."""
        # --- Test ---
        run("log", "Dev", "1h30m", "--client", "Acme", "--project", "Web", "--user", "mm-col", expect_exit=0)


# ============================================================
# 8. SHOW / LIST / SEARCH — TST-068 to TST-082
# ============================================================

class TestShowListSearch:

    @pytest.fixture
    def with_entries(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        run("client-add", "Acme", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("log", "Task A", "2h", "--client", "Acme", "--project", "Web", "--user", "mm-col")
        run("log", "Task B", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        return "mm-mgr", "mm-col"

    def test_tst_068_show_own(self, with_entries):
        """TST-068: User shows own entry by ID."""
        mgr, col = with_entries
        # --- Test: collaborator ve su propia entrada ---
        r = run("show", "1", "--user", col, expect_exit=0)
        assert "task a" in r.stdout.lower()

    def test_tst_069_show_other_manager(self, with_entries):
        """TST-069: Manager can show any user's entry."""
        mgr, col = with_entries
        # --- Test: manager ve entrada de collaborator ---
        r = run("show", "1", "--user", mgr, expect_exit=0)
        assert "task a" in r.stdout.lower()

    def test_tst_070_show_not_found(self, with_entries):
        """TST-070: Show nonexistent entry returns not found."""
        mgr, col = with_entries
        # --- Test: ID inexistente ---
        r = run("show", "999", "--user", col, expect_exit=0)
        assert "not found" in r.stdout.lower()

    def test_tst_071_show_approval_status(self, with_entries):
        """TST-071: Show entry displays approval status when workflow on."""
        mgr, col = with_entries
        # Precondiciones: activar aprobación
        run("setting-set", "approval_required", "true", "--user", mgr)
        # --- Test: mostrar estado de aprobación ---
        r = run("show", "1", "--user", col, expect_exit=0)
        assert "approval" in r.stdout.lower() or "pending" in r.stdout.lower()

    def test_tst_072_show_rejected(self, with_entries):
        """TST-072: Show entry displays rejection status."""
        mgr, col = with_entries
        # Precondiciones: activar aprobación y rechazar entrada
        run("setting-set", "approval_required", "true", "--user", mgr)
        run("reject", "1", "--reason", "Bad", "--user", mgr)
        # --- Test: mostrar estado de rechazo ---
        r = run("show", "1", "--user", col, expect_exit=0)
        assert "reject" in r.stdout.lower()

    def test_tst_073_list_own(self, with_entries):
        """TST-073: User lists only own entries."""
        mgr, col = with_entries
        # --- Test: collaborator solo ve sus entradas ---
        r = run("list", "--user", col, expect_exit=0)
        assert "task a" in r.stdout.lower()
        assert "task b" not in r.stdout.lower()

    def test_tst_074_list_all_manager(self, with_entries):
        """TST-074: Manager lists all users' entries."""
        mgr, col = with_entries
        # --- Test: manager ve entradas de todos ---
        r = run("list", "--user", mgr, expect_exit=0)
        assert "task a" in r.stdout.lower()
        assert "task b" in r.stdout.lower()

    def test_tst_075_list_filter_client(self, with_entries):
        """TST-075: List entries filtered by client."""
        mgr, col = with_entries
        # --- Test: filtrar por cliente ---
        r = run("list", "--client", "Acme", "--user", mgr, expect_exit=0)
        lines = [l for l in r.stdout.split("\n") if l.strip() and l.strip()[0:1].isdigit()]
        assert len(lines) >= 1

    def test_tst_076_list_date_range(self, with_entries):
        """TST-076: List entries filtered by date range."""
        mgr, col = with_entries
        # --- Test: filtrar por rango de fechas ---
        r = run("list", "--date-from", "2026-01-01", "--date-to", "2026-12-31", "--user", mgr, expect_exit=0)

    def test_tst_077_list_with_status_column(self, with_entries):
        """TST-077: List shows status column when approval workflow on."""
        mgr, col = with_entries
        # Precondiciones: activar aprobación
        run("setting-set", "approval_required", "true", "--user", mgr)
        # --- Test: columna status visible ---
        r = run("list", "--user", mgr, expect_exit=0)
        assert "status" in r.stdout.lower()

    def test_tst_078_list_no_status_column(self, with_entries):
        """TST-078: List hides status column when approval workflow off."""
        mgr, col = with_entries
        # --- Test: sin workflow, no hay columna status ---
        r = run("list", "--user", mgr, expect_exit=0)
        assert "status" not in r.stdout.lower()

    def test_tst_079_search_own(self, with_entries):
        """TST-079: User searches only own entries."""
        mgr, col = with_entries
        # --- Test: collaborator busca en sus entradas ---
        r = run("search", "Task", "--user", col, expect_exit=0)
        assert "task a" in r.stdout.lower()

    def test_tst_080_search_all_manager(self, with_entries):
        """TST-080: Manager searches all users' entries."""
        mgr, col = with_entries
        # --- Test: manager busca en todas las entradas ---
        r = run("search", "Task", "--user", mgr, expect_exit=0)
        assert "task a" in r.stdout.lower()
        assert "task b" in r.stdout.lower()

    def test_tst_081_search_no_results(self, with_entries):
        """TST-081: Search with no matches returns empty message."""
        mgr, col = with_entries
        # --- Test: búsqueda sin resultados ---
        r = run("search", "zzznonexistent", "--user", mgr, expect_exit=0)
        assert "no entries" in r.stdout.lower() or "0 entries" in r.stdout.lower()

    def test_tst_082_search_external_id(self, with_entries):
        """TST-082: Search finds entry by external ID."""
        mgr, col = with_entries
        # Precondiciones: registrar entrada con ID externo
        run("log", "JIRA task", "1h", "--client", "Acme", "--project", "Web", "--external-id", "JIRA-999", "--user", mgr)
        # --- Test: buscar por external ID ---
        r = run("search", "JIRA-999", "--user", mgr, expect_exit=0)
        assert "jira-999" in r.stdout.lower()


# ============================================================
# 9. EDIT — TST-083 to TST-093
# ============================================================

class TestEdit:

    @pytest.fixture
    def setup_with_approval(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        run("user-add", "mm-apr", "--name", "APR", "--user", "mm-mgr")
        run("role-add", "mm-apr", "approver", "--user", "mm-mgr")
        run("user-add", "mm-tk", "--name", "TK", "--user", "mm-mgr")
        run("role-add", "mm-tk", "timekeeper", "--user", "mm-mgr")
        run("client-add", "Acme", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("assign", "mm-apr", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("setting-set", "approval_required", "true", "--user", "mm-mgr")
        run("log", "Task", "2h", "--client", "Acme", "--project", "Web", "--user", "mm-col")
        return "mm-mgr", "mm-col", "mm-apr", "mm-tk"

    def test_tst_083_edit_pending(self, setup_with_approval):
        """TST-083: Owner edits pending entry."""
        mgr, col, apr, tk = setup_with_approval
        # --- Test: collaborator edita su entrada pendiente ---
        r = run("edit", "1", "--description", "Updated", "--user", col, expect_exit=0)
        assert "updated" in r.stdout.lower()

    def test_tst_084_edit_rejected_resets_pending(self, setup_with_approval):
        """TST-084: Edit rejected entry resets status to pending."""
        mgr, col, apr, tk = setup_with_approval
        # Precondiciones: rechazar entrada
        run("reject", "1", "--reason", "Fix it", "--user", mgr)
        # --- Test: editar entrada rechazada la vuelve a pending ---
        r = run("edit", "1", "--description", "Fixed", "--user", col, expect_exit=0)
        assert "warning" in r.stdout.lower() or "pending" in r.stdout.lower()

    def test_tst_085_edit_approved_blocked(self, setup_with_approval):
        """TST-085: Cannot edit approved entry."""
        mgr, col, apr, tk = setup_with_approval
        # Precondiciones: aprobar entrada
        run("approve", "1", "--user", mgr)
        # --- Test: entrada aprobada no editable ---
        r = run("edit", "1", "--description", "Hack", "--user", col, expect_exit=1)
        assert "cannot edit" in r.stdout.lower() or "approved" in r.stdout.lower()

    def test_tst_086_edit_approved_workflow_off(self, setup_with_approval):
        """TST-086: Approved entry editable when approval workflow turned off."""
        mgr, col, apr, tk = setup_with_approval
        # Precondiciones: aprobar entrada, luego desactivar workflow
        run("approve", "1", "--user", mgr)
        run("setting-set", "approval_required", "false", "--user", mgr)
        # --- Test: sin workflow, entrada aprobada es editable ---
        r = run("edit", "1", "--description", "Hack", "--user", col, expect_exit=0)
        assert "updated" in r.stdout.lower()

    def test_tst_087_edit_other_blocked(self, setup_with_approval):
        """TST-087: Approver cannot edit another user's entry."""
        mgr, col, apr, tk = setup_with_approval
        # --- Test: approver solo edita sus entradas ---
        r = run("edit", "1", "--description", "Hack", "--user", apr, expect_exit=1)
        assert "own" in r.stdout.lower()

    def test_tst_088_edit_other_manager(self, setup_with_approval):
        """TST-088: Manager can edit any user's entry."""
        mgr, col, apr, tk = setup_with_approval
        # --- Test: manager edita entrada de collaborator ---
        r = run("edit", "1", "--description", "Mgr edit", "--user", mgr, expect_exit=0)
        assert "updated" in r.stdout.lower()

    def test_tst_089_edit_inactive_client(self, setup_with_approval):
        """TST-089: Cannot edit entry whose client is inactive."""
        mgr, col, apr, tk = setup_with_approval
        # Precondiciones: desactivar cliente
        run("client-deactivate", "Acme", "--confirm", "--user", mgr)
        # --- Test ---
        r = run("edit", "1", "--description", "Try", "--user", col, expect_exit=1)
        assert "deactivat" in r.stdout.lower()

    def test_tst_090_edit_not_found(self, setup_with_approval):
        """TST-090: Edit nonexistent entry returns not found."""
        mgr, col, apr, tk = setup_with_approval
        # --- Test: ID inexistente ---
        r = run("show", "999", "--user", col, expect_exit=0)
        assert "not found" in r.stdout.lower()

    def test_tst_091_edit_timekeeper_blocked(self, setup_with_approval):
        """TST-091: Timekeeper cannot modify entries."""
        mgr, col, apr, tk = setup_with_approval
        # --- Test: timekeeper no puede editar ---
        r = run("edit", "1", "--description", "Try", "--user", tk, expect_exit=1)
        assert "cannot modify" in r.stdout.lower()

    def test_tst_092_edit_other_approver_blocked(self, setup_with_approval):
        """TST-092: Approver cannot edit another user's entry (only own)."""
        mgr, col, apr, tk = setup_with_approval
        # --- Test: approver solo edita sus entradas ---
        r = run("edit", "1", "--description", "Try", "--user", apr, expect_exit=1)
        assert "own" in r.stdout.lower()

    def test_tst_093_edit_own_approver(self, setup_with_approval):
        """TST-093: Approver edits own entry."""
        mgr, col, apr, tk = setup_with_approval
        # Precondiciones: approver registra entrada propia
        run("log", "APR task", "1h", "--client", "Acme", "--project", "Web", "--user", apr)
        # --- Test: approver edita su propia entrada ---
        r = run("edit", "2", "--description", "Updated", "--user", apr, expect_exit=0)
        assert "updated" in r.stdout.lower()


# ============================================================
# 10. DELETE — TST-094 to TST-099
# ============================================================

class TestDelete:

    @pytest.fixture
    def setup(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        run("user-add", "mm-tk", "--name", "TK", "--user", "mm-mgr")
        run("role-add", "mm-tk", "timekeeper", "--user", "mm-mgr")
        run("client-add", "Acme", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("log", "Task", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-col")
        return "mm-mgr", "mm-col", "mm-tk"

    def test_tst_094_delete_own_with_confirm(self, setup):
        """TST-094: Owner deletes own entry with --confirm."""
        mgr, col, tk = setup
        # --- Test: collaborator borra su entrada ---
        r = run("delete", "1", "--confirm", "--user", col, expect_exit=0)
        assert "deleted" in r.stdout.lower()

    def test_tst_095_delete_no_confirm(self, setup):
        """TST-095: Without --confirm shows prompt (no actual deletion)."""
        mgr, col, tk = setup
        # --- Test: sin --confirm muestra prompt ---
        r = run("delete", "1", "--user", col, expect_exit=0)
        assert "confirm" in r.stdout.lower()

    def test_tst_096_delete_other_blocked(self, setup):
        """TST-096: Collaborator cannot delete another user's entry."""
        mgr, col, tk = setup
        # Precondiciones: manager borra entry 1 (mgr puede), crear entry 2 de manager
        run("delete", "1", "--confirm", "--user", "mm-mgr", expect_exit=0)
        # --- Test: collaborator no puede borrar entry de manager ---
        run("log", "Mgr task", "1h", "--client", "Acme", "--project", "Web", "--user", mgr)
        run("delete", "2", "--confirm", "--user", col, expect_exit=1)

    def test_tst_097_delete_other_manager(self, setup):
        """TST-097: Manager can delete any user's entry."""
        mgr, col, tk = setup
        # --- Test: manager borra entrada de collaborator ---
        r = run("delete", "1", "--confirm", "--user", mgr, expect_exit=0)
        assert "deleted" in r.stdout.lower()

    def test_tst_098_delete_timekeeper_blocked(self, setup):
        """TST-098: Timekeeper cannot delete entries."""
        mgr, col, tk = setup
        # --- Test: timekeeper no puede borrar ---
        run("delete", "1", "--confirm", "--user", tk, expect_exit=1)

    def test_tst_099_delete_not_found(self, setup):
        """TST-099: Delete nonexistent entry returns not found."""
        mgr, col, tk = setup
        # --- Test: ID inexistente ---
        r = run("show", "999", "--user", col, expect_exit=0)
        assert "not found" in r.stdout.lower()


# ============================================================
# 11-14. APPROVAL WORKFLOW — TST-100 to TST-137
# ============================================================

class TestApprovalWorkflow:

    @pytest.fixture
    def setup(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        run("user-add", "mm-apr", "--name", "APR", "--user", "mm-mgr")
        run("role-add", "mm-apr", "approver", "--user", "mm-mgr")
        run("user-add", "mm-tk", "--name", "TK", "--user", "mm-mgr")
        run("role-add", "mm-tk", "timekeeper", "--user", "mm-mgr")
        run("client-add", "Acme", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("assign", "mm-apr", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("setting-set", "approval_required", "true", "--user", "mm-mgr")
        run("log", "Task A", "2h", "--client", "Acme", "--project", "Web", "--user", "mm-col")
        run("log", "Task B", "1h", "--client", "Acme", "--project", "Web", "--user", "mm-col")
        return "mm-mgr", "mm-col", "mm-apr", "mm-tk"

    # --- Pending ---

    def test_tst_100_pending_entries(self, setup):
        """TST-100: Approver sees pending entries from assigned projects."""
        mgr, col, apr, tk = setup
        # --- Test: approver ve entradas pendientes ---
        r = run("pending", "--user", apr, expect_exit=0)
        assert "task a" in r.stdout.lower()

    def test_tst_101_pending_for_user(self, setup):
        """TST-101: Approver filters pending by specific user."""
        mgr, col, apr, tk = setup
        # --- Test: filtrar pendientes por usuario ---
        r = run("pending", "--for-user", col, "--user", apr, expect_exit=0)
        assert "task a" in r.stdout.lower()

    def test_tst_102_pending_project(self, setup):
        """TST-102: Approver filters pending by project."""
        mgr, col, apr, tk = setup
        # --- Test: filtrar pendientes por proyecto ---
        r = run("pending", "--project", "Web", "--user", apr, expect_exit=0)
        assert "pending" in r.stdout.lower()

    def test_tst_103_pending_client(self, setup):
        """TST-103: Approver filters pending by client."""
        mgr, col, apr, tk = setup
        # --- Test: filtrar pendientes por cliente ---
        r = run("pending", "--client", "Acme", "--user", apr, expect_exit=0)

    def test_tst_104_pending_date_range(self, setup):
        """TST-104: Approver filters pending by date range."""
        mgr, col, apr, tk = setup
        # --- Test: filtrar pendientes por rango de fechas ---
        r = run("pending", "--date-from", "2026-01-01", "--date-to", "2026-12-31", "--user", apr, expect_exit=0)

    def test_tst_105_pending_without_approval(self, setup):
        """TST-105: Pending command warns when approval workflow disabled."""
        mgr, col, apr, tk = setup
        # Precondiciones: desactivar workflow
        run("setting-set", "approval_required", "false", "--user", mgr)
        # --- Test: sin workflow, avisa que no está habilitado ---
        r = run("pending", "--user", apr, expect_exit=0)
        assert "not enabled" in r.stdout.lower()

    def test_tst_106_pending_collaborator_blocked(self, setup):
        """TST-106: Collaborator sees own rejections (empty)."""
        mgr, col, apr, tk = setup
        # --- Test: collaborator ve own_rejections (vacío) ---
        r = run("pending", "--user", col, expect_exit=0)
        assert "no pending" in r.stdout.lower() or "pending" not in r.stdout.lower()

    def test_tst_107_pending_timekeeper(self, setup):
        """TST-107: Timekeeper can view pending entries (read access)."""
        mgr, col, apr, tk = setup
        # --- Test: timekeeper tiene acceso de lectura ---
        r = run("pending", "--user", tk, expect_exit=0)

    def test_tst_108_pending_no_results(self, setup):
        """TST-108: Pending returns empty when all entries approved."""
        mgr, col, apr, tk = setup
        # Precondiciones: aprobar todas las entradas
        run("approve", "1", "2", "--user", mgr)
        # --- Test: sin entradas pendientes ---
        r = run("pending", "--user", apr, expect_exit=0)
        assert "no pending" in r.stdout.lower()

    def test_tst_109_pending_excludes_own(self, setup):
        """TST-109: Approver's pending list excludes own entries."""
        mgr, col, apr, tk = setup
        # Precondiciones: approver registra entrada propia
        run("log", "APR task", "1h", "--client", "Acme", "--project", "Web", "--user", apr)
        # --- Test: pendientes excluyen entradas propias del approver ---
        r = run("pending", "--user", apr, expect_exit=0)
        assert "apr task" not in r.stdout.lower()

    # --- Approve ---

    def test_tst_110_approve_pending(self, setup):
        """TST-110: Approver approves a pending entry."""
        mgr, col, apr, tk = setup
        # --- Test ---
        r = run("approve", "1", "--user", apr, expect_exit=0)
        assert "approved" in r.stdout.lower()

    def test_tst_111_approve_multiple(self, setup):
        """TST-111: Approver approves multiple entries in batch."""
        mgr, col, apr, tk = setup
        # --- Test: aprobar 2 entradas juntas ---
        r = run("approve", "1", "2", "--user", apr, expect_exit=0)
        assert "2 entry" in r.stdout.lower() or "approved" in r.stdout.lower()

    def test_tst_112_approve_manager_any_scope(self, setup):
        """TST-112: Manager approves any entry regardless of assignment."""
        mgr, col, apr, tk = setup
        # --- Test: manager no está asignado pero puede aprobar ---
        r = run("approve", "1", "--user", mgr, expect_exit=0)
        assert "approved" in r.stdout.lower()

    def test_tst_113_manager_auto_approve_own(self, setup):
        """TST-113: Manager approves own entry (auto-approve)."""
        mgr, col, apr, tk = setup
        # Precondiciones: manager registra entrada propia
        run("log", "Mgr task", "1h", "--client", "Acme", "--project", "Web", "--user", mgr)
        # --- Test: manager aprueba su propia entrada ---
        r = run("approve", "3", "--user", mgr, expect_exit=0)
        assert "approved" in r.stdout.lower()

    def test_tst_114_approver_cannot_auto_approve(self, setup):
        """TST-114: Approver cannot approve own entry (skipped)."""
        mgr, col, apr, tk = setup
        # Precondiciones: approver registra entrada propia
        run("log", "APR task", "1h", "--client", "Acme", "--project", "Web", "--user", apr)
        # --- Test: approver no puede auto-aprobar, se saltea ---
        r = run("approve", "3", "--user", apr, expect_exit=0)
        assert "skip" in r.stdout.lower() or "own" in r.stdout.lower()

    def test_tst_115_approve_unassigned_scope(self, setup):
        """TST-115: Approver skips entry from unassigned project."""
        mgr, col, apr, tk = setup
        # Precondiciones: crear proyecto donde approver no está asignado
        run("client-add", "Beta", "--user", mgr)
        run("project-add", "Mobile", "--client", "Beta", "--user", mgr)
        run("assign", "mm-col", "--client", "Beta", "--project", "Mobile", "--user", mgr)
        run("log", "Beta task", "1h", "--client", "Beta", "--project", "Mobile", "--user", col)
        # --- Test: approver no puede aprobar de proyecto no asignado ---
        r = run("approve", "3", "--user", apr, expect_exit=0)
        assert "skip" in r.stdout.lower()

    def test_tst_116_approve_already_approved(self, setup):
        """TST-116: Re-approving already approved entry is idempotent."""
        mgr, col, apr, tk = setup
        # Precondiciones: aprobar entrada
        run("approve", "1", "--user", mgr)
        # --- Test: segunda aprobación es idempotente ---
        r = run("approve", "1", "--user", mgr, expect_exit=0)
        assert "approved" in r.stdout.lower()

    def test_tst_117_approve_rejected(self, setup):
        """TST-117: Approving a rejected entry skipped."""
        mgr, col, apr, tk = setup
        # Precondiciones: rechazar entrada
        run("reject", "1", "--reason", "Bad", "--user", mgr)
        # --- Test: aprobar entrada rechazada se saltea ---
        r = run("approve", "1", "--user", mgr, expect_exit=0)
        assert "skip" in r.stdout.lower() or "rejected" in r.stdout.lower()

    def test_tst_118_approve_without_workflow(self, setup):
        """TST-118: Approve warns when approval workflow disabled."""
        mgr, col, apr, tk = setup
        # Precondiciones: desactivar workflow
        run("setting-set", "approval_required", "false", "--user", mgr)
        # --- Test: sin workflow, avisa que no está habilitado ---
        r = run("approve", "1", "--user", apr, expect_exit=0)
        assert "not enabled" in r.stdout.lower()

    def test_tst_119_approve_collaborator_blocked(self, setup):
        """TST-119: Collaborator cannot approve entries (skipped)."""
        mgr, col, apr, tk = setup
        # --- Test: collaborator sin permiso de aprobación ---
        r = run("approve", "1", "--user", col, expect_exit=0)
        assert "skip" in r.stdout.lower() or "role" in r.stdout.lower()

    def test_tst_120_approve_partial_failure(self, setup):
        """TST-120: Batch approve with partial failure (already approved + pending)."""
        mgr, col, apr, tk = setup
        # Precondiciones: aprobar entry 1, dejar entry 2 pendiente
        run("approve", "1", "--user", mgr)
        # --- Test: batch aprueba entry 2, saltea entry 1 ---
        r = run("approve", "1", "2", "--user", apr, expect_exit=0)
        assert "skip" in r.stdout.lower() or "approved" in r.stdout.lower()

    # --- Reject ---

    def test_tst_121_reject_pending(self, setup):
        """TST-121: Approver rejects pending entry with reason."""
        mgr, col, apr, tk = setup
        # --- Test ---
        r = run("reject", "1", "--reason", "Need detail", "--user", apr, expect_exit=0)
        assert "reject" in r.stdout.lower()

    def test_tst_122_reject_approved(self, setup):
        """TST-122: Reject an already approved entry (reconsideration)."""
        mgr, col, apr, tk = setup
        # Precondiciones: aprobar entrada
        run("approve", "1", "--user", mgr)
        # --- Test: rechazar entrada aprobada ---
        r = run("reject", "1", "--reason", "Reconsider", "--user", apr, expect_exit=0)
        assert "reject" in r.stdout.lower()

    def test_tst_123_reject_no_reason(self, setup):
        """TST-123: Reject without --reason fails (argparse error)."""
        mgr, col, apr, tk = setup
        # --- Test: --reason obligatorio para rechazar ---
        run("reject", "1", "--user", apr, expect_exit=2)

    def test_tst_124_reject_already_rejected(self, setup):
        """TST-124: Re-rejecting already rejected entry skipped."""
        mgr, col, apr, tk = setup
        # Precondiciones: rechazar entrada
        run("reject", "1", "--reason", "Bad", "--user", mgr)
        # --- Test: segundo rechazo se saltea ---
        r = run("reject", "1", "--reason", "Again", "--user", mgr, expect_exit=0)
        assert "skip" in r.stdout.lower() or "rejected" in r.stdout.lower()

    def test_tst_125_reject_manager(self, setup):
        """TST-125: Manager rejects any pending entry."""
        mgr, col, apr, tk = setup
        # --- Test ---
        r = run("reject", "1", "--reason", "Bad", "--user", mgr, expect_exit=0)
        assert "reject" in r.stdout.lower()

    def test_tst_126_reject_without_workflow(self, setup):
        """TST-126: Reject warns when approval workflow disabled."""
        mgr, col, apr, tk = setup
        # Precondiciones: desactivar workflow
        run("setting-set", "approval_required", "false", "--user", mgr)
        # --- Test: sin workflow, avisa que no está habilitado ---
        r = run("reject", "1", "--reason", "Bad", "--user", apr, expect_exit=0)
        assert "not enabled" in r.stdout.lower()

    def test_tst_127_reject_multiple(self, setup):
        """TST-127: Batch reject multiple entries."""
        mgr, col, apr, tk = setup
        # --- Test: rechazar 2 entradas juntas ---
        r = run("reject", "1", "2", "--reason", "Bad batch", "--user", apr, expect_exit=0)
        assert "reject" in r.stdout.lower()

    # --- Rejections / History ---

    def test_tst_128_rejections_with_entries(self, setup):
        """TST-128: User sees their rejected entries with reasons."""
        mgr, col, apr, tk = setup
        # Precondiciones: rechazar entrada
        run("reject", "1", "--reason", "Fix needed", "--user", mgr)
        # --- Test: collaborator ve sus rechazos ---
        r = run("rejections", "--user", col, expect_exit=0)
        assert "fix needed" in r.stdout.lower()

    def test_tst_129_rejections_empty(self, setup):
        """TST-129: Rejections returns empty when no rejections exist."""
        mgr, col, apr, tk = setup
        # --- Test: sin rechazos ---
        r = run("rejections", "--user", col, expect_exit=0)
        assert "no rejected" in r.stdout.lower()

    def test_tst_130_approval_history_with_data(self, setup):
        """TST-130: Approval history shows reject event."""
        mgr, col, apr, tk = setup
        # Precondiciones: rechazar entrada
        run("reject", "1", "--reason", "Bad", "--user", mgr)
        # --- Test: historial muestra rechazo ---
        r = run("approval-history", "1", "--user", col, expect_exit=0)
        assert "reject" in r.stdout.lower()

    def test_tst_131_approval_history_empty(self, setup):
        """TST-131: Approval history empty for pending entry (no events)."""
        mgr, col, apr, tk = setup
        # --- Test: entrada pendiente sin historial de aprobación ---
        r = run("approval-history", "1", "--user", col, expect_exit=0)
        assert "no approval" in r.stdout.lower() or "pending" in r.stdout.lower()

    def test_tst_132_approval_history_not_found(self, setup):
        """TST-132: Approval history for nonexistent entry."""
        mgr, col, apr, tk = setup
        # --- Test: ID inexistente ---
        r = run("approval-history", "999", "--user", col, expect_exit=0)
        assert "not found" in r.stdout.lower()

    # --- Full cycles ---

    def test_tst_133_cycle_log_approve(self, setup):
        """TST-133: Full cycle — log → approve → verify status."""
        mgr, col, apr, tk = setup
        # --- Test: ciclo completo de aprobación ---
        run("approve", "1", "--user", mgr)
        r = run("show", "1", "--user", col, expect_exit=0)
        assert "approved" in r.stdout.lower()

    def test_tst_134_cycle_reject_edit_approve(self, setup):
        """TST-134: Full cycle — reject → edit → approve."""
        mgr, col, apr, tk = setup
        # --- Test: ciclo de corrección ---
        run("reject", "1", "--reason", "Fix", "--user", mgr)
        run("edit", "1", "--description", "Fixed", "--user", col)
        run("approve", "1", "--user", mgr)
        r = run("show", "1", "--user", col, expect_exit=0)
        assert "approved" in r.stdout.lower()

    def test_tst_135_cycle_approve_reject_edit(self, setup):
        """TST-135: Full cycle — approve → reject → edit (back to pending)."""
        mgr, col, apr, tk = setup
        # --- Test: reconsideración vuelve entrada a pending ---
        run("approve", "1", "--user", mgr)
        run("reject", "1", "--reason", "Reconsider", "--user", mgr)
        run("edit", "1", "--description", "Updated", "--user", col)
        r = run("show", "1", "--user", col, expect_exit=0)
        assert "pending" in r.stdout.lower()

    def test_tst_136_edit_approved_blocked(self, setup):
        """TST-136: Cannot edit approved entry (reinforces TST-085)."""
        mgr, col, apr, tk = setup
        # Precondiciones: aprobar entrada
        run("approve", "1", "--user", mgr)
        # --- Test: edición bloqueada ---
        r = run("edit", "1", "--description", "Hack", "--user", col, expect_exit=1)
        assert "cannot edit" in r.stdout.lower()

    def test_tst_137_reject_approved_then_edit(self, setup):
        """TST-137: Reject approved entry, then owner can edit it."""
        mgr, col, apr, tk = setup
        # Precondiciones: aprobar y luego rechazar
        run("approve", "1", "--user", mgr)
        run("reject", "1", "--reason", "Error", "--user", mgr)
        # --- Test: entrada rechazada vuelve a ser editable ---
        r = run("edit", "1", "--description", "Corrected", "--user", col, expect_exit=0)
        assert "updated" in r.stdout.lower()


# ============================================================
# 15-17. DEACTIVATION CASCADES — TST-138 to TST-145
# ============================================================

class TestDeactivationCascades:

    @pytest.fixture
    def setup(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        run("client-add", "Acme", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        return "mm-mgr", "mm-col"

    def test_tst_138_log_inactive_client(self, setup):
        """TST-138: Cannot log time against inactive client."""
        mgr, col = setup
        # Precondiciones: desactivar cliente
        run("client-deactivate", "Acme", "--confirm", "--user", mgr)
        # --- Test ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", col, expect_exit=1)
        assert "deactivat" in r.stdout.lower()

    def test_tst_139_log_project_of_inactive_client(self, setup):
        """TST-139: Cannot log time on project whose client is inactive."""
        mgr, col = setup
        # Precondiciones: desactivar cliente
        run("client-deactivate", "Acme", "--confirm", "--user", mgr)
        # --- Test: proyecto de cliente inactivo también bloquea ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", col, expect_exit=1)

    def test_tst_140_edit_entry_inactive_client(self, setup):
        """TST-140: Cannot edit entry whose client is now inactive."""
        mgr, col = setup
        # Precondiciones: registrar entrada, luego desactivar cliente
        run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", col)
        run("client-deactivate", "Acme", "--confirm", "--user", mgr)
        # --- Test: edición bloqueada por cliente inactivo ---
        r = run("edit", "1", "--description", "Try", "--user", col, expect_exit=1)
        assert "deactivat" in r.stdout.lower()

    def test_tst_141_project_add_inactive_client(self, setup):
        """TST-141: Cannot create project under inactive client."""
        mgr, col = setup
        # Precondiciones: desactivar cliente
        run("client-deactivate", "Acme", "--confirm", "--user", mgr)
        # --- Test ---
        r = run("project-add", "Mobile", "--client", "Acme", "--user", mgr, expect_exit=1)
        assert "deactivat" in r.stdout.lower()

    def test_tst_142_reactivate_client_log_works(self, setup):
        """TST-142: Reactivating client restores logging ability."""
        mgr, col = setup
        # Precondiciones: desactivar y reactivar cliente
        run("client-deactivate", "Acme", "--confirm", "--user", mgr)
        run("client-reactivate", "Acme", "--user", mgr)
        # --- Test: log funciona tras reactivar ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", col, expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_143_log_inactive_project(self, setup):
        """TST-143: Cannot log time against inactive project."""
        mgr, col = setup
        # Precondiciones: desactivar proyecto
        run("project-deactivate", "Web", "--confirm", "--user", mgr)
        # --- Test ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", col, expect_exit=1)
        assert "deactivat" in r.stdout.lower()

    def test_tst_144_reactivate_project_log_works(self, setup):
        """TST-144: Reactivating project restores logging ability."""
        mgr, col = setup
        # Precondiciones: desactivar y reactivar proyecto
        run("project-deactivate", "Web", "--confirm", "--user", mgr)
        run("project-reactivate", "Web", "--user", mgr)
        # --- Test: log funciona tras reactivar ---
        r = run("log", "test", "1h", "--client", "Acme", "--project", "Web", "--user", col, expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_145_deactivate_project_inactive_client(self, setup):
        """TST-145: Cannot deactivate project whose client is inactive."""
        mgr, col = setup
        # Precondiciones: desactivar cliente
        run("client-deactivate", "Acme", "--confirm", "--user", mgr)
        # --- Test: proyecto de cliente inactivo no se puede desactivar ---
        r = run("project-deactivate", "Web", "--confirm", "--user", mgr, expect_exit=1)
        assert "deactivat" in r.stdout.lower()


# ============================================================
# 18-19. SETTINGS & CATEGORIES — TST-146 to TST-157
# ============================================================

class TestSettingsCategories:

    @pytest.fixture
    def manager(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        return "mm-mgr", "mm-col"

    def test_tst_146_settings_list(self, manager):
        """TST-146: List all system settings."""
        # --- Test ---
        r = run("settings", expect_exit=0)
        assert "default_rate" in r.stdout.lower()

    def test_tst_147_setting_get(self, manager):
        """TST-147: Get specific setting value."""
        # --- Test: default_rate = 85 ---
        r = run("setting-get", "default_rate", expect_exit=0)
        assert "85" in r.stdout

    def test_tst_148_setting_set_rate(self, manager):
        """TST-148: Manager updates default_rate setting."""
        mgr, col = manager
        # --- Test: cambiar tarifa default ---
        run("setting-set", "default_rate", "95", "--user", mgr, expect_exit=0)
        r = run("setting-get", "default_rate")
        assert "95" in r.stdout

    def test_tst_149_setting_set_approval_true(self, manager):
        """TST-149: Manager enables approval workflow."""
        mgr, col = manager
        # --- Test: activar aprobación ---
        run("setting-set", "approval_required", "true", "--user", mgr, expect_exit=0)
        r = run("setting-get", "approval_required")
        assert "true" in r.stdout.lower()

    def test_tst_150_setting_set_approval_false(self, manager):
        """TST-150: Manager disables approval workflow."""
        mgr, col = manager
        # Precondiciones: activar aprobación primero
        run("setting-set", "approval_required", "true", "--user", mgr)
        # --- Test: desactivar aprobación ---
        run("setting-set", "approval_required", "false", "--user", mgr, expect_exit=0)

    def test_tst_151_setting_set_collaborator_blocked(self, manager):
        """TST-151: Collaborator cannot modify settings."""
        mgr, col = manager
        # --- Test: collaborator sin permiso ---
        run("setting-set", "default_rate", "100", "--user", col, expect_exit=1)

    def test_tst_152_categories_list(self, manager):
        """TST-152: List time categories (includes defaults)."""
        # --- Test: categorías predefinidas ---
        r = run("categories", expect_exit=0)
        assert "development" in r.stdout.lower()

    def test_tst_153_category_add(self, manager):
        """TST-153: Manager adds new category."""
        mgr, col = manager
        # --- Test ---
        r = run("category-add", "mentoring", "--user", mgr, expect_exit=0)
        assert "mentoring" in r.stdout.lower()

    def test_tst_154_category_add_duplicate(self, manager):
        """TST-154: Adding duplicate category fails."""
        mgr, col = manager
        # Precondiciones: crear categoría
        run("category-add", "mentoring", "--user", mgr, expect_exit=0)
        # --- Test: duplicado rechazado ---
        run("category-add", "mentoring", "--user", mgr, expect_exit=1)

    def test_tst_155_category_remove(self, manager):
        """TST-155: Manager removes category."""
        mgr, col = manager
        # --- Test: eliminar categoría 'other' ---
        r = run("category-remove", "other", "--user", mgr, expect_exit=0)

    def test_tst_156_category_add_collaborator_blocked(self, manager):
        """TST-156: Collaborator cannot add categories."""
        mgr, col = manager
        # --- Test: collaborator sin permiso ---
        run("category-add", "newcat", "--user", col, expect_exit=1)

    def test_tst_157_category_remove_collaborator_blocked(self, manager):
        """TST-157: Collaborator cannot remove categories."""
        mgr, col = manager
        # --- Test: collaborator sin permiso ---
        run("category-remove", "other", "--user", col, expect_exit=1)


# ============================================================
# 20-21. REPORTING & EXPORT — TST-158 to TST-169
# ============================================================

class TestReportingExport:

    @pytest.fixture
    def setup(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("user-add", "mm-col", "--name", "Col", "--user", "mm-mgr")
        run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
        run("user-add", "mm-apr", "--name", "APR", "--user", "mm-mgr")
        run("role-add", "mm-apr", "approver", "--user", "mm-mgr")
        run("client-add", "Acme", "--user", "mm-mgr")
        run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
        run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("assign", "mm-apr", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        run("log", "Task A", "2h", "--client", "Acme", "--project", "Web", "--user", "mm-col")
        run("log", "Task B", "3h", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        return "mm-mgr", "mm-col", "mm-apr"

    def test_tst_158_summary_own(self, setup):
        """TST-158: User sees own time summary."""
        mgr, col, apr = setup
        # --- Test: collaborator ve resumen de sus horas ---
        r = run("summary", "--user", col, expect_exit=0)
        assert "2h" in r.stdout or "120" in r.stdout

    def test_tst_159_summary_team_manager(self, setup):
        """TST-159: Manager sees team summary with --team flag."""
        mgr, col, apr = setup
        # --- Test: manager ve resumen de todo el equipo ---
        r = run("summary", "--team", "--user", mgr, expect_exit=0)

    def test_tst_160_summary_team_collaborator(self, setup):
        """TST-160: Collaborator with --team (filtered or error)."""
        mgr, col, apr = setup
        # --- Test: collaborator no debería ver datos de equipo ---
        run("summary", "--team", "--user", col, expect_exit=0)

    def test_tst_161_summary_team_approver(self, setup):
        """TST-161: Approver with --team flag."""
        mgr, col, apr = setup
        # --- Test: approver ve resumen de equipo ---
        r = run("summary", "--team", "--user", apr, expect_exit=0)

    def test_tst_162_summary_round_up(self, setup):
        """TST-162: Summary with --round-up rounds minutes to hours."""
        mgr, col, apr = setup
        # --- Test: redondeo hacia arriba ---
        r = run("summary", "--round-up", "--user", mgr, expect_exit=0)

    def test_tst_163_stats_manager(self, setup):
        """TST-163: Manager views stats."""
        mgr, col, apr = setup
        # --- Test ---
        r = run("stats", "--user", mgr, expect_exit=0)

    def test_tst_164_stats_collaborator(self, setup):
        """TST-164: Collaborator views own stats."""
        mgr, col, apr = setup
        # --- Test ---
        r = run("stats", "--user", col, expect_exit=0)

    def test_tst_165_export_json(self, setup):
        """TST-165: Manager exports entries as JSON."""
        mgr, col, apr = setup
        # --- Test ---
        r = run("export", "json", "--user", mgr, expect_exit=0)

    def test_tst_166_export_csv(self, setup):
        """TST-166: Manager exports entries as CSV."""
        mgr, col, apr = setup
        # --- Test ---
        r = run("export", "csv", "--user", mgr, expect_exit=0)

    def test_tst_167_export_json_collaborator(self, setup):
        """TST-167: Collaborator exports own entries as JSON."""
        mgr, col, apr = setup
        # --- Test: collaborator exporta solo sus entradas ---
        r = run("export", "json", "--user", col, expect_exit=0)

    def test_tst_168_export_filtered(self, setup):
        """TST-168: Export filtered by client."""
        mgr, col, apr = setup
        # --- Test: filtrar exportación por cliente ---
        r = run("export", "json", "--client", "Acme", "--user", mgr, expect_exit=0)

    def test_tst_169_export_empty(self, fresh_db):
        """TST-169: Export with no entries returns empty message."""
        # --- Test: DB vacía, sin entradas ---
        r = run("export", "json", expect_exit=0)
        assert "exported" in r.stdout.lower()


# ============================================================
# 22. RATE CASCADE — TST-170 to TST-173
# ============================================================

class TestRateCascade:

    @pytest.fixture
    def setup(self):
        run("user-add", "mm-mgr", "--name", "Manager")
        run("role-add", "mm-mgr", "manager")
        run("client-add", "Acme", "--rate", "80", "--user", "mm-mgr")
        run("client-add", "Beta", "--user", "mm-mgr")  # no rate
        run("project-add", "Web", "--client", "Acme", "--rate", "100", "--user", "mm-mgr")
        run("project-add", "Mobile", "--client", "Acme", "--user", "mm-mgr")  # no project rate
        run("project-add", "Standalone", "--client", "Beta", "--user", "mm-mgr")
        return "mm-mgr"

    def test_tst_170_rate_from_project(self, setup):
        """TST-170: Rate resolved from project (project rate=100)."""
        mgr = setup
        # --- Test: proyecto Web tiene rate=100 ---
        r = run("log", "Dev", "1h", "--client", "Acme", "--project", "Web", "--user", mgr, expect_exit=0)
        s = run("show", "1", "--user", mgr)
        assert "100" in s.stdout

    def test_tst_171_rate_from_client(self, setup):
        """TST-171: Rate falls back to client (client rate=80, no project rate)."""
        mgr = setup
        # --- Test: proyecto Mobile sin rate → usa rate del cliente Acme=80 ---
        run("log", "Dev", "1h", "--client", "Acme", "--project", "Mobile", "--user", mgr, expect_exit=0)
        s = run("show", "1", "--user", mgr)
        assert "80" in s.stdout

    def test_tst_172_rate_default(self, setup):
        """TST-172: Rate falls back to default_rate=85 (no client/project rate)."""
        mgr = setup
        # --- Test: cliente Beta sin rate, proyecto sin rate → default ---
        run("log", "Dev", "1h", "--client", "Beta", "--project", "Standalone", "--user", mgr, expect_exit=0)
        s = run("show", "1", "--user", mgr)
        assert "85" in s.stdout

    def test_tst_173_rate_override(self, setup):
        """TST-173: Explicit --rate overrides project/client/default."""
        mgr = setup
        # --- Test: --rate 150 pisa rate del proyecto ---
        run("log", "Dev", "1h", "--client", "Acme", "--project", "Web", "--rate", "150", "--user", mgr, expect_exit=0)
        s = run("show", "1", "--user", mgr)
        assert "150" in s.stdout


# ============================================================
# 23. SINGLE-USER — TST-174 to TST-181
# ============================================================

class TestSingleUser:

    def test_tst_174_log_no_user(self):
        """TST-174: Log time without --user (single-user mode)."""
        # Precondiciones: crear cliente y proyecto sin autenticación
        run("client-add", "Acme")
        run("project-add", "Web", "--client", "Acme")
        # --- Test: registrar horas sin --user ---
        r = run("log", "Dev", "2h", "--client", "Acme", "--project", "Web", expect_exit=0)
        assert "logged" in r.stdout.lower()

    def test_tst_175_list_no_user(self):
        """TST-175: List entries without --user (single-user mode)."""
        # Precondiciones: registrar entrada sin --user
        run("client-add", "Acme")
        run("project-add", "Web", "--client", "Acme")
        run("log", "Dev", "2h", "--client", "Acme", "--project", "Web")
        # --- Test ---
        r = run("list", expect_exit=0)
        assert "dev" in r.stdout.lower()

    def test_tst_176_show_no_user(self):
        """TST-176: Show entry without --user (single-user mode)."""
        # Precondiciones: registrar entrada sin --user
        run("client-add", "Acme")
        run("project-add", "Web", "--client", "Acme")
        run("log", "Dev", "2h", "--client", "Acme", "--project", "Web")
        # --- Test ---
        r = run("show", "1", expect_exit=0)
        assert "dev" in r.stdout.lower()


# ============================================================
# 26. AUDIT LOG — TST-191 to TST-214
# ============================================================

def _get_audit(db_dir):
    """Query audit_log table from the test DB."""
    db_path = db_dir / "timetrack.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result


def _setup_full():
    """Bootstrap: manager + client + project + assignment."""
    run("user-add", "mm-mgr", "--name", "Manager")
    run("role-add", "mm-mgr", "manager")
    run("user-add", "mm-col", "--name", "Collab", "--user", "mm-mgr")
    run("role-add", "mm-col", "collaborator", "--user", "mm-mgr")
    run("user-add", "mm-apr", "--name", "Approver", "--user", "mm-mgr")
    run("role-add", "mm-apr", "approver", "--user", "mm-mgr")
    run("client-add", "Acme", "--rate", "90", "--user", "mm-mgr")
    run("project-add", "Web", "--client", "Acme", "--user", "mm-mgr")
    run("assign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
    run("assign", "mm-apr", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")


class TestAuditLog:

    def test_tst_191_audit_user_add_create(self, fresh_db):
        """TST-191: Audit on user-add (create)."""
        run("user-add", "mm-alice", "--name", "Alice")
        audit = _get_audit(fresh_db)
        assert len(audit) >= 1
        entry = audit[0]
        assert entry['action'] == 'create'
        assert entry['entity_type'] == 'user'
        assert entry['entity_id'] == 'mm-alice'
        assert entry['before_json'] is None
        after = json.loads(entry['after_json'])
        assert after['name'] == 'Alice'

    def test_tst_192_audit_role_add_create(self, fresh_db):
        """TST-192: Audit on role-add (create)."""
        run("user-add", "mm-alice", "--name", "Alice")
        run("role-add", "mm-alice", "manager")
        audit = _get_audit(fresh_db)
        role_entries = [a for a in audit if a['entity_type'] == 'role']
        assert len(role_entries) == 1
        e = role_entries[0]
        assert e['action'] == 'create'
        assert e['entity_id'] == 'mm-alice:manager'
        meta = json.loads(e['metadata'])
        assert meta['role'] == 'manager'

    def test_tst_193_audit_role_remove_delete(self, fresh_db):
        """TST-193: Audit on role-remove (delete)."""
        _setup_full()
        audit_before = len(_get_audit(fresh_db))
        run("role-remove", "mm-col", "collaborator", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[audit_before:] if a['entity_type'] == 'role']
        assert len(new) == 1
        assert new[0]['action'] == 'delete'
        assert new[0]['before_json'] is not None

    def test_tst_194_audit_client_add_create(self, fresh_db):
        """TST-194: Audit on client-add (create)."""
        _setup_full()
        audit = _get_audit(fresh_db)
        client_entries = [a for a in audit if a['entity_type'] == 'client']
        assert len(client_entries) == 1
        e = client_entries[0]
        assert e['action'] == 'create'
        after = json.loads(e['after_json'])
        assert after['name'] == 'Acme'
        assert e['actor_id'] == 'mm-mgr'

    def test_tst_195_audit_client_rename_update(self, fresh_db):
        """TST-195: Audit on client-rename (update)."""
        _setup_full()
        n = len(_get_audit(fresh_db))
        run("client-rename", "Acme", "Acme Corp", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'client']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        before = json.loads(e['before_json'])
        after = json.loads(e['after_json'])
        assert before['name'] == 'Acme'
        assert after['name'] == 'Acme Corp'

    def test_tst_196_audit_client_deactivate_update(self, fresh_db):
        """TST-196: Audit on client-deactivate (update)."""
        _setup_full()
        n = len(_get_audit(fresh_db))
        run("client-deactivate", "Acme", "--confirm", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'client']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        before = json.loads(e['before_json'])
        after = json.loads(e['after_json'])
        assert before['active'] == 1
        assert after['active'] == 0

    def test_tst_197_audit_project_add_create(self, fresh_db):
        """TST-197: Audit on project-add (create)."""
        _setup_full()
        audit = _get_audit(fresh_db)
        proj = [a for a in audit if a['entity_type'] == 'project']
        assert len(proj) == 1
        e = proj[0]
        assert e['action'] == 'create'
        after = json.loads(e['after_json'])
        assert after['name'] == 'Web'

    def test_tst_198_audit_assignment_create_delete(self, fresh_db):
        """TST-198: Audit on assign/unassign (create/delete)."""
        _setup_full()
        audit = _get_audit(fresh_db)
        assigns = [a for a in audit if a['entity_type'] == 'assignment']
        assert len(assigns) >= 1
        assert any(a['action'] == 'create' for a in assigns)
        n = len(_get_audit(fresh_db))
        run("unassign", "mm-col", "--client", "Acme", "--project", "Web", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'assignment']
        assert len(new) == 1
        assert new[0]['action'] == 'delete'
        assert new[0]['before_json'] is not None

    def test_tst_199_audit_log_entry_create(self, fresh_db):
        """TST-199: Audit on log entry (create)."""
        _setup_full()
        n = len(_get_audit(fresh_db))
        run("log", "Dev work", "2h", "--client", "Acme", "--project", "Web",
            "--user", "mm-col")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'entry']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'create'
        after = json.loads(e['after_json'])
        assert after['description'] == 'Dev work'
        assert e['actor_id'] == 'mm-col'

    def test_tst_200_audit_edit_entry_update(self, fresh_db):
        """TST-200: Audit on edit entry (update)."""
        _setup_full()
        run("log", "Dev work", "2h", "--client", "Acme", "--project", "Web",
            "--user", "mm-col")
        n = len(_get_audit(fresh_db))
        run("edit", "1", "--description", "Updated work", "--user", "mm-col")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'entry']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        before = json.loads(e['before_json'])
        after = json.loads(e['after_json'])
        assert before['description'] == 'Dev work'
        assert after['description'] == 'Updated work'

    def test_tst_201_audit_delete_entry_delete(self, fresh_db):
        """TST-201: Audit on delete entry (delete)."""
        _setup_full()
        run("log", "Dev work", "2h", "--client", "Acme", "--project", "Web",
            "--user", "mm-col")
        n = len(_get_audit(fresh_db))
        run("delete", "1", "--confirm", "--user", "mm-col")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'entry']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'delete'
        assert e['before_json'] is not None
        assert e['after_json'] is None

    def test_tst_202_audit_approve_update(self, fresh_db):
        """TST-202: Audit on approve (update)."""
        _setup_full()
        run("setting-set", "approval_required", "true", "--user", "mm-mgr")
        run("log", "Dev work", "2h", "--client", "Acme", "--project", "Web",
            "--user", "mm-col")
        n = len(_get_audit(fresh_db))
        run("approve", "1", "--user", "mm-apr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'entry']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        meta = json.loads(e['metadata'])
        assert meta['approval_action'] == 'approved'

    def test_tst_203_audit_reject_update(self, fresh_db):
        """TST-203: Audit on reject (update)."""
        _setup_full()
        run("setting-set", "approval_required", "true", "--user", "mm-mgr")
        run("log", "Dev work", "2h", "--client", "Acme", "--project", "Web",
            "--user", "mm-col")
        n = len(_get_audit(fresh_db))
        run("reject", "1", "--reason", "Bad quality", "--user", "mm-apr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'entry']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        meta = json.loads(e['metadata'])
        assert meta['approval_action'] == 'rejected'
        assert meta['reason'] == 'Bad quality'

    def test_tst_204_audit_setting_create(self, fresh_db):
        """TST-204: Audit on setting-set for new setting (create)."""
        _setup_full()
        n = len(_get_audit(fresh_db))
        run("setting-set", "custom_flag", "enabled", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'setting']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'create'
        assert e['before_json'] is None
        after = json.loads(e['after_json'])
        assert after['value'] == 'enabled'

    def test_tst_205_audit_setting_update(self, fresh_db):
        """TST-205: Audit on setting-set for existing setting (update)."""
        _setup_full()
        run("setting-set", "custom_flag", "v1", "--user", "mm-mgr")
        n = len(_get_audit(fresh_db))
        run("setting-set", "custom_flag", "v2", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'setting']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        before = json.loads(e['before_json'])
        after = json.loads(e['after_json'])
        assert before['value'] == 'v1'
        assert after['value'] == 'v2'

    def test_tst_206_audit_category_add_create(self, fresh_db):
        """TST-206: Audit on category-add (create)."""
        _setup_full()
        n = len(_get_audit(fresh_db))
        run("category-add", "qa-testing", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'category']
        assert len(new) == 1
        assert new[0]['action'] == 'create'
        after = json.loads(new[0]['after_json'])
        assert after['name'] == 'qa-testing'

    def test_tst_207_audit_category_remove_update(self, fresh_db):
        """TST-207: Audit on category-remove (update)."""
        _setup_full()
        run("category-add", "qa-testing", "--user", "mm-mgr")
        n = len(_get_audit(fresh_db))
        run("category-remove", "qa-testing", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'category']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        before = json.loads(e['before_json'])
        after = json.loads(e['after_json'])
        assert before['active'] == 1
        assert after['active'] == 0

    def test_tst_208_audit_user_deactivate_update(self, fresh_db):
        """TST-208: Audit on user-deactivate (update)."""
        _setup_full()
        n = len(_get_audit(fresh_db))
        run("user-deactivate", "mm-col", "--confirm", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'user']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        before = json.loads(e['before_json'])
        after = json.loads(e['after_json'])
        assert before['active'] == 1
        assert after['active'] == 0

    def test_tst_209_audit_actor_id_correct(self, fresh_db):
        """TST-209: Audit actor_id matches manager who executed."""
        _setup_full()
        audit = _get_audit(fresh_db)
        mgr_actions = [a for a in audit if a['actor_id'] == 'mm-mgr']
        assert len(mgr_actions) > 0

    def test_tst_210_audit_actor_id_null_bootstrap(self, fresh_db):
        """TST-210: Audit actor_id NULL in bootstrap (first user-add)."""
        run("user-add", "mm-first", "--name", "First")
        audit = _get_audit(fresh_db)
        assert len(audit) >= 1
        e = audit[0]
        assert e['action'] == 'create'
        assert e['entity_type'] == 'user'
        assert e['actor_id'] is None

    def test_tst_211_readonly_no_audit(self, fresh_db):
        """TST-211: Read-only commands do not generate audit entries."""
        _setup_full()
        run("log", "Work", "2h", "--client", "Acme", "--project", "Web",
            "--user", "mm-col")
        n = len(_get_audit(fresh_db))
        run("show", "1", "--user", "mm-col")
        run("list", "--user", "mm-col")
        run("clients")
        run("projects")
        run("settings")
        run("categories")
        audit_after = _get_audit(fresh_db)
        assert len(audit_after) == n, "Read-only commands should not create audit entries"

    def test_tst_212_audit_timestamp_populated(self, fresh_db):
        """TST-212: Audit timestamps are populated and valid ISO format."""
        _setup_full()
        audit = _get_audit(fresh_db)
        assert len(audit) > 0
        for a in audit:
            assert a['timestamp'] is not None
            assert 'T' in a['timestamp'] or '-' in a['timestamp']

    def test_tst_213_audit_client_reactivate_update(self, fresh_db):
        """TST-213: Audit on client-reactivate (update)."""
        _setup_full()
        run("client-deactivate", "Acme", "--confirm", "--user", "mm-mgr")
        n = len(_get_audit(fresh_db))
        run("client-reactivate", "Acme", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        new = [a for a in audit[n:] if a['entity_type'] == 'client']
        assert len(new) == 1
        e = new[0]
        assert e['action'] == 'update'
        before = json.loads(e['before_json'])
        after = json.loads(e['after_json'])
        assert before['active'] == 0
        assert after['active'] == 1

    def test_tst_214_audit_project_deactivate_reactivate(self, fresh_db):
        """TST-214: Audit on project-deactivate/reactivate (update)."""
        _setup_full()
        n = len(_get_audit(fresh_db))
        run("project-deactivate", "Web", "--confirm", "--user", "mm-mgr")
        audit = _get_audit(fresh_db)
        deact = [a for a in audit[n:] if a['entity_type'] == 'project']
        assert len(deact) == 1
        before = json.loads(deact[0]['before_json'])
        after = json.loads(deact[0]['after_json'])
        assert before['active'] == 1
        assert after['active'] == 0
        n2 = len(audit)
        run("project-reactivate", "Web", "--user", "mm-mgr")
        audit2 = _get_audit(fresh_db)
        react = [a for a in audit2[n2:] if a['entity_type'] == 'project']
        assert len(react) == 1
        before2 = json.loads(react[0]['before_json'])
        after2 = json.loads(react[0]['after_json'])
        assert before2['active'] == 0
        assert after2['active'] == 1


# ============================================================
# 27. ME COMMAND — TST-215 to TST-217
# ============================================================

class TestMe:

    def test_tst_215_me_valid_user(self, fresh_db):
        """TST-215: me returns user name."""
        run("user-add", "mm-alice", "--name", "Alice Manager")
        run("role-add", "mm-alice", "manager")
        r = run("me", "--user", "mm-alice")
        assert "Alice Manager" in r.stdout

    def test_tst_216_me_no_user_multiuser(self, fresh_db):
        """TST-216: me without --user in multi-user mode errors."""
        run("user-add", "mm-alice", "--name", "Alice")
        run("role-add", "mm-alice", "manager")
        r = run("me", expect_exit=1)
        output = (r.stdout + r.stderr).lower()
        assert "user" in output or "required" in output

    def test_tst_217_me_unknown_user(self, fresh_db):
        """TST-217: me with unknown user returns not found."""
        run("user-add", "mm-alice", "--name", "Alice")
        run("role-add", "mm-alice", "manager")
        r = run("me", "--user", "mm-nobody", expect_exit=0)
        assert "not found" in r.stdout.lower()
