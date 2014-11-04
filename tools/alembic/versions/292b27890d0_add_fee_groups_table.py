"""Add fee groups table, link users to fee groups, add fees column to contracts table

Revision ID: 292b27890d0
Revises: None
Create Date: 2014-10-31 13:44:27.827894

"""

# revision identifiers, used by Alembic.
revision = '292b27890d0'
down_revision = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('fee_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('aggressive_factor', sa.Integer(), server_default='100', nullable=False),
    sa.Column('passive_factor', sa.Integer(), server_default='100', nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sqlite_autoincrement=True
    )
    op.add_column(u'contracts', sa.Column('fees', sa.BigInteger(), server_default='100', nullable=False))
    op.alter_column(u'positions', 'pending_postings',
               existing_type=sa.BIGINT(),
               nullable='False',
               existing_server_default='0::bigint')
    op.add_column(u'users', sa.Column('fee_group_id', sa.Integer(), server_default='1', nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column(u'users', 'fee_group_id')
    op.alter_column(u'positions', 'pending_postings',
               existing_type=sa.BIGINT(),
               nullable=True,
               existing_server_default='0::bigint')
    op.drop_column(u'contracts', 'fees')
    op.drop_table('fee_groups')
    ### end Alembic commands ###
