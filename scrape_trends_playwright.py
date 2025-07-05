#!/usr/bin/env python3
"""
Télécharge l’historique « daily » (API datawars2.ie) pour la fenêtre fixe
   2025-01-05  ➜  2025-07-03  (180 jours, exclut 2025-07-04).

▸ 1 fichier JSON par item dans scraped_trends/<ID>.json
▸ checkpoint.txt évite de re-scraper un ID déjà traité
▸ 40 workers parallèles en continu (filaire) – affichage en flux
"""

from dotenv import load_dotenv
load_dotenv()
import os
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL n'est pas défini (ni dans .env, ni en variable d'environnement).")

import aiohttp, asyncio, json
from pathlib import Path
from datetime import datetime, timedelta, timezone

# ── PARAMÈTRES ────────────────────────────────────────────────────────────────
CONCURRENCY = 40                       # workers simultanés
API_BASE    = "https://api.datawars2.ie/gw2/v2/history/json?itemID="
TIMEOUT     = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)

MAX_DATE = datetime(2025, 7, 3, tzinfo=timezone.utc).date()
MIN_DATE = MAX_DATE - timedelta(days=179)            # 180 jours inclus

OUT_DIR  = Path("scraped_trends"); OUT_DIR.mkdir(exist_ok=True)
CHK_FILE = OUT_DIR / "checkpoint.txt"; CHK_FILE.touch(exist_ok=True)
IDS_FILE = "item_ids.txt"

# ── HELPERS ───────────────────────────────────────────────────────────────────
def in_window(iso: str) -> bool:
    d = datetime.fromisoformat(iso.replace("Z","+00:00")).date()
    return MIN_DATE <= d <= MAX_DATE

def map_row(item: int, e: dict):
    if None in (
        e["buy_price_min"],  e["buy_price_max"],
        e["sell_price_min"], e["sell_price_max"]
    ):
        return None
    mid_buy  = round((e["buy_price_min"]  + e["buy_price_max"])  / 2, 2)
    mid_sell = round((e["sell_price_min"] + e["sell_price_max"]) / 2, 2)
    return {
        "item_id"  : item,
        "ts"       : e["date"].replace("T00:00:00.000Z","T00:00:00Z"),
        "buy_price": mid_buy,
        "buy_qty"  : e.get("buy_quantity_max")  or 0,
        "sell_price":mid_sell,
        "sell_qty" : e.get("sell_quantity_max") or 0,
    }

# ── WORKER ────────────────────────────────────────────────────────────────────
async def worker(queue: asyncio.Queue, session: aiohttp.ClientSession):
    while True:
        item_id = await queue.get()
        try:
            resp = await session.get(API_BASE + item_id)
            if resp.status != 200:
                print(f"HTTP {resp.status} → {item_id}")
                queue.task_done(); continue
            raw = await resp.json()
        except Exception as exc:
            print(f"⚠️  {item_id}: {exc}")
            queue.task_done(); continue

        rows = [
            r for e in raw if in_window(e["date"])
            if (r := map_row(int(item_id), e))
        ]
        (OUT_DIR/f"{item_id}.json").write_text(json.dumps(rows, indent=2))
        CHK_FILE.write_text(CHK_FILE.read_text() + item_id + "\n")
        print(f"✅ {item_id} : {len(rows)} jours")
        queue.task_done()

# ── MAIN ───────────────────────────────────────────────────────────────────────
async def main():
    ids_all = [l.strip() for l in open(IDS_FILE) if l.strip().isdigit()]
    done    = set(CHK_FILE.read_text().split())
    todo    = [i for i in ids_all if i not in done]
    print(f"{len(done)} déjà faits — {len(todo)} à faire")

    queue = asyncio.Queue()
    for id_ in todo:
        queue.put_nowait(id_)

    conn = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=conn, timeout=TIMEOUT) as sess:
        workers = [asyncio.create_task(worker(queue, sess)) for _ in range(CONCURRENCY)]
        await queue.join()                # attend que la file soit vide
        for w in workers: w.cancel()      # arrête les workers

if __name__ == "__main__":
    asyncio.run(main())
