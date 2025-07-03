import requests
import time
import datetime
from models import Session, Snapshot, Item
from sqlalchemy import text, select

API_BASE = "https://api.guildwars2.com/v2"

def get_all_price_snapshots():
    url = f"{API_BASE}/commerce/prices"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_price_details(ids):
    chunks = [ids[i:i+200] for i in range(0, len(ids), 200)]
    results = []
    for chunk in chunks:
        url = f"{API_BASE}/commerce/prices"
        response = requests.get(url, params={"ids": ",".join(map(str, chunk))})
        response.raise_for_status()
        results.extend(response.json())
        time.sleep(0.3)
    return results

def get_item_names(ids):
    chunks = [ids[i:i+200] for i in range(0, len(ids), 200)]
    results = []
    for chunk in chunks:
        url = f"{API_BASE}/items"
        response = requests.get(url, params={"ids": ",".join(map(str, chunk))})
        response.raise_for_status()
        results.extend(response.json())
        time.sleep(0.3)
    return results

def fetch_and_store_snapshots():
    ids = get_all_price_snapshots()
    print(f"{len(ids)} items à snapshot.")
    data = get_price_details(ids)
    now = datetime.datetime.now(datetime.timezone.utc)

    with Session() as session:
        # Liste des item_id connus
        known_ids = {row[0] for row in session.execute(select(Item.id)).all()}

        missing_ids = set()
        for entry in data:
            item_id = entry["id"]
            if item_id not in known_ids:
                print(f"⚠️ Item {item_id} manquant → à insérer")
                missing_ids.add(item_id)

        # Récupération des noms manquants
        if missing_ids:
            print(f"🔍 Récupération des noms pour {len(missing_ids)} items manquants...")
            details = get_item_names(list(missing_ids))
            for item in details:
                item_id = item.get("id")
                name = item.get("name", "UNKNOWN")
                session.merge(Item(id=item_id, name=name))

        # Insertion snapshots
        for entry in data:
            session.execute(
                text("""
                    INSERT INTO snapshots (item_id, ts, buy_price, buy_quantity, sell_price, sell_quantity)
                    VALUES (:item_id, :ts, :buy_price, :buy_qty, :sell_price, :sell_qty)
                    ON CONFLICT (item_id, ts) DO NOTHING
                """),
                {
                    "item_id": entry["id"],
                    "ts": now,
                    "buy_price": entry["buys"]["unit_price"],
                    "buy_qty": entry["buys"]["quantity"],
                    "sell_price": entry["sells"]["unit_price"],
                    "sell_qty": entry["sells"]["quantity"],
                }
            )

        session.commit()
    print("✔️ Snapshots enregistrés.")

if __name__ == "__main__":
    fetch_and_store_snapshots()
