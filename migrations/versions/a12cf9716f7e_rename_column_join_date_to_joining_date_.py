"""Rename column 'join_date' to 'joining_date' in 'employee' table

Revision ID: a12cf9716f7e
Revises: 0e920f4f1e01
Create Date: 2024-07-27 21:47:26.238799

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a12cf9716f7e'
down_revision = '0e920f4f1e01'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('employee', schema=None) as batch_op:
        batch_op.add_column(sa.Column('joining_date', sa.Date(), nullable=True))
        batch_op.drop_column('join_date')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('employee', schema=None) as batch_op:
        batch_op.add_column(sa.Column('join_date', sa.DATE(), nullable=True))
        batch_op.drop_column('joining_date')

    # ### end Alembic commands ###