import pytest

from src.storage.additive_schema import ensure_additive_schema
from src.storage.models import SetupLog, Trade


def test_new_journal_rows_default_to_binance():
    assert SetupLog.__table__.c.venue.default.arg == "binance"
    assert Trade.__table__.c.venue.default.arg == "binance"


@pytest.mark.asyncio
async def test_additive_venue_columns_default_to_binance():
    class Connection:
        statements = []

        async def execute(self, statement):
            self.statements.append(str(statement))

    connection = Connection()
    await ensure_additive_schema(connection)
    venue_statements = [statement for statement in connection.statements if "venue VARCHAR" in statement]

    assert len(venue_statements) == 2
    assert all("DEFAULT 'binance'" in statement for statement in venue_statements)
