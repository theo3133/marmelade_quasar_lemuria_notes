# trading/aggregate_daily.py
# ------------------------------------------------------------------
# Agrège chaque journée complète dans daily_raw, calcule toutes les
# statistiques (prix, spreads, volumes, ratios) — y compris :
#   pct_spread, coef_var_buy, true_range, vwap_buy/vwap_sell,
#   imbalance_qty, sell_through_rate, atr_like.
# Si l'item n'existe pas dans la table items, on appelle l’API GW2
# pour récupérer son nom (en anglais) et on l’insère automatiquement,
# puis on upsert dans snapshots et on purge le brut.
# ------------------------------------------------------------------

import datetime
import os
from dotenv import load_dotenv

load_dotenv()
import os
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL n'est pas défini (ni dans .env, ni en variable d'environnement).")
import requests                       # ← nouveau
from sqlalchemy import select, func, case, BigInteger
from models import Session, DailyRaw, Snapshot, Item


# ------------------------------------------------------------------
# Récupère le nom officiel d’un item (API GW2, langue « en »)
# ------------------------------------------------------------------
def fetch_item_name(item_id: int) -> str | None:
    url = f"https://api.guildwars2.com/v2/items/{item_id}?lang=en"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json().get("name")
    except Exception:
        return None


def aggregate_all_days() -> None:
    today = datetime.date.today()

    with Session() as s:
        # ── jours complets (≤ hier) encore présents dans daily_raw ───────
        days = [
            d for (d,) in
            s.query(func.date(DailyRaw.ts))
             .filter(func.date(DailyRaw.ts) < today)
             .group_by(func.date(DailyRaw.ts))
        ]
        if not days:
            print("👍 Rien à agréger.")
            return

        for day in days:
            print(f"📊 Agrégation du {day} …")

            # ========= CTE 1 : snapshots + LAG des quantités =============
            lagged = (
                select(
                    DailyRaw.item_id, DailyRaw.ts,
                    DailyRaw.buy_price, DailyRaw.sell_price,
                    DailyRaw.buy_quantity, DailyRaw.sell_quantity,
                    func.lag(DailyRaw.buy_quantity)
                        .over(partition_by=DailyRaw.item_id,
                              order_by=DailyRaw.ts).label("prev_buy_qty"),
                    func.lag(DailyRaw.sell_quantity)
                        .over(partition_by=DailyRaw.item_id,
                              order_by=DailyRaw.ts).label("prev_sell_qty"),
                )
                .where(func.date(DailyRaw.ts) == day)
                .cte("lagged")
            )

            # ========= CTE 2 : calcul de toutes les fenêtres =============
            w = lagged.alias()

            with_windows = (
                select(
                    w.c.item_id, w.c.ts,
                    w.c.buy_price, w.c.sell_price,
                    w.c.buy_quantity, w.c.sell_quantity,
                    w.c.prev_buy_qty, w.c.prev_sell_qty,

                    func.first_value(w.c.buy_price)
                        .over(partition_by=w.c.item_id,
                              order_by=w.c.ts).label("open_buy"),
                    func.first_value(w.c.sell_price)
                        .over(partition_by=w.c.item_id,
                              order_by=w.c.ts).label("open_sell"),

                    func.last_value(w.c.buy_price)
                        .over(partition_by=w.c.item_id,
                              order_by=w.c.ts,
                              rows=(None, None)).label("close_buy"),
                    func.last_value(w.c.sell_price)
                        .over(partition_by=w.c.item_id,
                              order_by=w.c.ts,
                              rows=(None, None)).label("close_sell"),

                    (w.c.sell_price - w.c.buy_price).label("spread"),

                    case(
                        (w.c.prev_sell_qty > w.c.sell_quantity,
                         w.c.prev_sell_qty - w.c.sell_quantity), else_=0
                    ).label("delta_exec_buy"),
                    case(
                        (w.c.prev_buy_qty > w.c.buy_quantity,
                         w.c.prev_buy_qty - w.c.buy_quantity), else_=0
                    ).label("delta_exec_sell"),
                )
            ).cte("with_windows")

            # ========= SELECT final : uniquement des agrégats ============
            z = with_windows.alias()

            rows = s.execute(
                select(
                    z.c.item_id,

                    func.min(z.c.open_buy).label("open_buy"),
                    func.min(z.c.open_sell).label("open_sell"),
                    func.max(z.c.close_buy).label("close_buy"),
                    func.max(z.c.close_sell).label("close_sell"),

                    func.min(z.c.buy_price).label("min_buy"),
                    func.max(z.c.buy_price).label("max_buy"),
                    func.min(z.c.sell_price).label("min_sell"),
                    func.max(z.c.sell_price).label("max_sell"),

                    func.avg(z.c.buy_price).label("avg_buy"),
                    func.avg(z.c.sell_price).label("avg_sell"),

                    func.percentile_cont(0.5).within_group(
                        z.c.buy_price).label("median_buy"),
                    func.percentile_cont(0.5).within_group(
                        z.c.sell_price).label("median_sell"),

                    func.stddev_pop(z.c.buy_price).label("std_buy"),
                    func.stddev_pop(z.c.sell_price).label("std_sell"),

                    func.avg(z.c.spread).label("avg_spread"),
                    func.min(z.c.spread).label("min_spread"),
                    func.max(z.c.spread).label("max_spread"),

                    (func.max(z.c.buy_price) - func.min(z.c.buy_price)).label("delta_buy"),
                    (func.max(z.c.sell_price) - func.min(z.c.sell_price)).label("delta_sell"),

                    func.sum(z.c.buy_quantity).label("tot_buy_listed"),
                    func.sum(z.c.sell_quantity).label("tot_sell_listed"),
                    func.sum(z.c.delta_exec_buy.cast(BigInteger)).label("exec_buy_qty"),
                    func.sum(z.c.delta_exec_sell.cast(BigInteger)).label("exec_sell_qty"),
                )
                .group_by(z.c.item_id)
            ).fetchall()

            # ========= insertion / merge dans snapshots ===================
            ts0 = datetime.datetime.combine(day, datetime.time())

            for r in rows:
                # 0) créer l'item s'il n'existe pas (nom réel ou placeholder)
                if not s.get(Item, r.item_id):
                    real_name = fetch_item_name(r.item_id) or f"auto_{r.item_id}"
                    s.add(Item(id=r.item_id, name=real_name))
                    s.flush()  # FK OK

                # ratios simples
                pct_buy  = ((r.close_buy  - r.open_buy)  * 100 / r.open_buy)  if r.open_buy  else None
                pct_sell = ((r.close_sell - r.open_sell) * 100 / r.open_sell) if r.open_sell else None
                buy_liq  = (r.exec_sell_qty / r.tot_sell_listed) if r.tot_sell_listed else None
                sell_liq = (r.exec_buy_qty  / r.tot_buy_listed)  if r.tot_buy_listed  else None

                # métriques dérivées
                pct_spread       = (r.avg_spread * 100 / r.avg_sell) if r.avg_sell else None
                coef_var_buy     = (r.std_buy / r.avg_buy) if r.avg_buy else None
                true_range       = r.max_sell - r.min_buy
                vwap_buy         = int(r.avg_buy)
                vwap_sell        = int(r.avg_sell)
                imbalance_qty    = r.tot_buy_listed - r.tot_sell_listed
                sell_through_rate = (r.exec_sell_qty / (r.exec_sell_qty + r.tot_sell_listed)
                                     if (r.exec_sell_qty + r.tot_sell_listed) else None)
                atr_like         = r.delta_buy + r.delta_sell

                s.merge(Snapshot(
                    item_id = r.item_id, ts = ts0,

                    open_buy_price   = r.open_buy,
                    open_sell_price  = r.open_sell,
                    close_buy_price  = r.close_buy,
                    close_sell_price = r.close_sell,

                    min_buy_price  = r.min_buy,
                    max_buy_price  = r.max_buy,
                    min_sell_price = r.min_sell,
                    max_sell_price = r.max_sell,

                    avg_buy_price  = int(r.avg_buy),
                    avg_sell_price = int(r.avg_sell),
                    median_buy_price  = int(r.median_buy),
                    median_sell_price = int(r.median_sell),
                    std_buy_price = r.std_buy,
                    std_sell_price = r.std_sell,

                    avg_spread = int(r.avg_spread),
                    min_spread = r.min_spread,
                    max_spread = r.max_spread,

                    delta_buy_price = r.delta_buy,
                    delta_sell_price = r.delta_sell,
                    pct_change_buy  = pct_buy,
                    pct_change_sell = pct_sell,

                    total_buy_qty_listed  = r.tot_buy_listed,
                    total_sell_qty_listed = r.tot_sell_listed,
                    exec_buy_qty = r.exec_buy_qty,
                    exec_sell_qty = r.exec_sell_qty,

                    buy_liquidity_ratio  = buy_liq,
                    sell_liquidity_ratio = sell_liq,

                    pct_spread        = pct_spread,
                    coef_var_buy      = coef_var_buy,
                    true_range        = true_range,
                    vwap_buy          = vwap_buy,
                    vwap_sell         = vwap_sell,
                    imbalance_qty     = imbalance_qty,
                    sell_through_rate = sell_through_rate,
                    atr_like          = atr_like,
                ))

            # ========= purge du brut du jour ==============================
            s.query(DailyRaw).filter(func.date(DailyRaw.ts) == day).delete(synchronize_session=False)
            s.commit()
            print(f"✅ {day} agrégé & purgé.")


if __name__ == "__main__":
    aggregate_all_days()
