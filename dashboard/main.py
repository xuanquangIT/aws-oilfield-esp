"""CLI entry point; UI tooling may invoke the same ASGI app later."""

from __future__ import annotations

import argparse
from dataclasses import replace

import uvicorn

from dashboard.app.core.config import Settings
from dashboard.app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fixture", "aws"))
    parser.add_argument("--fixture-state", choices=("normal", "low-flow", "stale", "unavailable"))
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.mode:
        settings = replace(settings, mode=args.mode)
    if args.fixture_state:
        settings = replace(settings, fixture_state=args.fixture_state)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
