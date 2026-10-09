"""food usage (Actual Food Usage Recording, K14)

Revision ID: 9b4f2c7e1d63
Revises: 7d3e9a1c5b20
Create Date: 2026-10-09 16:30:00

Additive only: one new table.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b4f2c7e1d63'
down_revision = '7d3e9a1c5b20'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('food_usage',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('menu_item_id', sa.Integer(), nullable=False),
    sa.Column('usage_date', sa.Date(), nullable=False),
    sa.Column('usage_type', sa.String(length=20), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('outlet_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_food_usage_qty')),
    sa.CheckConstraint("usage_type IN ('staff_meal', 'complimentary', 'sample', 'other')", name=op.f('ck_food_usage_usage_type')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_food_usage_created_by_users')),
    sa.ForeignKeyConstraint(['menu_item_id'], ['menu_items.id'], name=op.f('fk_food_usage_menu_item_id_menu_items')),
    sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id'], name=op.f('fk_food_usage_outlet_id_outlets')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_food_usage')),
    sa.UniqueConstraint('outlet_id', 'menu_item_id', 'usage_date', 'usage_type', name='uq_food_usage_item_day_type')
    )
    with op.batch_alter_table('food_usage', schema=None) as batch_op:
        batch_op.create_index('ix_food_usage_date', ['outlet_id', 'usage_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_food_usage_outlet_id'), ['outlet_id'], unique=False)


def downgrade():
    with op.batch_alter_table('food_usage', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_food_usage_outlet_id'))
        batch_op.drop_index('ix_food_usage_date')
    op.drop_table('food_usage')
