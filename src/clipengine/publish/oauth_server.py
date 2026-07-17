import http.server
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass


@dataclass
class OAuthCallbackResult:
    code: str | None
    state: str | None
    error: str | None


class _LocalCallbackServer(http.server.HTTPServer):
    def server_bind(self) -> None:
        # HTTPServer.server_bind() por defecto resuelve el hostname vía socket.getfqdn(),
        # que en macOS sin red activa puede colgarse ~30s en la primera resolución de
        # "localhost" — no hace falta ese hostname acá, así que se evita del todo.
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


def _make_handler(result_holder: dict, done_event: threading.Event) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            # El navegador suele pedir /favicon.ico antes o después del callback real —
            # ignorarlo evita capturar una respuesta vacía en vez de la de /callback.
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = urllib.parse.parse_qs(parsed.query)
            result_holder["code"] = params.get("code", [None])[0]
            result_holder["state"] = params.get("state", [None])[0]
            result_holder["error"] = params.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body>Listo, podés cerrar esta pestaña y volver a la terminal.</body></html>".encode(
                    "utf-8"
                )
            )
            done_event.set()

        def log_message(self, format: str, *args) -> None:  # silencia el log del server en stderr
            pass

    return Handler


def wait_for_callback(auth_url: str, port: int, timeout_seconds: float = 300) -> OAuthCallbackResult:
    """Levanta un servidor HTTP local en localhost:port/callback, abre auth_url en el
    navegador y espera hasta que llegue el callback de la plataforma (o venza el
    timeout). Usado por tiktok.py/instagram.py en su authorize() respectivo — cada
    plataforma arma su propia auth_url (con su client_id/scope/PKCE), esto solo resuelve
    la plomería de bajo nivel común a ambas."""
    result_holder: dict = {}
    done_event = threading.Event()
    server = _LocalCallbackServer(("localhost", port), _make_handler(result_holder, done_event))
    server.timeout = 1.0  # para que handle_request() no bloquee más allá del deadline

    def _serve() -> None:
        deadline = time.monotonic() + timeout_seconds
        while not done_event.is_set() and time.monotonic() < deadline:
            server.handle_request()

    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()

    webbrowser.open(auth_url)

    finished = done_event.wait(timeout_seconds)
    server_thread.join(timeout=5)
    server.server_close()

    if not finished:
        raise TimeoutError(
            "Tiempo de espera agotado esperando la autorización en el navegador. "
            "Volvé a correr `clipengine auth <plataforma>`."
        )

    return OAuthCallbackResult(
        code=result_holder.get("code"), state=result_holder.get("state"), error=result_holder.get("error")
    )
