"""Loopback-only server wrapper for the offline desktop application."""

from threading import Thread

from werkzeug.serving import make_server


class LocalAppServer:
    def __init__(self, app, port: int = 5050) -> None:
        self._app = app
        self.host = "127.0.0.1"
        self._server = make_server(self.host, port, app)
        self.port = self._server.server_port
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self._server.server_close()
        task_store = self._app.extensions.get("task_store")
        if task_store is not None:
            task_store.close()


def main() -> int:
    try:
        from payroll_tool.desktop.launcher import run_desktop

        run_desktop()
    except Exception as exc:
        print(f"通用薪酬绩效工具启动失败：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
