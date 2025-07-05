import requests
import time
from models import Session, Item

API_BASE = "https://api.guildwars2.com/v2"

def get_all_trading_post_item_ids():
    url = f"{API_BASE}/commerce/prices"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_item_details(ids):
    chunks = [ids[i:i+200] for i in range(0, len(ids), 200)]
    results = []
    for chunk in chunks:
        url = f"{API_BASE}/items"
        response = requests.get(url, params={"ids": ",".join(map(str, chunk))})
        response.raise_for_status()
        results.extend(response.json())
        time.sleep(0.3)  # pour respecter l'API rate limit
    return results

def fetch_and_store_items():
    ids = get_all_trading_post_item_ids()
    print(f"{len(ids)} items trouvés sur le Trading Post")

    items_data = get_item_details(ids)
    print("Détails récupérés. Insertion en base...")

    with Session() as session:
        for item in items_data:
            item_id = item.get("id")
            name = item.get("name")
            if not name:
                continue
            session.merge(Item(id=item_id, name=name))
        session.commit()

    print("✔️ Insertion terminée.")

if __name__ == "__main__":
    fetch_and_store_items()
