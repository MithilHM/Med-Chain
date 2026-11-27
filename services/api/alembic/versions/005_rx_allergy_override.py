"""Record why a prescriber continued despite a matching allergy.

Revision ID: 005_rx_allergy_override
Revises: 004_accounts_allergies
Create Date: 2026-11-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_rx_allergy_override'
down_revision: Union[str, None] = '004_accounts_allergies'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('prescription', schema=None) as batch_op:
        batch_op.add_column(sa.Column('allergy_override_reason', sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('prescription', schema=None) as batch_op:
        batch_op.drop_column('allergy_override_reason')
