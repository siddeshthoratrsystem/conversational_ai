"""The message footer, the audit helper and the store's transaction (spec 011, T019)."""

from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, insert, select, text

from wealth_agent.actions import gate, store

FOOTER = "Demo data: no real account was changed."


# --- footer ----------------------------------------------------------------------------------


def test_footer_is_the_last_line_after_a_blank_line():
    out = gate.with_footer("Done.")
    assert out == f"Done.\n\n{FOOTER}"
    assert out.splitlines()[-1] == FOOTER


def test_footer_added_once_even_if_applied_twice():
    out = gate.with_footer(gate.with_footer("Done."))
    assert out.count(FOOTER) == 1
    assert out.endswith(FOOTER)


# --- audit helper ----------------------------------------------------------------------------


def test_audit_helper_inserts_one_row_with_only_permitted_columns(engine, gate_store):
    with gate_store.transaction() as conn:
        gate.record_audit(conn, "alice", "contribution_change", "rejected", reason="out_of_range")
    with engine.connect() as conn:
        rows = conn.execute(select(store.action_audit)).all()
    assert len(rows) == 1
    row = rows[0]
    assert (row.user_id, row.action_type, row.step, row.reason) == (
        "alice",
        "contribution_change",
        "rejected",
        "out_of_range",
    )
    assert row.pending_action_id is None
    assert row.created_at is not None
    columns = {c["name"] for c in inspect(engine).get_columns("action_audit")}
    assert columns == {"id", "user_id", "action_type", "pending_action_id", "step", "reason", "created_at"}


def test_audit_helper_accepts_a_rejected_row_without_a_pending_action_id(engine, gate_store):
    with gate_store.transaction() as conn:
        gate.record_audit(conn, "alice", "contribution_change", "rejected", reason="nothing_pending")
    with engine.connect() as conn:
        assert conn.execute(select(store.action_audit.c.pending_action_id)).scalar_one() is None


def test_audit_steps_match_the_database_check(engine, gate_store):
    for step in ("rejected", "staged", "confirmed", "cancelled", "expired", "executed", "failed"):
        with gate_store.transaction() as conn:
            gate.record_audit(conn, "alice", "contribution_change", step)
    with pytest.raises(store.GateStoreError):
        with gate_store.transaction() as conn:
            gate.record_audit(conn, "alice", "contribution_change", "proposed")


def test_the_audit_helper_only_inserts():
    import inspect as py_inspect

    source = py_inspect.getsource(gate)
    assert "update(store.action_audit" not in source and "delete(store.action_audit" not in source


# --- store.transaction -------------------------------------------------------------------------


class FakeConnection:
    def __init__(self, log):
        self.log = log

    def execute(self, statement, *args, **kwargs):
        self.log.append(str(statement))
        return SimpleNamespace(rowcount=0)


class FakePostgresEngine:
    """Records what a transaction sends, without a database."""

    def __init__(self):
        self.log = []
        self.dialect = SimpleNamespace(name="postgresql")

    def begin(self):
        from contextlib import contextmanager

        @contextmanager
        def tx():
            yield FakeConnection(self.log)

        return tx()


def test_a_postgres_transaction_sets_the_statement_timeout_first_for_reads():
    engine = FakePostgresEngine()
    with store.Store(engine, timeout_ms=3000).transaction() as conn:
        conn.execute(select(store.contributions))
    assert engine.log[0] == "SET LOCAL statement_timeout = 3000"
    assert "SELECT" in engine.log[1].upper()


def test_a_postgres_transaction_sets_the_statement_timeout_first_for_writes():
    engine = FakePostgresEngine()
    with store.Store(engine, timeout_ms=1500).transaction() as conn:
        conn.execute(insert(store.action_audit).values(user_id="a", action_type="x", step="staged"))
    assert engine.log[0] == "SET LOCAL statement_timeout = 1500"


def test_sqlite_has_no_statement_timeout_statement(engine, gate_store):
    statements = []
    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", lambda c, cur, stmt, *a: statements.append(stmt))
    with gate_store.transaction() as conn:
        conn.execute(select(store.contributions))
    assert not any("statement_timeout" in s for s in statements)


def test_the_timeout_comes_from_the_settings():
    from wealth_agent.actions import config

    engine = FakePostgresEngine()
    settings = config.load_settings({"ACTION_DB_TIMEOUT_SECONDS": "2"})
    with store.Store.from_settings(engine, settings).transaction():
        pass
    assert engine.log == ["SET LOCAL statement_timeout = 2000"]


def test_a_database_error_inside_a_transaction_raises_gate_store_error_and_rolls_back(engine, gate_store, switch):
    switch.fail("error", only="from contributions")
    with pytest.raises(store.GateStoreError):
        with gate_store.transaction() as conn:
            gate.record_audit(conn, "alice", "contribution_change", "staged")
            conn.execute(select(store.contributions))
    with engine.connect() as conn:
        assert conn.execute(select(store.action_audit)).all() == []


def test_a_statement_timeout_raises_gate_store_error_and_rolls_back(engine, gate_store, switch):
    switch.fail("timeout", only="from contributions")
    with pytest.raises(store.GateStoreError) as raised:
        with gate_store.transaction() as conn:
            gate.record_audit(conn, "alice", "contribution_change", "staged")
            conn.execute(select(store.contributions))
    assert raised.value.timed_out is True
    with engine.connect() as conn:
        assert conn.execute(select(store.action_audit)).all() == []


def test_a_successful_transaction_commits(engine, gate_store):
    with gate_store.transaction() as conn:
        conn.execute(text("SELECT 1"))
        gate.record_audit(conn, "alice", "contribution_change", "staged")
    with engine.connect() as conn:
        assert len(conn.execute(select(store.action_audit)).all()) == 1


def test_the_store_never_creates_tables_outside_tests():
    import inspect as py_inspect

    assert "create_all" not in py_inspect.getsource(store.Store)
    assert "create_all" not in py_inspect.getsource(store.get_store)
