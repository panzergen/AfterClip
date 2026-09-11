"""Frozen entry point for the PyInstaller build.

Kept separate from ``app.main`` so the spec can pass a real script path while
the installed console entry point (``afterclip = app.main:main``) stays
unchanged.
"""

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
