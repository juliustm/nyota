"""Add customer language column

Revision ID: c7d2e3f4a5b6
Revises: b3f1a2c4d5e6
Create Date: 2026-02-24 11:38:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d2e3f4a5b6'
down_revision = 'b3f1a2c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    # Check if the column already exists (some databases may have it from
    # a previous ad-hoc migration that was later removed).
    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info('customer')"))
    columns = [row[1] for row in result]
    if 'language' not in columns:
        with op.batch_alter_table('customer', schema=None) as batch_op:
            batch_op.add_column(sa.Column('language', sa.String(length=5), nullable=True, server_default='en'))


def downgrade():
    with op.batch_alter_table('customer', schema=None) as batch_op:
        batch_op.drop_column('language')
