"""created random salt column for users

Revision ID: 30258e7d6924
Revises: 550dfe04e996
Create Date: 2013-08-18 01:46:23.302661

"""

# revision identifiers, used by Alembic.
revision = '30258e7d6924'
down_revision = '550dfe04e996'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('users', sa.Column('salt', sa.String(50)))


def downgrade():
    op.drop_column('users', 'salt')
