"""Add per-asset translations

Gives an asset a place to keep its second language. Purely additive and
nullable: the existing columns go on holding whatever the creator originally
typed, so every asset already in the database reads exactly as it did before
this ran, and there is nothing to backfill.

Revision ID: f3a9c1d5b7e2
Revises: e8b2c5f7a1d4
Create Date: 2026-08-17 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a9c1d5b7e2'
down_revision = 'e8b2c5f7a1d4'
branch_labels = None
depends_on = None


def _columns(conn, table):
    return [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info('{table}')"))]


def upgrade():
    conn = op.get_bind()

    asset_columns = _columns(conn, 'digital_asset')
    with op.batch_alter_table('digital_asset', schema=None) as batch_op:
        if 'translations' not in asset_columns:
            batch_op.add_column(sa.Column('translations', sa.JSON(), nullable=True))
        if 'primary_language' not in asset_columns:
            batch_op.add_column(sa.Column('primary_language', sa.String(length=5), nullable=True))

    if 'translations' not in _columns(conn, 'asset_file'):
        with op.batch_alter_table('asset_file', schema=None) as batch_op:
            batch_op.add_column(sa.Column('translations', sa.JSON(), nullable=True))


def downgrade():
    conn = op.get_bind()

    if 'translations' in _columns(conn, 'asset_file'):
        with op.batch_alter_table('asset_file', schema=None) as batch_op:
            batch_op.drop_column('translations')

    asset_columns = _columns(conn, 'digital_asset')
    with op.batch_alter_table('digital_asset', schema=None) as batch_op:
        if 'primary_language' in asset_columns:
            batch_op.drop_column('primary_language')
        if 'translations' in asset_columns:
            batch_op.drop_column('translations')
