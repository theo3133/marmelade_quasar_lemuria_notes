import requests, time, datetime, os
from sqlalchemy import select
from models import Session, DailyRaw, Item              # ←  NOTE: DailyRaw !
API_BASE = "https://api.guildwars2.com/v2"

# --- Helpers ---------------------------------------------------------------
def batched(iterable, n=200):
    for i in range(0, len(iterable), n):
        yield iterable[i : i + n]

def get_all_price_ids():
    r = requests.get(f"{API_BASE}/commerce/prices", timeout=20)
    r.raise_for_status()
    return r.json()          # → liste d’IDs

def get_price_details(ids):
    results = []
    for chunk in batched(ids):
        r = requests.get(f"{API_BASE}/commerce/prices",
                         params={"ids": ",".join(map(str, chunk))},
                         timeout=20)
        r.raise_for_status()
        results.extend(r.json())
        time.sleep(0.3)      # throttle léger
    return results

def get_item_names(ids):
    results = []
    for chunk in batched(ids):
        r = requests.get(f"{API_BASE}/items",
                         params={"ids": ",".join(map(str, chunk))},
                         timeout=20)
        r.raise_for_status()
        results.extend(r.json())
        time.sleep(0.3)
    return {it["id"]: it.get("name", "UNKNOWN") for it in results}

# --- Main fetch ------------------------------------------------------------
def fetch_and_store_daily_raw():
    ids = get_all_price_ids()
    print(f"📦  {len(ids)} items à snapshot ({datetime.datetime.utcnow():%F %T} UTC)")

    data   = get_price_details(ids)
    now_ts = datetime.datetime.now(datetime.timezone.utc)

    with Session() as s:
        # 1) S’assurer que tous les items existent dans la table items
        known_ids = {row[0] for row in s.execute(select(Item.id)).all()}
        missing   = set(ids) - known_ids
        if missing:
            print(f"➕  {len(missing)} nouveaux items → insertion dans items…")
            names = get_item_names(list(missing))
            s.bulk_save_objects([Item(id=i, name=names.get(i, "UNKNOWN"))
                                 for i in missing])

        # 2) Insertion des snapshots bruts
        s.bulk_save_objects([
            DailyRaw(
                item_id      = entry["id"],
                ts           = now_ts,
                buy_price    = entry["buys"]["unit_price"],
                buy_quantity = entry["buys"]["quantity"],
                sell_price   = entry["sells"]["unit_price"],
                sell_quantity= entry["sells"]["quantity"],
            )
            for entry in data
        ])
        s.commit()
    print("✅  Snapshots enregistrés dans daily_raw.")

if __name__ == "__main__":
    fetch_and_store_daily_raw()
