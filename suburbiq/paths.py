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


def ensure() -> None:
    for d in (DATA_DIR, OUT_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)
