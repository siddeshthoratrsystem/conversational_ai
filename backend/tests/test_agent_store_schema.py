"""The agent's copy of the gate tables must match the back end's models (research R21).

The agent cannot import the back end, so `agent/src/wealth_agent/actions/store.py` defines its own
copy. It imports only SQLAlchemy, so it is loaded here by file path.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import models

STORE = Path(__file__).resolve().parents[2] / "agent/src/wealth_agent/actions/store.py"
TABLES = ["contributions", "pending_actions", "action_audit"]


@pytest.fixture(scope="module")
def agent_store():
    assert STORE.exists(), f"{STORE} is missing"
    spec = importlib.util.spec_from_file_location("agent_store_under_test", STORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tables(agent_store, name):
    return models.Base.metadata.tables[name], agent_store.metadata.tables[name]


@pytest.mark.parametrize("name", TABLES)
def test_columns_match(agent_store, name):
    backend, agent = _tables(agent_store, name)
    describe = lambda t: {  # noqa: E731
        c.name: (str(c.type.compile(dialect=postgresql.dialect())), c.nullable, c.primary_key)
        for c in t.columns
    }
    assert describe(agent) == describe(backend)


@pytest.mark.parametrize("name", TABLES)
def test_named_check_constraints_match(agent_store, name):
    backend, agent = _tables(agent_store, name)
    checks = lambda t: {  # noqa: E731
        c.name: " ".join(str(c.sqltext).split()) for c in t.constraints if isinstance(c, CheckConstraint)
    }
    assert checks(agent) == checks(backend)


@pytest.mark.parametrize("name", TABLES)
def test_foreign_keys_match(agent_store, name):
    backend, agent = _tables(agent_store, name)
    fks = lambda t: {  # noqa: E731
        (tuple(c.column_keys), tuple(e.target_fullname for e in c.elements))
        for c in t.constraints
        if isinstance(c, ForeignKeyConstraint)
    }
    assert fks(agent) == fks(backend)


def test_pending_actions_session_fk_points_at_sessions(agent_store):
    _, agent = _tables(agent_store, "pending_actions")
    targets = {e.target_fullname for fk in agent.foreign_key_constraints for e in fk.elements}
    assert "sessions.id" in targets


def test_partial_unique_index_matches(agent_store):
    backend, agent = _tables(agent_store, "pending_actions")
    sql = lambda t: {  # noqa: E731
        i.name: " ".join(str(CreateIndex(i).compile(dialect=postgresql.dialect())).split())
        for i in t.indexes
    }
    assert sql(agent) == sql(backend)
    assert "WHERE status = 'pending'" in sql(agent)["uq_pending_actions_one_pending"]


@pytest.mark.parametrize("name", TABLES)
def test_create_table_sql_matches(agent_store, name):
    backend, agent = _tables(agent_store, name)
    render = lambda t: " ".join(str(CreateTable(t).compile(dialect=postgresql.dialect())).split())  # noqa: E731
    # FK constraint names differ only if one side leaves them unnamed
    assert render(agent) == render(backend)


def test_the_agents_sessions_table_has_an_id_primary_key(agent_store):
    sessions = agent_store.metadata.tables["sessions"]
    assert [c.name for c in sessions.primary_key.columns] == ["id"]
