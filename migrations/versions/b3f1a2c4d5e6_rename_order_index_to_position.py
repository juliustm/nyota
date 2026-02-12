"""rename order_index to position

Revision ID: b3f1a2c4d5e6
Revises: 6242fa5c4b84
Create Date: 2026-02-12 12:53:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f1a2c4d5e6'
down_revision = '6242fa5c4b84'
branch_labels = None
depends_on = None


def upgrade():
    # Safety check: only rename if 'order_index' exists (i.e. the DB was
    # created before the initial migration was consolidated to use 'position').
    conn = op.get_bind()
    columns = [col['name'] for col in sa.inspect(conn).get_columns('asset_file')]

    if 'order_index' in columns and 'position' not in columns:
        with op.batch_alter_table('asset_file', schema=None) as batch_op:
            batch_op.alter_column('order_index', new_column_name='position')
    elif 'order_index' not in columns and 'position' not in columns:
        # Neither column exists (shouldn't happen, but handle defensively)
        with op.batch_alter_table('asset_file', schema=None) as batch_op:
            batch_op.add_column(sa.Column('position', sa.Integer(), nullable=True))
    # else: 'position' already exists — nothing to do (fresh install)


def downgrade():
    with op.batch_alter_table('asset_file', schema=None) as batch_op:
        batch_op.alter_column('position', new_column_name='order_index')
