"""Store question images in the database (images, questions.prompt_image_id)

Revision ID: 005
Revises: 004
Create Date: 2026-10-05

T8 (docs/plans/t8-image-support.md D1, D5): each image belongs to one course
and its bytes never change under an ID. A question's prompt image is a real
column so the database refuses to delete a referenced one; option and hotspot
images live in questions.config.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey(
                "courses.id", name="fk_images_course_id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("data", mysql.MEDIUMBLOB(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "uploaded_by",
            sa.String(36),
            sa.ForeignKey(
                "users.id", name="fk_images_uploaded_by", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("course_id", "sha256", name="uq_images_course_sha256"),
    )
    op.create_index("ix_images_course_id", "images", ["course_id"])

    op.add_column(
        "questions", sa.Column("prompt_image_id", sa.Integer(), nullable=True)
    )
    op.create_index("ix_questions_prompt_image_id", "questions", ["prompt_image_id"])
    op.create_foreign_key(
        "fk_questions_prompt_image_id",
        "questions",
        "images",
        ["prompt_image_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_questions_prompt_image_id", "questions", type_="foreignkey")
    op.drop_index("ix_questions_prompt_image_id", table_name="questions")
    op.drop_column("questions", "prompt_image_id")
    op.drop_index("ix_images_course_id", table_name="images")
    op.drop_table("images")
