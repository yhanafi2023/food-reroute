"""users.supabase_user_id: the linked Supabase Auth user (app/supabase_auth.py)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('supabase_user_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_supabase_user_id'), ['supabase_user_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_supabase_user_id'))
        batch_op.drop_column('supabase_user_id')
