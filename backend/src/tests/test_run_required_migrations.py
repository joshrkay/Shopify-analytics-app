"""Tests for migration SQL statement splitting."""

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_required_migrations.py"
    spec = importlib.util.spec_from_file_location("run_required_migrations", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_split_sql_statements_handles_dollar_quoted_functions():
    mod = _load_module()
    sql = """
    CREATE TABLE demo (id int);

    CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS trigger AS $$
    BEGIN
        NEW.id = COALESCE(NEW.id, 1);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg BEFORE INSERT ON demo FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """

    statements = mod.split_sql_statements(sql)

    assert len(statements) == 3
    assert statements[0].startswith("CREATE TABLE demo")
    assert "LANGUAGE plpgsql" in statements[1]
    assert statements[2].startswith("CREATE TRIGGER trg")


def test_split_sql_statements_ignores_semicolons_in_comments_and_strings():
    mod = _load_module()
    sql = """
    -- Comment with ; should not split
    INSERT INTO notes(text) VALUES ('hello;world');
    /* block comment ; still comment */
    UPDATE notes SET text = 'done' WHERE id = 1;
    """

    statements = mod.split_sql_statements(sql)

    assert len(statements) == 2
    assert statements[0].startswith("-- Comment")
    assert "'hello;world'" in statements[0]
    assert statements[1].startswith("/* block comment")
