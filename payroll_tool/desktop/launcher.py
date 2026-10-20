"""Native window lifecycle for the offline desktop application."""


def run_desktop(
    data_root=None,
    *,
    app_factory=None,
    server_factory=None,
    webview_module=None,
):
    if app_factory is None:
        from app import create_desktop_app

        app_factory = create_desktop_app
    if server_factory is None:
        from desktop import LocalAppServer

        server_factory = LocalAppServer
    if webview_module is None:
        import webview as webview_module

    app = app_factory(data_root)
    server = server_factory(app, port=0)
    server.start()
    try:
        webview_module.create_window(
            "通用薪酬绩效工具",
            f"http://127.0.0.1:{server.port}/",
            min_size=(1024, 720),
        )
        webview_module.start()
    finally:
        server.stop()
