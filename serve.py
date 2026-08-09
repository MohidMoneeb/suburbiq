#!/usr/bin/env python3
"""Dev-server launcher.

Prefers the project-local `venv/` for dependencies. Some sandboxed launchers
cannot read the user site-packages under ~/Library/Python, and cannot exec a
relative interpreter path either, so this script runs under whatever `python3`
is on PATH and prepends the project venv's site-packages instead.

Plain `python -m uvicorn suburbiq.api:app` works fine outside that sandbox;
this file exists purely to make the in-app preview launcher work.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

for site in glob.glob(os.path.join(ROOT, "venv", "lib", "python*", "site-packages")):
    if site not in sys.path:
        sys.path.insert(0, site)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import uvicorn  # noqa: E402  (import must follow the sys.path setup)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8077"))
    uvicorn.run("suburbiq.api:app", host="127.0.0.1", port=port, loop="asyncio")
