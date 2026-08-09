"""Single source of truth for on-disk locations.

Centralised so a package move can't silently scatter the database and cache
into the wrong directory, and so deployments can relocate data with one env var.
"""
import os

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PKG_DIR)

DATA_DIR = os.environ.get("SUBURBIQ_DATA", os.path.join(ROOT, "data"))
OUT_DIR = os.environ.get("SUBURBIQ_OUT", os.path.join(ROOT, "out"))
CACHE_DIR = os.path.join(DATA_DIR, "cache")
DB_PATH = os.path.join(DATA_DIR, "suburbiq.db")
WEB_DIR = os.path.join(PKG_DIR, "web")
SEED_DB = os.path.join(ROOT, "seed", "suburbiq-seed.db")


def ensure() -> None:
    """Create working directories, and seed the database on a cold start.

    The working database is gitignored, so a fresh deployment would otherwise
    boot with nothing to show. If a seed snapshot is committed and no database
    exists yet, restore it once. Local runs with an existing db are untouched.
    """
    for d in (DATA_DIR, OUT_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)

    if not os.path.exists(DB_PATH) and os.path.exists(SEED_DB):
        import shutil
        shutil.copyfile(SEED_DB, DB_PATH)
