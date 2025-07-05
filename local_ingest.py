"""
local_ingest.py
──────────────────────────────────────────────────────────────────────────────
Met à jour la branche `raw-feed`, ingère tous les snapshots JSON dans
daily_raw, supprime les fichiers puis pousse la purge.  Si des
modifications locales sont en cours, elles sont automatiquement stashées
avant le pull/rebase et restaurées ensuite.
"""

import json, os, subprocess, pathlib, datetime
from models import Session, DailyRaw      # modèles existants

# ───────────── CONFIG ────────────────────────────────────────────────────────
DATABASE_URL = "postgresql://postgres:password@localhost/gw2"   # ← ta DB locale
BRANCH       = "raw-feed"
SNAP_DIR     = pathlib.Path("snapshots")                        # dossier dans le dépôt
# ─────────────────────────────────────────────────────────────────────────────


def git(*args, check: bool = True):
    """Exécute git dans le repo courant."""
    subprocess.run(["git", *args], check=check)


def ensure_branch_up_to_date() -> None:
    """
    Passe (ou crée) la branche BRANCH puis la met à jour via
    `git pull --rebase`.  Toutes les modifs locales sont stashées
    automatiquement pour éviter l’erreur « cannot pull with rebase ».
    """
    # 1) switch / create
    if subprocess.call(
        ["git", "rev-parse", "--verify", BRANCH],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ):
        git("switch", "--create", BRANCH)
    else:
        git("switch", BRANCH)

    # 2) stash automatique
    git("stash", "push", "-u", "-m", "auto_local_ingest")  # -u : inclut fichiers non suivis
    try:
        git("pull", "--rebase", "origin", BRANCH)
    finally:
        # tente de sortir le stash ; si rien à appliquer, retourne code 1 → check=False
        git("stash", "pop", check=False)


def files_to_ingest() -> list[pathlib.Path]:
    SNAP_DIR.mkdir(exist_ok=True)
    return sorted(SNAP_DIR.glob("*.json"))


def ingest_file(path: pathlib.Path) -> None:
    print(f"   ↳ {path.name}")
    data = json.loads(path.read_text("utf-8"))
    with Session() as s:
        for row in data:
            s.add(DailyRaw(**row))
        s.commit()
    path.unlink()   # suppression après succès


def main() -> None:
    # assure que models.py se connecte à la bonne DB
    os.environ["DATABASE_URL"] = DATABASE_URL

    print("→ Mise à jour de la branche raw-feed …")
    ensure_branch_up_to_date()

    files = files_to_ingest()
    if not files:
        print("✅ Aucun nouveau snapshot à ingérer.")
        return

    for f in files:
        ingest_file(f)

    # pousser la purge (suppression des fichiers) vers GitHub
    git("add", "-u", str(SNAP_DIR))
    git("commit", "-m", f"purge after ingest {datetime.date.today()}") or True
    git("push", "origin", BRANCH)

    print("🎉 Tous les snapshots ont été ingérés et purgés.")


if __name__ == "__main__":
    main()
