"""Drive an Android device over adb for promo recordings: find things on screen by their
text, tap, scroll lists, hold keys, keep the screen tidy, and record it.

Coordinates are screen pixels in the current orientation (what `adb shell input` uses).
"""
from __future__ import annotations

import html
import re
import shlex
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    """One element from a UI dump."""
    text: str
    desc: str
    resource_id: str
    bounds: tuple[int, int, int, int]  # left, top, right, bottom
    clickable: bool

    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.bounds
        return (l + r) // 2, (t + b) // 2

    @property
    def label(self) -> str:
        """Its text, or its content description when it has no text (icons, images)."""
        return self.text or self.desc


_ATTR = re.compile(r'([\w-]+)=(?:"([^"]*)"|\'([^\']*)\')')


def parse_ui(xml: str) -> list[Node]:
    """Nodes from `uiautomator dump` XML. Handles both quote styles (text='Save "X"' happens)
    and HTML entities."""
    nodes = []
    for m in re.finditer(r'<node\b(.*?)/?>', xml, re.S):
        attrs = {k: html.unescape(v1 if v1 or not v2 else v2) for k, v1, v2 in _ATTR.findall(m.group(1))}
        b = re.findall(r'\d+', attrs.get('bounds', ''))
        if len(b) != 4:
            continue
        nodes.append(Node(attrs.get('text', ''), attrs.get('content-desc', ''), attrs.get('resource-id', ''),
                          tuple(int(v) for v in b), attrs.get('clickable') == 'true'))
    return nodes


