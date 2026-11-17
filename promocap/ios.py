"""iPhone/iPad Simulator helpers for promo material (needs Xcode's `xcrun simctl`).

Real devices can't be scripted like this without extra tools; for App Store screenshots
and app previews the Simulator at the right device size is the usual route anyway.
"""
from __future__ import annotations

import shlex
import signal
import subprocess
import time


class Simulator:
    def __init__(self, udid: str = 'booted', dry_run: bool = False):
        self.udid = udid
        self.dry_run = dry_run
        self.log: list[str] = []

    def _simctl(self, *args: str) -> str:
        cmd = ['xcrun', 'simctl', *args]
        self.log.append(shlex.join(cmd))
        if self.dry_run:
            return ''
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

    def status_bar(self, time_text: str = '9:41', battery: int = 100):
        """Apple's marketing status bar: 9:41, full battery, full signal, no carrier name."""
        self._simctl('status_bar', self.udid, 'override', '--time', time_text, '--dataNetwork', 'wifi',
                     '--wifiMode', 'active', '--wifiBars', '3', '--cellularMode', 'active', '--cellularBars', '4',
                     '--operatorName', '', '--batteryState', 'charged', '--batteryLevel', str(battery))

    def clear_status_bar(self):
        self._simctl('status_bar', self.udid, 'clear')

    def appearance(self, dark: bool):
        self._simctl('ui', self.udid, 'appearance', 'dark' if dark else 'light')

    def launch(self, bundle_id: str, *args: str):
        self._simctl('launch', self.udid, bundle_id, *args)

    def open_url(self, url: str):
        self._simctl('openurl', self.udid, url)

    def screenshot(self, path: str):
        self._simctl('io', self.udid, 'screenshot', path)

    def start_recording(self, path: str, codec: str = 'h264') -> subprocess.Popen | None:
        """Records until stop_recording(). Returns the process (None in dry-run)."""
        cmd = ['xcrun', 'simctl', 'io', self.udid, 'recordVideo', f'--codec={codec}', '--force', path]
        self.log.append(shlex.join(cmd))
        if self.dry_run:
            return None
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(1.0)  # recordVideo needs a moment before the first frame
        return p

    @staticmethod
    def stop_recording(p: subprocess.Popen | None, timeout: float = 10):
        """recordVideo finishes its file on SIGINT (like Ctrl-C), not on kill."""
        if p is None:
            return
        p.send_signal(signal.SIGINT)
        p.wait(timeout=timeout)
