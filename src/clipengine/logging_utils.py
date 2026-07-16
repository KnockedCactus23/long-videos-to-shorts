import sys


def warn(message: str) -> None:
    print(f"[clipengine] Aviso: {message}", file=sys.stderr)


def info(message: str) -> None:
    """Mensaje de progreso, no de error — para que pasos largos (descargas,
    transcripción) den señales de vida en vez de dejar la terminal en blanco."""
    print(f"[clipengine] {message}", file=sys.stderr)
