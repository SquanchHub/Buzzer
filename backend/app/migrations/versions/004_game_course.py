"""Attach each game to one course (games.course_id)

Revision ID: 004
Revises: 003
Create Date: 2026-10-01

Backfill rule: a game gets a course only when every one of its sessions was
played in the same course. Games with no sessions, or sessions in several
courses, stay NULL ("unassigned") until an admin assigns one.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("games", sa.Column("course_id", sa.Integer(), nullable=True))
    op.create_index("ix_games_course_id", "games", ["course_id"])
    op.create_foreign_key(
        "fk_games_course_id",
        "games",
        "courses",
        ["course_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # MySQL rejects an UPDATE whose subquery reads the target table, but this
    # one reads only game_sessions, so a correlated subquery is fine.
    op.execute(
        """
        UPDATE games g
        SET g.course_id = (
            SELECT MIN(s.course_id) FROM game_sessions s WHERE s.game_id = g.id
        )
        WHERE (
            SELECT COUNT(DISTINCT s.course_id)
            FROM game_sessions s
            WHERE s.game_id = g.id
        ) = 1
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_games_course_id", "games", type_="foreignkey")
    op.drop_index("ix_games_course_id", table_name="games")
    op.drop_column("games", "course_id")
