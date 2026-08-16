from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the production operations console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18020)
    args = parser.parse_args()
    uvicorn.run(
        "channel_engine.production_operations_app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
