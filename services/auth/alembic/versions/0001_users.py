"""Table auth.users et vue annuaire auth.user_directory

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="auth",
    )
    op.create_index("ix_auth_users_email", "users", ["email"], unique=True, schema="auth")

    # Vue annuaire : la seule chose que l'API métier peut lire dans le schéma auth.
    # Pas de mot de passe, pas de date : uniquement ce qui sert à trouver un destinataire.
    op.execute("CREATE VIEW auth.user_directory AS SELECT id, email, name FROM auth.users")
    op.execute("GRANT SELECT ON auth.user_directory TO poupal_api")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS auth.user_directory")
    op.drop_index("ix_auth_users_email", table_name="users", schema="auth")
    op.drop_table("users", schema="auth")
