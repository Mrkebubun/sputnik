"""tweak FuturesContract

Revision ID: 3187ef2367e9
Revises: 4659e9d1d318
Create Date: 2013-06-27 14:20:15.263572

"""

# revision identifiers, used by Alembic.
revision = '3187ef2367e9'
down_revision = '4659e9d1d318'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('futures', 'multiplier',nullable=False,server_default="1",type_=sa.BigInteger)



def downgrade():
    op.alter_column('futures', 'multiplier',nullable=True,type_=sa.Integer)
