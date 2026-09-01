"""The file list scrolls from wheel, trackpad, and arrow keys — not just the
scrollbar.

Tk 9 on macOS sends three different things for "scroll the thing under the
pointer": <MouseWheel> (physical wheel), <TouchpadScroll> (two-finger
trackpad), and plain key events. A Canvas gets a default binding for none of
them, so main.bind_region_scroll wires all three on the toplevel. These tests
drive each path with event_generate and check the canvas actually moves.
"""

import time

import pytest

import main
from tests.test_covers import _write

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _list_with_files(tmp_path, n=20):
    app = main.App()
    app.update()
    files = [_write(tmp_path / f"s{i:02d}.pdf", cover=False, music_pages=4)
             for i in range(n)]
    app.filelist.set_files(files)
    app._recompute()
    end = time.time() + 6
    while time.time() < end and (app.setplan is None or app.setplan.has_errors):
        app.update()
        time.sleep(0.02)
    app.update_idletasks()
    return app


def _deep_label(app):
    """A label inside the first row — i.e. the pointer is 'over the file list'
    but not over the canvas or the scrollbar."""
    row = app.filelist._real_rows()[0]
    return [c for c in row.winfo_children() if isinstance(c, main.tk.Label)][0]


def _over(canvas):
    return (canvas.winfo_rootx() + canvas.winfo_width() // 2,
            canvas.winfo_rooty() + canvas.winfo_height() // 2)


def test_mousewheel_over_a_row_scrolls_the_list(tmp_path):
    app = _list_with_files(tmp_path)
    try:
        cv = app.filelist._canvas
        mx, my = _over(cv)
        top = round(cv.yview()[0], 4)
        _deep_label(app).event_generate("<MouseWheel>", delta=-40, rootx=mx, rooty=my)
        app.update()
        assert cv.yview()[0] > top                       # scrolled down
        mid = cv.yview()[0]
        _deep_label(app).event_generate("<MouseWheel>", delta=40, rootx=mx, rooty=my)
        app.update()
        assert cv.yview()[0] < mid                        # and back up
    finally:
        app._on_close()


def test_touchpad_two_finger_scroll_moves_the_list(tmp_path):
    app = _list_with_files(tmp_path)
    try:
        cv = app.filelist._canvas
        mx, my = _over(cv)
        start = cv.yview()[0]
        # fingers moving up (natural): negative precise dy -> view goes toward end
        for _ in range(40):
            app.filelist._real_rows()[0].event_generate(
                "<TouchpadScroll>", delta=(0x10000 - 2), rootx=mx, rooty=my)
        app.update()
        assert cv.yview()[0] > start
    finally:
        app._on_close()


def test_arrow_key_scrolls_only_while_pointer_is_over_the_list(tmp_path):
    app = _list_with_files(tmp_path)
    try:
        cv = app.filelist._canvas
        mx, my = _over(cv)
        app.event_generate("<KeyPress-Down>", rootx=mx, rooty=my)
        app.update()
        moved = cv.yview()[0]
        assert moved > 0

        far_x, far_y = cv.winfo_rootx() - 400, cv.winfo_rooty() - 400
        app.event_generate("<KeyPress-Down>", rootx=far_x, rooty=far_y)
        app.update()
        assert cv.yview()[0] == moved                     # ignored off the list
    finally:
        app._on_close()


def test_short_list_does_not_scroll(tmp_path):
    app = _list_with_files(tmp_path, n=2)
    try:
        cv = app.filelist._canvas
        mx, my = _over(cv)
        _deep_label(app).event_generate("<MouseWheel>", delta=-40, rootx=mx, rooty=my)
        app.update()
        assert cv.yview() == (0.0, 1.0)
    finally:
        app._on_close()
