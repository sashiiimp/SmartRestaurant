"""pre-order customer details, pickup time and the completed status (Preorder Management, K10)

Revision ID: c4e1a7b9d052
Revises: 9b4f2c7e1d63
Create Date: 2026-10-13 15:00:00

Additive only: four nullable columns, and the status CHECK also allows 'completed'. Existing pre-orders keep their
values (the new columns stay empty). The downgrade turns completed pre-orders back into confirmed ones, because the
old CHECK does not allow 'completed', and drops the four columns with their values.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e1a7b9d052'
down_revision = '9b4f2c7e1d63'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pre_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('customer_name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('customer_contact', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('pickup_time', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(), nullable=True))
        batch_op.drop_constraint(batch_op.f('ck_pre_orders_status'), type_='check')
        batch_op.create_check_constraint(batch_op.f('ck_pre_orders_status'),
                                         "status IN ('pending', 'confirmed', 'completed', 'cancelled')")


def downgrade():
    op.execute("UPDATE pre_orders SET status = 'confirmed' WHERE status = 'completed'")
    with op.batch_alter_table('pre_orders', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('ck_pre_orders_status'), type_='check')
        batch_op.create_check_constraint(batch_op.f('ck_pre_orders_status'), "status IN ('pending', 'confirmed', 'cancelled')")
        batch_op.drop_column('completed_at')
        batch_op.drop_column('pickup_time')
        batch_op.drop_column('customer_contact')
        batch_op.drop_column('customer_name')
