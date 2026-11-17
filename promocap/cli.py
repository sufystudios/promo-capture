"""promocap: capture app footage for promo videos (Android over adb, the iOS Simulator, macOS windows).

Every command prints one JSON object.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from .android import Device
from .ios import Simulator
from .take import Take, validate


def _region(text):
    return tuple(int(v) for v in text.split(',')) if text else None


def android(o):
    d = Device(o.serial, o.adb)
    if o.action == 'dump':
        return {'nodes': [{'label': n.label, 'center': n.center, 'bounds': n.bounds, 'id': n.resource_id}
                          for n in d.dump() if n.label]}
    if o.action == 'find':
        n = d.find(o.arg, contains=o.contains, region=_region(o.region))
        return {'found': bool(n), 'label': o.arg, 'center': n.center if n else None, 'bounds': n.bounds if n else None}
    if o.action == 'tap-label':
        n = d.tap_label(o.arg, contains=o.contains)
        return {'tapped': n.label, 'center': n.center}
    if o.action == 'scroll-to':
        if not o.region:
            raise ValueError('scroll-to needs --region left,top,right,bottom (the list)')
        n = d.scroll_to(o.arg, _region(o.region))
        return {'found': n.label, 'center': n.center}
    if o.action == 'screenshot':
        d.screenshot(o.arg)
        return {'saved': o.arg}
    if o.action == 'record':
        started = time.time()
        p = d.start_recording(o.seconds, bitrate=o.bitrate)
        p.wait()
        time.sleep(1.0)
        d.pull('/sdcard/promocap.mp4', o.arg)
        return {'saved': o.arg, 'started_epoch': started, 'seconds': o.seconds}
    if o.action in ('landscape', 'portrait'):
        return {'locked': d.lock_orientation(o.action == 'landscape'), 'rotation': d.rotation()}
    if o.action == 'demo-mode':
        d.demo_mode(o.arg != 'off', o.clock)
        return {'demo_mode': o.arg != 'off'}
    raise ValueError(f'unknown action {o.action}')


def ios(o):
    s = Simulator(o.udid)
    if o.action == 'status-bar':
        s.clear_status_bar() if o.arg == 'clear' else s.status_bar()
        return {'status_bar': 'cleared' if o.arg == 'clear' else 'overridden'}
    if o.action == 'screenshot':
        s.screenshot(o.arg)
        return {'saved': o.arg}
    if o.action == 'record':
        p = s.start_recording(o.arg)
        started = time.time()
        time.sleep(o.seconds)
        Simulator.stop_recording(p)
        return {'saved': o.arg, 'started_epoch': started, 'seconds': o.seconds}
    if o.action == 'appearance':
        s.appearance(o.arg == 'dark')
        return {'appearance': o.arg}
    raise ValueError(f'unknown action {o.action}')


def take(o):
    spec = json.load(open(o.spec))
    problems = validate(spec)
    if o.validate or problems:
        return {'valid': not problems, 'problems': problems}
    t = Take(spec, dry_run=o.dry_run)
    result = t.run()
    if o.dry_run:
        result['commands'] = (t.device.log if t.device else []) + (t.sim.log if t.sim else []) + t.log
    return result


def build_parser():
    p = argparse.ArgumentParser(prog='promocap', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('android', help='one action on an Android device')
    a.add_argument('action', choices=['dump', 'find', 'tap-label', 'scroll-to', 'screenshot', 'record', 'landscape',
                                      'portrait', 'demo-mode'])
    a.add_argument('arg', nargs='?', help='label / output file / on|off')
    a.add_argument('--serial'); a.add_argument('--adb', default='adb')
    a.add_argument('--region', help='left,top,right,bottom'); a.add_argument('--contains', action='store_true')
    a.add_argument('--seconds', type=float, default=15); a.add_argument('--bitrate', type=int, default=6_000_000)
    a.add_argument('--clock', default='0900')
    a.set_defaults(fn=android)
    i = sub.add_parser('ios', help='one action on the iOS Simulator')
    i.add_argument('action', choices=['status-bar', 'screenshot', 'record', 'appearance'])
    i.add_argument('arg', nargs='?', help='output file / clear / dark|light')
    i.add_argument('--udid', default='booted'); i.add_argument('--seconds', type=float, default=15)
    i.set_defaults(fn=ios)
    t = sub.add_parser('take', help='run a scripted take from a JSON spec')
    t.add_argument('spec'); t.add_argument('--dry-run', action='store_true', help="print the commands, touch nothing")
    t.add_argument('--validate', action='store_true', help='only check the spec')
    t.set_defaults(fn=take)
    return p


def main(argv=None):
    o = build_parser().parse_args(argv)
    try:
        result = o.fn(o)
    except LookupError as e:
        print(json.dumps({'error': 'not_found', 'message': str(e)}))
        return 2
    except (ValueError, RuntimeError, OSError) as e:
        print(json.dumps({'error': 'failed', 'message': str(e)}))
        return 1
    print(json.dumps(result, indent=2, default=list))
    return 0 if result.get('valid', True) else 1


if __name__ == '__main__':
    sys.exit(main())
