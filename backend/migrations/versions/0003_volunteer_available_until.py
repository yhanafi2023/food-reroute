"""volunteer_profiles.available_until: "I'm free now", on top of the weekly schedule

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('volunteer_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('available_until', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('volunteer_profiles', schema=None) as batch_op:
        batch_op.drop_column('available_until')
