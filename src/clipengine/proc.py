import subprocess
import sys
import threading


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run con check=True + captura, pero incluyendo el stderr real
    del proceso (ej. el mensaje de ffmpeg/ffprobe) en la excepción — el error
    por defecto de CalledProcessError solo muestra el código de salida."""
    try:
        return subprocess.run(cmd, check=True, capture_output=True, **kwargs)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        raise RuntimeError(
            f"Comando falló ({' '.join(cmd)}):\n{stderr.strip()[-4000:]}"
        ) from e


def _print_bar(label: str, percent: int, width: int = 30) -> None:
    filled = round(width * percent / 100)
    # Caracteres ASCII simples (no bloques Unicode): las consolas de Windows con
    # codepage por defecto pueden fallar al imprimir caracteres fuera de ese rango.
    bar = "#" * filled + "-" * (width - filled)
    sys.stderr.write(f"\r[clipengine] {label} [{bar}] {percent:3d}%")
    sys.stderr.flush()


def run_ffmpeg_with_progress(cmd: list[str], total_seconds: float, label: str) -> None:
    """Corre un comando de ffmpeg mostrando una barra de progreso en stderr, en vez
    de quedarse en silencio hasta que termina — requiere que `cmd` incluya
    `-progress pipe:1` para que ffmpeg reporte `out_time_ms=` por stdout.

    El stderr de ffmpeg (warnings, mensajes de error) se drena en un hilo aparte
    mientras se lee stdout, para no arriesgar un deadlock si llena el buffer del
    pipe antes de que el proceso termine.
    """
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    stderr_chunks: list[str] = []

    def _drain_stderr() -> None:
        for line in process.stderr:
            stderr_chunks.append(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    last_percent = -1
    for line in process.stdout:
        if not line.startswith("out_time_ms="):
            continue
        try:
            out_time_seconds = int(line.strip().split("=", 1)[1]) / 1_000_000
        except ValueError:
            continue
        percent = min(100, int(out_time_seconds / total_seconds * 100)) if total_seconds > 0 else 100
        if percent != last_percent:
            _print_bar(label, percent)
            last_percent = percent

    returncode = process.wait()
    stderr_thread.join()
    if last_percent >= 0:
        sys.stderr.write("\n")

    if returncode != 0:
        stderr = "".join(stderr_chunks)
        raise RuntimeError(f"Comando falló ({' '.join(cmd)}):\n{stderr.strip()[-4000:]}")
