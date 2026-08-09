"""Shared HTTP layer: on-disk cache, polite pacing, exponential backoff.

This lives outside the adapters on purpose. Every source we probed rate-limits
(Overpass returned 429 after two rapid queries), so caching and backoff are
infrastructure concerns rather than something each adapter reimplements.
"""
import hashlib
import json
import os
import time
from typing import Optional, Dict

import requests

from .paths import CACHE_DIR

# Overpass asks for gentle use; one call per second is well inside their policy.
MIN_INTERVAL = 1.0
_last_call = [0.0]


def _cache_path(key: str) -> str:
    h = hashlib.sha1(key.encode()).hexdigest()[:20]
    return os.path.join(CACHE_DIR, f"{h}.cache")


def _pace() -> None:
    delta = time.time() - _last_call[0]
    if delta < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - delta)
    _last_call[0] = time.time()


def post_cached(url: str, data: Dict[str, str], *, cache_key: str,
                timeout: int = 180, max_retries: int = 4,
                use_cache: bool = True) -> str:
    """POST with disk caching and backoff on 429/5xx. Returns response text."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(cache_key)
    if use_cache and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    delay = 5.0
    last_status = 0
    for attempt in range(max_retries):
        _pace()
        try:
            resp = requests.post(url, data=data, timeout=timeout,
                                 headers={"User-Agent": "SuburbIQ/0.1 (PoC; contact via repo)"})
            last_status = resp.status_code
            if resp.status_code == 200:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(resp.text)
                return resp.text
            if resp.status_code in (429, 502, 503, 504):
                print(f"    rate limited ({resp.status_code}), backing off {delay:.0f}s "
                      f"[attempt {attempt + 1}/{max_retries}]")
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
        except requests.Timeout:
            print(f"    timeout, retrying in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"request failed after {max_retries} attempts (last status {last_status})")


def get_raw(url: str, *, timeout: int = 30,
            headers: Optional[Dict[str, str]] = None) -> requests.Response:
    """Plain GET used by the Yellow Pages adapter. No cache: we need the live
    status code to detect bot protection accurately."""
    _pace()
    base = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
    }
    if headers:
        base.update(headers)
    return requests.get(url, timeout=timeout, headers=base)


def load_json(text: str):
    return json.loads(text)
