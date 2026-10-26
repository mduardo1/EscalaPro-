"""Entrada do servidor de desenvolvimento. Em produção, use um servidor WSGI."""

import socket

from app import create_app

app = create_app()


def main():
    if app.config["PRODUCTION"]:
        raise SystemExit(
            "Use Gunicorn em produção; run.py é apenas para desenvolvimento."
        )
    try:
        with socket.create_connection(("127.0.0.1", 5000), timeout=5):
            pass
    except ConnectionRefusedError:
        pass
    except OSError:
        raise SystemExit(
            "Não foi possível verificar a porta 5000. Confira o servidor em execução."
        ) from None
    else:
        raise SystemExit(
            "A porta 5000 já está em uso. Encerre a instância anterior do EscalaPro antes de iniciar outra."
        )
    app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
