# models.py
# ────────────────────────────────────────────────────────────────
from sqlalchemy import (
    Column, Integer, BigInteger, Date, DateTime, Numeric,
    String, ForeignKey, UniqueConstraint, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

# -----------------------------------------------------------------
# Table items  ←  indispensable pour la FK item_id
# -----------------------------------------------------------------
class Item(Base):
    __tablename__ = "items"
    id   = Column(Integer, primary_key=True)
    name = Column(String)

# -----------------------------------------------------------------
# Table snapshots : toutes les stats quotidiennes par item
# -----------------------------------------------------------------
class Snapshot(Base):
    __tablename__ = "snapshots"
    id      = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    ts      = Column(Date, nullable=False)

    # Open / close
    open_buy_price   = Column(Integer)
    open_sell_price  = Column(Integer)
    close_buy_price  = Column(Integer)
    close_sell_price = Column(Integer)

    # Prix extrêmes / statistiques
    min_buy_price  = Column(Integer)
    max_buy_price  = Column(Integer)
    min_sell_price = Column(Integer)
    max_sell_price = Column(Integer)
    avg_buy_price  = Column(Integer)
    avg_sell_price = Column(Integer)
    median_buy_price  = Column(Integer)
    median_sell_price = Column(Integer)
    std_buy_price  = Column(Numeric(10, 2))
    std_sell_price = Column(Numeric(10, 2))

    # Spreads
    avg_spread = Column(Integer)
    min_spread = Column(Integer)
    max_spread = Column(Integer)
    pct_spread = Column(Numeric(6, 2))

    # Volatilité relative
    coef_var_buy = Column(Numeric(7, 4))

    # Étendue & ATR-like
    true_range = Column(Integer)
    delta_buy_price  = Column(Integer)
    delta_sell_price = Column(Integer)
    atr_like  = Column(Integer)

    # VWAP approximatifs
    vwap_buy  = Column(Integer)
    vwap_sell = Column(Integer)

    # Carnet & liquidité
    total_buy_qty_listed  = Column(BigInteger)
    total_sell_qty_listed = Column(BigInteger)
    exec_buy_qty  = Column(BigInteger)
    exec_sell_qty = Column(BigInteger)
    imbalance_qty     = Column(Integer)
    sell_through_rate = Column(Numeric(7, 4))
    buy_liquidity_ratio  = Column(Numeric(7, 4))
    sell_liquidity_ratio = Column(Numeric(7, 4))

    # Variations %
    pct_change_buy  = Column(Numeric(6, 2))
    pct_change_sell = Column(Numeric(6, 2))

# -----------------------------------------------------------------
# Table daily_raw  (brut 2 h)
# -----------------------------------------------------------------
class DailyRaw(Base):
    __tablename__ = "daily_raw"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    buy_price  = Column(Integer)
    buy_quantity  = Column(Integer)
    sell_price = Column(Integer)
    sell_quantity = Column(Integer)

    __table_args__ = (
        UniqueConstraint("item_id", "ts", name="uq_daily_item_time"),
    )

# -----------------------------------------------------------------
# Connexion & création auto
# -----------------------------------------------------------------
DATABASE_URL = "postgresql://postgres:test1234@localhost:5432/postgres"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

Base.metadata.create_all(engine)