class Device:
    """One adb device. With dry_run=True nothing runs: commands are appended to `.log`, and
    dumps come from `.fake_dumps` (a list of XML strings, used in order) - for tests and planning."""

    def __init__(self, serial: str | None = None, adb: str = 'adb', dry_run: bool = False):
        self.adb = [adb] + (['-s', serial] if serial else [])
        self.dry_run = dry_run
        self.log: list[str] = []
        self.fake_dumps: list[str] = []

    # MARK: raw

    def _run(self, args: list[str], text=True) -> str | bytes:
        cmd = self.adb + args
        self.log.append(shlex.join(cmd))
        if self.dry_run:
            return '' if text else b''
        r = subprocess.run(cmd, capture_output=True, text=text)
        err = r.stderr if text else r.stderr.decode(errors='replace')
        if r.returncode != 0 or 'no devices/emulators found' in err or 'device offline' in err:
            raise RuntimeError(f'adb failed ({shlex.join(cmd)}): {err.strip() or r.returncode}')
        return r.stdout

    def shell(self, *args: str) -> str:
        return self._run(['shell', *args])

    # MARK: reading the screen

    def dump(self) -> list[Node]:
        """Everything on screen now. (Uses uiautomator; it can take ~1 s.)"""
        if self.dry_run:
            self.log.append('dump')
            return parse_ui(self.fake_dumps.pop(0)) if self.fake_dumps else []
        out = self.shell('uiautomator', 'dump', '/sdcard/promocap-ui.xml')
        if 'ERROR' in out or 'dumped to' not in out:
            # Seen when the screen is off or locked ("null root node"), or another dump is running.
            raise RuntimeError(f'uiautomator could not read the screen (is it on and unlocked?): {out.strip()}')
        return parse_ui(self._run(['exec-out', 'cat', '/sdcard/promocap-ui.xml']))

    def find(self, label: str, nodes: list[Node] | None = None, contains: bool = False,
             region: tuple[int, int, int, int] | None = None) -> Node | None:
        """The first element whose text (or description) is `label` (case-insensitive), optionally inside `region`."""
        want = label.casefold()
        for n in nodes if nodes is not None else self.dump():
            got = n.label.casefold()
            if (want in got) if contains else (got == want):
                if region is None or _inside(n.center, region):
                    return n
        return None

    # MARK: touching

    def tap(self, x: int, y: int):
        self.shell('input', 'tap', str(x), str(y))

    def tap_label(self, label: str, contains: bool = False, wait: float = 0.6) -> Node:
        n = self.find(label, contains=contains)
        if not n:
            raise LookupError(f'nothing labelled {label!r} on screen')
        self.tap(*n.center)
        time.sleep(0 if self.dry_run else wait)
        return n

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 400):
        self.shell('input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(ms))

    def hold(self, x: int, y: int, ms: int):
        """Press and hold one point (a key) for `ms`. Returns when it's released."""
        self.swipe(x, y, x, y, ms)

    def drag_path(self, points: list[tuple[int, int]], ms_per_segment: int = 300):
        """Drags through several points as quickly-chained swipes (adb has no multi-point gesture
        without root). Each segment is its own touch: fine for knobs that follow vertical drags."""
        cmds = [f'input swipe {a[0]} {a[1]} {b[0]} {b[1]} {ms_per_segment}' for a, b in zip(points, points[1:])]
        self.shell(' ; '.join(cmds))

    def scroll_to(self, label: str, region: tuple[int, int, int, int], max_swipes: int = 40,
                  settle: float = 0.5) -> Node:
        """Scrolls a list (the rectangle `region`) until `label` is fully inside it, searching down
        first, then back up. Returns the element where it settled."""
        l, t, r, b = region
        x = (l + r) // 2
        for direction in (1, -1):
            for _ in range(max_swipes):
                nodes = self.dump()
                n = self.find(label, nodes, region=(l, t + 10, r, b - 20))
                if n:
                    time.sleep(0 if self.dry_run else settle)  # let the list stop, then read its final place
                    return self.find(label, region=region) or n
                if direction > 0:
                    self.swipe(x, b - 30, x, b - 30 - (b - t) // 2, 500)
                else:
                    self.swipe(x, t + 30, x, t + 30 + (b - t) // 2, 500)
                time.sleep(0 if self.dry_run else 0.3)
        raise LookupError(f'{label!r} not found in the list at {region}')

    # MARK: device state

    def launch(self, package: str):
        self.shell('monkey', '-p', package, '-c', 'android.intent.category.LAUNCHER', '1')

    def wake(self, stay_on: bool = True):
        self.shell('input', 'keyevent', 'KEYCODE_WAKEUP')
        if stay_on:
            self.shell('svc', 'power', 'stayon', 'true')

    def rotation(self) -> int:
        """0, 90, 180 or 270."""
        out = self.shell('dumpsys', 'window')
        m = re.search(r'(?:mRotation|mCurrentRotation)=ROTATION_(\d+)', out or '')
        return int(m.group(1)) if m else 0

    def lock_orientation(self, landscape: bool = True, tries: int = 10) -> bool:
        """Turns auto-rotate off and locks the orientation, until it holds. (Some phones turn
        auto-rotate back on by themselves: call this again right before each take.)"""
        want = 90 if landscape else 0
        for _ in range(tries):
            self.shell('settings', 'put', 'system', 'accelerometer_rotation', '0')
            self.shell('settings', 'put', 'system', 'user_rotation', '1' if landscape else '0')
            if self.dry_run:
                return True
            time.sleep(1.5)
            if self.rotation() == want:
                return True
        return False

    def demo_mode(self, on: bool = True, clock: str = '0900', battery: int = 100):
        """A tidy status bar for screenshots and videos: fixed clock, full battery, full signal,
        no notification icons. Uses SystemUI demo mode."""
        bc = ['am', 'broadcast', '-a', 'com.android.systemui.demo', '-e', 'command']
        if not on:
            self.shell(*bc, 'exit')
            return
        self.shell('settings', 'put', 'global', 'sysui_demo_allowed', '1')
        self.shell(*bc, 'enter')
        self.shell(*bc, 'clock', '-e', 'hhmm', clock)
        self.shell(*bc, 'battery', '-e', 'level', str(battery), '-e', 'plugged', 'false')
        self.shell(*bc, 'network', '-e', 'wifi', 'show', '-e', 'level', '4')
        self.shell(*bc, 'network', '-e', 'mobile', 'show', '-e', 'datatype', 'none', '-e', 'level', '4')
        self.shell(*bc, 'notifications', '-e', 'visible', 'false')

    # MARK: capturing

    def screenshot(self, local_path: str):
        png = self._run(['exec-out', 'screencap', '-p'], text=False)
        if not self.dry_run:
            with open(local_path, 'wb') as f:
                f.write(png)

    def start_recording(self, seconds: float, remote: str = '/sdcard/promocap.mp4',
                        bitrate: int = 6_000_000) -> subprocess.Popen | None:
        """Starts `screenrecord` (max 180 s). 6 Mbps: on low-end phones higher rates slow the UI
        itself to a few frames per second and drop taps. Wait for it, then pull()."""
        self.shell('rm', '-f', remote)
        cmd = self.adb + ['shell', 'screenrecord', '--time-limit', str(int(min(180, seconds + 1))),
                          '--bit-rate', str(bitrate), remote]
        self.log.append(shlex.join(cmd))
        return None if self.dry_run else subprocess.Popen(cmd)

    def pull(self, remote: str, local: str):
        self._run(['pull', remote, local])


def _inside(p, region):
    l, t, r, b = region
    return l <= p[0] <= r and t <= p[1] <= b
