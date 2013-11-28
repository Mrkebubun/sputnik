"""adding a two factor column to the User table

Revision ID: 253211359f84
Revises: 30258e7d6924
Create Date: 2013-09-21 17:33:09.795609

"""

# revision identifiers, used by Alembic.
revision = '253211359f84'
down_revision = '30258e7d6924'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('users', sa.Column('two_factor', sa.String(50), nullable=True))

def downgrade():
    op.drop_column('users', 'two_factor')
