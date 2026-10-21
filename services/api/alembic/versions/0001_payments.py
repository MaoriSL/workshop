"""Schéma payments : comptes, transactions, clés d'idempotence

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

transaction_status = postgresql.ENUM("completed", "failed", "pending", name="transaction_status", schema="payments", create_type=False)


def upgrade() -> None:
    transaction_status.create(op.get_bind(), checkfirst=True)

    # Séquence des références lisibles (PP-2026-000001, ...)
    op.execute("CREATE SEQUENCE IF NOT EXISTS payments.transaction_reference_seq START 1")

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("balance_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("opening_balance_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("balance_cents >= 0", name="ck_accounts_balance_non_negative"),
        schema="payments",
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("reference", sa.String(20), nullable=False, unique=True),
        sa.Column("sender_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.accounts.id"), nullable=False),
        sa.Column("recipient_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.accounts.id"), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("status", transaction_status, nullable=False),
        sa.Column("failure_reason", sa.String(64), nullable=True),
        sa.Column("message", sa.String(140), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_transactions_amount_positive"),
        schema="payments",
    )
    op.create_index("ix_payments_transactions_sender", "transactions", ["sender_account_id"], schema="payments")
    op.create_index("ix_payments_transactions_recipient", "transactions", ["recipient_account_id"], schema="payments")
    op.create_index("ix_payments_transactions_created_at", "transactions", ["created_at"], schema="payments")

    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.transactions.id"), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="payments",
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema="payments")
    op.drop_index("ix_payments_transactions_created_at", table_name="transactions", schema="payments")
    op.drop_index("ix_payments_transactions_recipient", table_name="transactions", schema="payments")
    op.drop_index("ix_payments_transactions_sender", table_name="transactions", schema="payments")
    op.drop_table("transactions", schema="payments")
    op.drop_table("accounts", schema="payments")
    op.execute("DROP SEQUENCE IF EXISTS payments.transaction_reference_seq")
    transaction_status.drop(op.get_bind(), checkfirst=True)
