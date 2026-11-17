"""Run a scripted take from a JSON spec: recorders start and stop around the steps, and every
step's moment is written down, so later tools know when things happened.

Spec (all keys optional except steps):
{
  "out": "takes/orbit",                         # folder for this take's files
  "android": {"serial": null, "adb": "adb"},
  "ios_sim": {"udid": "booted"},
  "record": {
    "android":    {"seconds": 20, "bitrate": 6000000},
    "ios_sim":    {},
    "mac_window": {"title": "Drone Synth", "app": null, "seconds": 18, "binary": "macwinrec"}
  },
  "steps": [
    {"lock_landscape": true},
    {"tap_label": "Presets"},
    {"scroll_to": "ORBIT", "region": [380, 330, 700, 700]},
    {"start": true},                 # starts every recorder in "record"
    {"wait": 3},
    {"tap_label": "ORBIT", "mark": "load"},
    {"wait": 2.5},
    {"hold": [780, 640, 10000], "mark": "key"},
    {"stop": true}
  ]
}

Writes <out>/take.json: {"marks": {"key": <epoch>, ...}, "files": {...}, "recorders": {...}}.
Marks are wall-clock times (time.time()) taken just before each step runs. Use them to tell
event-sync roughly where to look (its --after options); measure the real moment with it.
"""
from __future__ import annotations

import json
import os
import subprocess
import time

from .android import Device
from .ios import Simulator

STEP_KEYS = {'wait', 'tap', 'tap_label', 'swipe', 'hold', 'drag_path', 'scroll_to', 'launch', 'lock_landscape',
             'lock_portrait', 'demo_mode', 'screenshot', 'start', 'stop', 'shell', 'mark'}


def validate(spec: dict) -> list[str]:
    """Problems with a spec, as readable messages (empty when it's fine)."""
    problems = []
    steps = spec.get('steps')
    if not isinstance(steps, list) or not steps:
        return ['"steps" must be a non-empty list']
    starts = sum(1 for s in steps if s.get('start'))
    stops = sum(1 for s in steps if s.get('stop'))
    if spec.get('record') and starts != 1:
        problems.append('with "record", exactly one step must be {"start": true}')
    if starts and stops > 1:
        problems.append('at most one {"stop": true}')
    for i, s in enumerate(steps):
        unknown = set(s) - STEP_KEYS - {'region', 'contains', 'ms', 'path', 'clock'}
        if unknown:
            problems.append(f'step {i}: unknown keys {sorted(unknown)}')
        if 'hold' in s and (not isinstance(s['hold'], list) or len(s['hold']) != 3):
            problems.append(f'step {i}: "hold" is [x, y, milliseconds]')
        if 'scroll_to' in s and 'region' not in s:
            problems.append(f'step {i}: "scroll_to" needs "region": [left, top, right, bottom]')
    rec = spec.get('record', {})
    if 'mac_window' in rec and 'title' not in rec['mac_window']:
        problems.append('record.mac_window needs "title"')
    return problems


