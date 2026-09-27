"""rescues.category: "general" for every rescue; food type no longer plays a part anywhere

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = "category IN ('general', 'hot', 'cold', 'frozen', 'shelf_stable')"
OLD = "category IN ('hot', 'cold', 'frozen', 'shelf_stable')"


def upgrade() -> None:
    with op.batch_alter_table('rescues', schema=None) as batch_op:
        batch_op.drop_constraint('ck_rescue_category', type_='check')
        batch_op.create_check_constraint('ck_rescue_category', NEW)
    op.execute("UPDATE rescues SET category = 'general'")


def downgrade() -> None:
    op.execute("UPDATE rescues SET category = 'shelf_stable' WHERE category = 'general'")
    with op.batch_alter_table('rescues', schema=None) as batch_op:
        batch_op.drop_constraint('ck_rescue_category', type_='check')
        batch_op.create_check_constraint('ck_rescue_category', OLD)
