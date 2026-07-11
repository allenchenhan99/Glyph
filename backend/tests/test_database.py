from sqlalchemy import create_engine, inspect

from glyph.database import migrate_sqlite_schema


def test_sqlite_migration_adds_formula_latex_to_existing_blocks_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE blocks (id VARCHAR(36) PRIMARY KEY)")

    migrate_sqlite_schema(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("blocks")}
    assert "formula_latex" in columns
