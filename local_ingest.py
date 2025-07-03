import json, os, subprocess, pathlib, datetime
from sqlalchemy import create_engine
from models import Session, DailyRaw        # tes modèles existants

# --------------------------------------------------------------------------
# CONFIG À ADAPTER UNE SEULE FOIS
DATABASE_URL = "postgresql://postgres:password@localhost/gw2"   # ← ta DB locale
BRANCH       = "raw-feed"
SNAP_DIR     = pathlib.Path("snapshots")                        # dossier dans le dépôt
# --------------------------------------------------------------------------

def git(*args):
    """helper : exécute git dans le repo courant"""
    subprocess.run(["git", *args], check=True)

def update_branch():
    print("→ fetch + switch raw-feed …")
    git("fetch", "origin", f"{BRANCH}:{BRANCH}")
    git("switch", BRANCH)

def files_to_ingest():
    SNAP_DIR.mkdir(exist_ok=True)
    return sorted(SNAP_DIR.glob("*.json"))

def ingest_file(path):
    print(f"   ↳ {path.name}")
    data = json.loads(path.read_text("utf-8"))
    with Session() as s:
        for row in data:
            s.add(DailyRaw(**row))
        s.commit()
    path.unlink()   # supprime le fichier après succès

def main():
    os.environ["DATABASE_URL"] = DATABASE_URL   # pour models.py
    update_branch()
    files = files_to_ingest()
    if not files:
        print("✅ Aucun nouveau snapshot.")
        return
    for f in files:
        ingest_file(f)
    # facultatif : pousser la purge vers GitHub
    git("add", "-u", "snapshots")
    git("commit", "-m", f"purge after ingest {datetime.date.today()}")
    git("push", "origin", BRANCH)
    print("🎉 Tous les snapshots ont été ingérés et purgés.")

if __name__ == "__main__":
    main()
