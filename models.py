from sqlalchemy import Column, Integer, String, create_engine, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.schema import UniqueConstraint

Base = declarative_base()

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    buy_price = Column(Integer)
    buy_quantity = Column(Integer)
    sell_price = Column(Integer)
    sell_quantity = Column(Integer)
    __table_args__ = (
        UniqueConstraint("item_id", "ts", name="uq_item_time"),
    )
class DailyRaw(Base):
    __tablename__ = "daily_raw"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    ts = Column(DateTime, nullable=False)
    buy_price = Column(Integer)
    buy_quantity = Column(Integer)
    sell_price = Column(Integer)
    sell_quantity = Column(Integer)

    __table_args__ = (
        UniqueConstraint("item_id", "ts", name="uq_daily_item_time"),
    )

# Base de données
DATABASE_URL = "postgresql://postgres:test1234@localhost:5432/postgres"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# Création automatique des tables si elles n'existent pas
Base.metadata.create_all(engine)
