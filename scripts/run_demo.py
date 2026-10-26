"""Servidor local exclusivo para uma base de demonstração identificada."""

import argparse
import os

try:
    from scripts.seed_demo import create_demo_app, demo_path, require_demo
except ModuleNotFoundError:
    from seed_demo import create_demo_app, demo_path, require_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=os.getenv("DEMO_DATABASE_PATH", ""))
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    try:
        if not 1024 <= args.port <= 65535:
            raise ValueError
        path = demo_path(args.database)
        require_demo(path)
    except ValueError, OSError:
        parser.exit(1, "Base demo inválida ou porta fora do intervalo 1024–65535.\n")
    print("Demonstração local: dados fictícios, envio de e-mails desativado.")
    create_demo_app(path).run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
