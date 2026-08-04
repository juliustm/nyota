"""Add customer saved_delivery column

Revision ID: e8b2c5f7a1d4
Revises: d1f4a7c9e2b3
Create Date: 2026-07-13 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8b2c5f7a1d4'
down_revision = 'd1f4a7c9e2b3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info('customer')"))
    columns = [row[1] for row in result]
    if 'saved_delivery' not in columns:
        with op.batch_alter_table('customer', schema=None) as batch_op:
            batch_op.add_column(sa.Column('saved_delivery', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('customer', schema=None) as batch_op:
        batch_op.drop_column('saved_delivery')
