import subprocess


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
