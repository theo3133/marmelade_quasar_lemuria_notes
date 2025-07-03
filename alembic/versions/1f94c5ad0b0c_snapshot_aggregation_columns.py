from alembic import op
import sqlalchemy as sa

# révision / dépendance
revision = "XXXXXXXXXX"
down_revision = "UUID_de_la_revision_précédente"
branch_labels = None
depends_on = None

def upgrade():
    # ⚠️ rename d’anciennes colonnes -> nouvelles
    op.alter_column("snapshots", "buy_price",  new_column_name="avg_buy_price")
    op.alter_column("snapshots", "sell_price", new_column_name="avg_sell_price")

    # on n’a plus besoin des anciennes qty brutes : on les renomme ou on garde
    op.alter_column("snapshots", "buy_quantity",  new_column_name="total_buy_qty_listed")
    op.alter_column("snapshots", "sell_quantity", new_column_name="total_sell_qty_listed")

    # nouvelles colonnes
    op.add_column("snapshots", sa.Column("delta_buy_price",  sa.Integer()))
    op.add_column("snapshots", sa.Column("delta_sell_price", sa.Integer()))
    op.add_column("snapshots", sa.Column("exec_buy_qty",    sa.Integer()))
    op.add_column("snapshots", sa.Column("exec_sell_qty",   sa.Integer()))

def downgrade():
    op.drop_column("snapshots", "exec_sell_qty")
    op.drop_column("snapshots", "exec_buy_qty")
    op.drop_column("snapshots", "delta_sell_price")
    op.drop_column("snapshots", "delta_buy_price")

    op.alter_column("snapshots", "total_sell_qty_listed", new_column_name="sell_quantity")
    op.alter_column("snapshots", "total_buy_qty_listed",  new_column_name="buy_quantity")
    op.alter_column("snapshots", "avg_sell_price", new_column_name="sell_price")
    op.alter_column("snapshots", "avg_buy_price",  new_column_name="buy_price")
