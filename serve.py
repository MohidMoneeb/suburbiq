#!/usr/bin/env python3
"""Server launcher — used both for local dev and for hosted deployment.

Prefers the project-local `venv/` for dependencies. Some sandboxed launchers
cannot read the user site-packages under ~/Library/Python, and cannot exec a
relative interpreter path either, so this script runs under whatever `python3`
is on PATH and prepends the project venv's site-packages instead. On a hosting
platform there is no `venv/` directory and the glob simply finds nothing.

Reads PORT and HOST from the environment, which is what hosts like Render,
Railway and Fly inject. Plain `python -m uvicorn suburbiq.api:app` also works.
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
    # Hosting platforms inject PORT and require binding 0.0.0.0. Locally we stay
    # on loopback so the dev server isn't exposed to the rest of the network.
    port = int(os.environ.get("PORT", "8077"))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run("suburbiq.api:app", host=host, port=port, loop="asyncio")
