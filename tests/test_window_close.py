import threading

from phrasync.desktop_export import DesktopExportBridge


class FakeWindow:
    def __init__(self, fail=False):
        self.fail = fail
        self.scripts = []
        self.destroyed = threading.Event()
        self.ran = threading.Event()

    def evaluate_js(self, script):
        self.scripts.append(script)
        self.ran.set()
        if self.fail:
            raise RuntimeError("page gone")

    def destroy(self):
        self.destroyed.set()


def test_x_in_editor_goes_back_to_start_page_then_closes():
    bridge = DesktopExportBridge()
    bridge._window = FakeWindow()
    bridge.set_editor_open(True)
    assert bridge._on_closing() is False
    assert bridge._window.ran.wait(2) and bridge._window.scripts == ["showHome()"]
    assert bridge._on_closing() is True  # now on the start page: close for real


def test_x_closes_when_page_cannot_respond_and_quit_always_closes():
    bridge = DesktopExportBridge()
    bridge._window = FakeWindow(fail=True)
    bridge.set_editor_open(True)
    assert bridge._on_closing() is False
    assert bridge._window.destroyed.wait(2)
    other = DesktopExportBridge()
    other._window = FakeWindow()
    other.set_editor_open(True)
    other.close_window()
    assert other._window.destroyed.wait(2) and other._on_closing() is True
