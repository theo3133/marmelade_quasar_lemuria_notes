# fetch_to_daily_raw.py
import argparse, requests, time, datetime, json, sys

API_BASE = "https://api.guildwars2.com/v2"

def batched(seq, n=200):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def fetch_snapshot():
    ids = requests.get(f"{API_BASE}/commerce/prices").json()
    data = []
    for chunk in batched(ids):
        r = requests.get(f"{API_BASE}/commerce/prices", params={"ids": ",".join(map(str, chunk))}, timeout=20)
        data.extend(r.json())
        time.sleep(0.3)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return [{
        "item_id": e["id"],
        "ts": now,
        "buy_price": e["buys"]["unit_price"],
        "buy_quantity": e["buys"]["quantity"],
        "sell_price": e["sells"]["unit_price"],
        "sell_quantity": e["sells"]["quantity"],
    } for e in data]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output")          # si présent → mode JSON
    args = ap.parse_args()

    snaps = fetch_snapshot()

    if args.output:                      # ----- mode cloud -----
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(snaps, f, separators=(",", ":"))
        print(f"💾 {args.output} écrit ({len(snaps)} items).")
    else:                                # ----- mode local -----
        from models import Session, DailyRaw, Item     # import tardif
        with Session() as s:
            for d in snaps:
                s.add(DailyRaw(**d))
            s.commit()
        print("✅ Snapshots insérés en base.")

if __name__ == "__main__":
    main()
