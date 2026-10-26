"""Outbox criptografada; rollback permitido somente sem tarefas armazenadas."""

from alembic import op
import sqlalchemy as sa

revision = "0002_outbox"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "challenge_id",
            sa.Text(),
            sa.ForeignKey("email_challenges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.Float(precision=53), nullable=False),
        sa.Column("lease_until", sa.Float(precision=53)),
        sa.Column("lease_token", sa.Text()),
        sa.Column("expires_at", sa.Float(precision=53), nullable=False),
        sa.Column("created_at", sa.Float(precision=53), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','sending','sent','cancelled','failed')"
        ),
        sa.CheckConstraint("attempts >= 0"),
    )
    op.create_index(
        "idx_outbox_due", "email_outbox", ["status", "available_at", "expires_at"]
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM email_outbox")).scalar():
        raise RuntimeError(
            "Rollback recusado: preserve/arquive a outbox antes de removê-la."
        )
    op.drop_index("idx_outbox_due", table_name="email_outbox")
    op.drop_table("email_outbox")
