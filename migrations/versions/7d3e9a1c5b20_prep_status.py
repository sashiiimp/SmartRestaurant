"""preparation workflow on recommendations (Food Preparation Management, K4)

Revision ID: 7d3e9a1c5b20
Revises: 4c1e5e7a9b2d
Create Date: 2026-10-09 16:00:00

Additive only: four nullable/defaulted columns and one CHECK. Existing decisions become `planned`.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7d3e9a1c5b20'
down_revision = '4c1e5e7a9b2d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prep_status', sa.String(length=20), nullable=False, server_default='planned'))
        batch_op.add_column(sa.Column('prep_started_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('prep_done_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('prep_done_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_recommendations_prep_done_by_users'), 'users', ['prep_done_by'], ['id'])
        batch_op.create_check_constraint(batch_op.f('ck_recommendations_prep_status'), "prep_status IN ('planned', 'in_progress', 'done')")


def downgrade():
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('ck_recommendations_prep_status'), type_='check')
        batch_op.drop_constraint(batch_op.f('fk_recommendations_prep_done_by_users'), type_='foreignkey')
        batch_op.drop_column('prep_done_by')
        batch_op.drop_column('prep_done_at')
        batch_op.drop_column('prep_started_at')
        batch_op.drop_column('prep_status')
