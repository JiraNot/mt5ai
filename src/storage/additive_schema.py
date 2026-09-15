"""Small idempotent migrations for additive columns on existing databases."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def ensure_additive_schema(connection: AsyncConnection) -> None:
    """Add venue/order identity columns without dropping existing journal data."""
    statements = (
        "ALTER TABLE setup_log ADD COLUMN venue VARCHAR(20) NOT NULL DEFAULT 'mt5'",
        "ALTER TABLE trades ADD COLUMN venue VARCHAR(20) NOT NULL DEFAULT 'mt5'",
        "ALTER TABLE trades ADD COLUMN external_order_id VARCHAR(100)",
        "ALTER TABLE trades ADD COLUMN execution_key VARCHAR(150)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_execution_key ON trades(execution_key) WHERE execution_key IS NOT NULL",
    )
    for statement in statements:
        try:
            await connection.execute(text(statement))
        except Exception as exc:
            # Existing columns are expected on every subsequent startup. Do
            # not hide an actual startup failure from the caller.
            message = str(exc).lower()
            if "duplicate column" not in message and "already exists" not in message:
                raise
