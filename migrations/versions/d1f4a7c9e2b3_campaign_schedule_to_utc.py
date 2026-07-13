"""Convert existing campaign schedule times from creator-local to UTC

Scheduled campaigns used to store whatever wall-clock string the admin's
datetime-local picker produced, while the background worker compares against
datetime.utcnow() — so a campaign set for 09:00 in Dar es Salaam fired at
12:00 local. Schedules are now stored in UTC; shift the rows that predate that.

Revision ID: d1f4a7c9e2b3
Revises: 9e285ad86707
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa
import json
from datetime import datetime
from zoneinfo import ZoneInfo

# revision identifiers, used by Alembic.
revision = 'd1f4a7c9e2b3'
down_revision = '9e285ad86707'
branch_labels = None
depends_on = None

DEFAULT_TZ = 'Africa/Nairobi'
UTC = ZoneInfo('UTC')


def _creator_zones(conn):
    rows = conn.execute(sa.text(
        "SELECT creator_id, value FROM creator_setting WHERE key = 'creator_timezone'"
    )).fetchall()
    zones = {}
    for creator_id, value in rows:
        # creator_setting.value is a JSON column, so raw SQL hands back '"Africa/..."'
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            pass
        try:
            zones[creator_id] = ZoneInfo(value)
        except Exception:
            zones[creator_id] = ZoneInfo(DEFAULT_TZ)
    return zones


def _shift(reverse=False):
    conn = op.get_bind()
    zones = _creator_zones(conn)
    default_zone = ZoneInfo(DEFAULT_TZ)

    rows = conn.execute(sa.text(
        "SELECT id, creator_id, scheduled_at, next_run_at FROM sms_campaign "
        "WHERE scheduled_at IS NOT NULL OR next_run_at IS NOT NULL"
    )).fetchall()

    for row in rows:
        tz = zones.get(row.creator_id, default_zone)

        def convert(dt):
            if dt is None:
                return None
            if isinstance(dt, str):  # SQLite hands back strings
                dt = datetime.fromisoformat(dt)
            if reverse:  # UTC -> creator wall-clock
                return dt.replace(tzinfo=UTC).astimezone(tz).replace(tzinfo=None)
            return dt.replace(tzinfo=tz).astimezone(UTC).replace(tzinfo=None)

        conn.execute(
            sa.text("UPDATE sms_campaign SET scheduled_at = :s, next_run_at = :n WHERE id = :i"),
            {
                's': convert(row.scheduled_at),
                'n': convert(row.next_run_at) or convert(row.scheduled_at),
                'i': row.id,
            },
        )


def upgrade():
    _shift(reverse=False)


def downgrade():
    _shift(reverse=True)
