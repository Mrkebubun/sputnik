"""enrich contract table

Revision ID: 4659e9d1d318
Revises: None
Create Date: 2013-06-27 13:00:31.920898

"""

# revision identifiers, used by Alembic.
from dns import name

revision = '4659e9d1d318'
down_revision = None

from alembic import op
import sqlalchemy as sa

enum_type = sa.Enum('futures', 'prediction', name='contract_types')

def upgrade():

    enum_type.create(op.get_bind())
    op.add_column('contracts', sa.Column('active', sa.Boolean, nullable=False, server_default="true"))
    op.add_column('contracts', sa.Column('contract_type', enum_type, server_default='futures', nullable=False))
    op.add_column('contracts', sa.Column('full_description', sa.String))
    op.create_unique_constraint(None, 'contracts', ['ticker'])

def downgrade():
    op.drop_column('contracts', 'active')
    op.drop_column('contracts', 'contract_type')
    op.drop_column('contracts', 'full_description')
    op.drop_constraint('contracts_ticker_key')
    enum_type.drop(op.get_bind())


