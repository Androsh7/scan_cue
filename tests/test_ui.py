"""Test UI"""

# Third-party libraries
import time

from rich.live import Live

# Project libraries
from scan_cue.ui import ScannerUI


def test_ui():
    ui = ScannerUI()
    with Live(ui, console=ui.console, refresh_per_second=1, transient=False) as live:
        ui.show_progress_bar()
        ui.update_progress_bar(current_progress=10, total_progress=100, description="test_progress")
        ui.advance_progress_bar(10)
        for num in range(100):
            time.sleep(0.01)
            ui.log("info", f"test{num}")
        ui.advance_progress_bar(10)
        time.sleep(0.5)
        ui.log("debug", "test2")
        ui.advance_progress_bar(10)
        time.sleep(0.5)
        ui.log("warning", "test5")
        ui.advance_progress_bar(10)
        ui.hide_progress_bar()
