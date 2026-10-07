"""Serialize owner writes with explicit privacy deletion lifecycle."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p9_owner_privacy_lifecycle"
down_revision: str | None = "p9_identity_privacy_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_privacy_lifecycle",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('active', 'purging', 'purged')", name="ck_owner_lifecycle_state"
        ),
        sa.PrimaryKeyConstraint("owner_id"),
    )
    op.execute(
        """
        CREATE FUNCTION shopping_guard_owner_write() RETURNS trigger AS $$
        DECLARE owner_state varchar(16);
        BEGIN
            IF TG_OP = 'UPDATE' AND OLD.owner_id IS DISTINCT FROM NEW.owner_id THEN
                RAISE EXCEPTION 'owner identity is immutable' USING ERRCODE = '55000';
            END IF;
            INSERT INTO owner_privacy_lifecycle (owner_id, state)
                VALUES (NEW.owner_id, 'active') ON CONFLICT (owner_id) DO NOTHING;
            SELECT state INTO owner_state FROM owner_privacy_lifecycle
                WHERE owner_id = NEW.owner_id FOR SHARE;
            IF owner_state <> 'active' THEN
                RAISE EXCEPTION 'owner data is unavailable during privacy deletion'
                    USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        DO $$
        DECLARE owned_table record;
        BEGIN
            FOR owned_table IN
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND column_name = 'owner_id'
                  AND table_name NOT IN (
                      'firebase_owner_bindings', 'owner_privacy_events',
                      'owner_privacy_lifecycle'
                  )
                GROUP BY table_name
            LOOP
                EXECUTE format(
                    'CREATE TRIGGER shopping_owner_write_guard '
                    'BEFORE INSERT OR UPDATE ON %I '
                    'FOR EACH ROW EXECUTE FUNCTION shopping_guard_owner_write()',
                    owned_table.table_name
                );
            END LOOP;
        END;
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE owned_table record;
        BEGIN
            FOR owned_table IN
                SELECT event_object_table AS table_name
                FROM information_schema.triggers
                WHERE trigger_schema = current_schema()
                  AND trigger_name = 'shopping_owner_write_guard'
            LOOP
                EXECUTE format(
                    'DROP TRIGGER IF EXISTS shopping_owner_write_guard ON %I',
                    owned_table.table_name
                );
            END LOOP;
        END;
        $$
        """
    )
    op.execute("DROP FUNCTION shopping_guard_owner_write()")
    op.drop_table("owner_privacy_lifecycle")
