"""session version on users (ends sessions on logout and password reset)

Revision ID: 4c1e5e7a9b2d
Revises: 165b04a3da7c
Create Date: 2026-10-04 16:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4c1e5e7a9b2d'
down_revision = '165b04a3da7c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_version', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('session_version')
