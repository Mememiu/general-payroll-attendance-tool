import unittest

from payroll_tool.desktop.launcher import run_desktop


class FakeServer:
    def __init__(self, app, port=0):
        self.app = app
        self.port = 43210
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeWebview:
    def __init__(self, fail=False):
        self.fail = fail
        self.window = None
        self.started = False

    def create_window(self, title, url, **options):
        self.window = (title, url, options)
        if self.fail:
            raise RuntimeError("webview failed")

    def start(self):
        self.started = True


class DesktopLauncherTests(unittest.TestCase):
    def test_launcher_opens_loopback_window_and_stops_server(self):
        webview = FakeWebview()
        servers = []

        def server_factory(app, port=0):
            server = FakeServer(app, port)
            servers.append(server)
            return server

        run_desktop(
            data_root="/tmp/payroll-test",
            app_factory=lambda root: {"root": root},
            server_factory=server_factory,
            webview_module=webview,
        )

        self.assertEqual(webview.window[1], "http://127.0.0.1:43210/")
        self.assertEqual(webview.window[2]["min_size"], (1024, 720))
        self.assertTrue(webview.started)
        self.assertTrue(servers[0].started)
        self.assertTrue(servers[0].stopped)

    def test_launcher_stops_server_when_window_creation_fails(self):
        webview = FakeWebview(fail=True)
        server = FakeServer({})
        with self.assertRaisesRegex(RuntimeError, "webview failed"):
            run_desktop(
                app_factory=lambda root: {},
                server_factory=lambda app, port=0: server,
                webview_module=webview,
            )
        self.assertTrue(server.stopped)


if __name__ == "__main__":
    unittest.main()
