# find_fast_flips.py (hybride snapshots + daily_raw du jour)
# ----------------------------------------------------------------
# Combine les stats de la veille (snapshots) avec les données du jour (daily_raw)
# pour détecter les flips rapides de manière plus actuelle.
# ----------------------------------------------------------------

from dotenv import load_dotenv
load_dotenv()
import os
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL n'est pas défini (ni dans .env, ni en variable d'environnement).")

from models import Session, Snapshot, DailyRaw, Item
from sqlalchemy import func
from tabulate import tabulate
import pandas as pd
import datetime

# Seuils recommandés
MAX_BUY_WAIT_RATIO = 1.5
MIN_SELL_SPEED     = 1000
MIN_NET_GAIN       = 15
MIN_SPREAD_PCT     = 10

def format_price(copper):
    if copper is None: return "-"
    po = copper // 10000
    pa = (copper % 10000) // 100
    pc = copper % 100
    return f"{po}p {pa:02}a {pc:02}c"

def find_fast_flips():
    today = datetime.date.today()

    with Session() as s:
        latest_ts = s.query(func.max(Snapshot.ts)).scalar()
        print(f"📅 Snapshot le plus récent : {latest_ts}")
        print(f"📊 Enrichissement avec daily_raw du {today} (en cours)\n")

        # --- DailyRaw du jour (agg intraday par item) ---
        today_data = {
            item_id: {
                "exec_sells": 0,
                "exec_buys": 0,
                "buy_qty": 0,
                "sell_qty": 0,
            }
            for (item_id,) in s.query(DailyRaw.item_id).filter(func.date(DailyRaw.ts) == today).distinct()
        }

        rows = s.query(DailyRaw).filter(func.date(DailyRaw.ts) == today).all()
        for row in rows:
            if row.item_id not in today_data:
                continue
            t = today_data[row.item_id]
            t["buy_qty"] += row.buy_quantity or 0
            t["sell_qty"] += row.sell_quantity or 0

        # on recalcule les exec_qty comme la ↓ d’un tick à l’autre
        for item_id in today_data:
            buy_diffs = []
            sell_diffs = []
            prev = None
            raw = s.query(DailyRaw).filter(DailyRaw.item_id == item_id, func.date(DailyRaw.ts) == today).order_by(DailyRaw.ts).all()
            for r in raw:
                if prev:
                    if prev.sell_quantity > r.sell_quantity:
                        buy_diffs.append(prev.sell_quantity - r.sell_quantity)
                    if prev.buy_quantity > r.buy_quantity:
                        sell_diffs.append(prev.buy_quantity - r.buy_quantity)
                prev = r
            today_data[item_id]["exec_sells"] = sum(buy_diffs)
            today_data[item_id]["exec_buys"] = sum(sell_diffs)

        # --- Snapshots de la veille (base des calculs) ---
        q = (
            s.query(Snapshot, Item.name)
            .join(Item, Snapshot.item_id == Item.id)
            .filter(Snapshot.ts == latest_ts)
            .filter(Snapshot.avg_buy_price.isnot(None),
                    Snapshot.avg_sell_price.isnot(None),
                    Snapshot.total_buy_qty_listed.isnot(None))
        )

        results = []
        for snap, name in q.all():
            item_id = snap.item_id
            extra = today_data.get(item_id, {})
            exec_sell_qty = extra.get("exec_sells", snap.exec_sell_qty)
            exec_buy_qty = extra.get("exec_buys", snap.exec_buy_qty)

            spread = snap.avg_sell_price - snap.avg_buy_price
            spread_pct = (spread * 100 / snap.avg_buy_price) if snap.avg_buy_price else 0
            net_gain = int(snap.avg_sell_price * 0.85) - snap.avg_buy_price

            buy_queue_ratio = (
                snap.total_buy_qty_listed / exec_sell_qty
                if exec_sell_qty else None
            )

            if (
                net_gain >= MIN_NET_GAIN and
                spread_pct >= MIN_SPREAD_PCT and
                buy_queue_ratio is not None and
                buy_queue_ratio <= MAX_BUY_WAIT_RATIO and
                exec_buy_qty >= MIN_SELL_SPEED
            ):
                results.append({
                    "Item ID": item_id,
                    "Nom": name,
                    "Achat": format_price(snap.avg_buy_price),
                    "Vente": format_price(snap.avg_sell_price),
                    "Gain Net": format_price(net_gain),
                    "Spread %": f"{spread_pct:6.2f}%",
                    "⏳ Attente": f"{buy_queue_ratio:>4.2f}j",
                    "Vendus (achat)": f"{exec_sell_qty:,}",
                    "Vendus (vente)": f"{exec_buy_qty:,}",
                })

        if not results:
            print("❌ Aucun flip rapide détecté.")
            return

        print("⚡ Objets à flip rapide :\n")
        print(tabulate(results, headers="keys", tablefmt="fancy_grid"))

if __name__ == "__main__":
    find_fast_flips()