class Take:
    def __init__(self, spec: dict, dry_run: bool = False):
        self.spec = spec
        self.dry_run = dry_run
        self.out = spec.get('out', 'take')
        a = spec.get('android', {})
        self.device = Device(a.get('serial'), a.get('adb', 'adb'), dry_run) if (a or self._needs_android()) else None
        self.sim = Simulator(spec.get('ios_sim', {}).get('udid', 'booted'), dry_run) if 'ios_sim' in spec else None
        self.marks: dict[str, float] = {}
        self.files: dict[str, str] = {}
        self.recorders: dict[str, dict] = {}
        self._procs: dict[str, subprocess.Popen | None] = {}
        self.log: list[str] = []

    def _needs_android(self):
        keys = {'tap', 'tap_label', 'swipe', 'hold', 'drag_path', 'scroll_to', 'launch', 'lock_landscape',
                'lock_portrait', 'demo_mode', 'screenshot'}
        return any(set(s) & keys for s in self.spec.get('steps', [])) or 'android' in self.spec.get('record', {})

    def _sleep(self, s):
        if not self.dry_run:
            time.sleep(s)

    # MARK: recorders

    def start(self):
        rec = self.spec.get('record', {})
        os.makedirs(self.out, exist_ok=True)
        if 'mac_window' in rec:
            m = rec['mac_window']
            path = os.path.join(self.out, 'window.mov')
            cmd = [m.get('binary', 'macwinrec'), '--title', m['title'], '--seconds', str(m.get('seconds', 20)),
                   '--out', path] + (['--app', m['app']] if m.get('app') else [])
            self.log.append(' '.join(cmd))
            self._procs['mac_window'] = None if self.dry_run else subprocess.Popen(
                cmd, stdout=subprocess.PIPE, text=True)
            self.files['mac_window'] = path
        if 'android' in rec:
            r = rec['android']
            self._procs['android'] = self.device.start_recording(r.get('seconds', 20),
                                                                 bitrate=r.get('bitrate', 6_000_000))
            self.files['android'] = os.path.join(self.out, 'android.mp4')
        if 'ios_sim' in rec:
            path = os.path.join(self.out, 'ios.mp4')
            self._procs['ios_sim'] = self.sim.start_recording(path)
            self.files['ios_sim'] = path
        self.marks['recording_started'] = time.time()

    def stop(self):
        if 'ios_sim' in self._procs:
            Simulator.stop_recording(self._procs.pop('ios_sim'))
        for name, p in list(self._procs.items()):
            if p is None:
                continue
            out, _ = p.communicate(timeout=240)
            if name == 'mac_window' and out:
                events = [json.loads(l) for l in out.splitlines() if l.startswith('{')]
                self.recorders[name] = {e['event']: e for e in events}
                if 'error' in self.recorders[name]:
                    raise RuntimeError(f"window recording failed: {self.recorders[name]['error']['message']}")
        if 'android' in self.files:
            self._sleep(1.0)
            self.device.pull('/sdcard/promocap.mp4', self.files['android'])
        self._procs.clear()

    # MARK: steps

    def run(self) -> dict:
        problems = validate(self.spec)
        if problems:
            raise ValueError('; '.join(problems))
        try:
            for step in self.spec['steps']:
                if 'mark' in step:
                    self.marks[step['mark']] = time.time()
                self._step(step)
        finally:
            if self._procs:
                self.stop()
        result = {'out': self.out, 'marks': self.marks, 'files': self.files, 'recorders': self.recorders}
        if not self.dry_run:
            os.makedirs(self.out, exist_ok=True)
            with open(os.path.join(self.out, 'take.json'), 'w') as f:
                json.dump(result, f, indent=2)
        return result

    def _step(self, s: dict):
        d = self.device
        if 'wait' in s:
            self._sleep(float(s['wait']))
        if s.get('lock_landscape'):
            d.lock_orientation(True)
        if s.get('lock_portrait'):
            d.lock_orientation(False)
        if 'demo_mode' in s:
            d.demo_mode(bool(s['demo_mode']), s.get('clock', '0900'))
        if 'launch' in s:
            d.launch(s['launch'])
        if 'scroll_to' in s:
            d.scroll_to(s['scroll_to'], tuple(s['region']))
        if 'tap_label' in s:
            d.tap_label(s['tap_label'], contains=s.get('contains', False))
        if 'tap' in s:
            d.tap(*s['tap'])
        if 'swipe' in s:
            d.swipe(*s['swipe'])
        if 'drag_path' in s:
            d.drag_path([tuple(p) for p in s['drag_path']], s.get('ms', 300))
        if 'hold' in s:
            d.hold(*s['hold'])
        if 'shell' in s:
            d.shell(*s['shell'])
        if 'screenshot' in s:
            os.makedirs(self.out, exist_ok=True)
            d.screenshot(os.path.join(self.out, s['screenshot']))
        if s.get('start'):
            self.start()
        if s.get('stop'):
            self.stop()
