#!/usr/bin/env python3
"""Importe scraped_trends/*.json → tables items & daily_raw (ORM models.py)."""

import argparse, json
from dotenv import load_dotenv

load_dotenv()
import os
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL n'est pas défini (ni dans .env, ni en variable d'environnement).")
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from models import engine, Item, DailyRaw   # ← ton fichier models.py

# ────── paramètres CLI ───────────────────────────────────────────────────────
p = argparse.ArgumentParser()
p.add_argument("--dir",   default="scraped_trends", help="dossier .json")
p.add_argument("--batch", default=10_000, type=int, help="taille batch")
args = p.parse_args()
DATA_DIR = Path(args.dir)
assert DATA_DIR.exists(), f"{DATA_DIR} introuvable"

# ────── helpers ──────────────────────────────────────────────────────────────
def parse_ts(ts: str) -> datetime:      # « 2025-01-05T00:00:01.000Z » → naïf
    return datetime.fromisoformat(ts.replace("Z", ""))   # pas de TZ → ts « naive »

def ensure_items(sess: Session, ids: set[int]):
    existing = {i for (i,) in sess.execute(select(Item.id).where(Item.id.in_(ids)))}
    missing  = ids - existing
    if missing:
        sess.bulk_save_objects([Item(id=i, name=f"item_{i}") for i in missing])
        sess.flush()     # pas commit ici – commit à la fin du fichier

def flush(sess: Session, buf: list[dict]):
    if not buf:
        return
    stmt = (
        pg_insert(DailyRaw)
        .values(buf)
        .on_conflict_do_nothing(index_elements=["item_id", "ts"])
    )
    sess.execute(stmt)

# ────── import ───────────────────────────────────────────────────────────────
files = sorted(DATA_DIR.glob("*.json"))
print(f"{len(files)} fichiers à importer…")

with Session(engine) as sess:
    for jf in files:
        data = json.loads(jf.read_text())
        if not data:
            print(f"⚠️  {jf.name} vide – ignoré"); continue

        ensure_items(sess, {int(r["item_id"]) for r in data})

        batch = []
        for r in data:
            batch.append(
                dict(
                    item_id       = int(r["item_id"]),
                    ts            = parse_ts(r["ts"]),
                    buy_price     = int(r["buy_price"]),
                    buy_quantity  = int(r["buy_qty"]),
                    sell_price    = int(r["sell_price"]),
                    sell_quantity = int(r["sell_qty"]),
                )
            )
            if len(batch) >= args.batch:
                flush(sess, batch); batch.clear()

        flush(sess, batch)
        sess.commit()
        print(f"✅ {jf.name}  ({len(data)} lignes)")

print("🎉  Import terminé – lance aggregate_daily.py pour snapshots.")
