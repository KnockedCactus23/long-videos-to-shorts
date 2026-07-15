import sys


def warn(message: str) -> None:
    print(f"[clipengine] Aviso: {message}", file=sys.stderr)
