"""python3 -m unittest discover -s tests -v   (no device needed: uses dry-run devices and sample dumps)"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from promocap import Device, Take, parse_ui, validate  # noqa: E402
from promocap.cli import main  # noqa: E402

DUMP_TOP = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="1">
<node index="0" text="" resource-id="" class="android.widget.FrameLayout" content-desc="" clickable="false" bounds="[0,0][1600,720]">
<node index="1" text="Presets" resource-id="" class="android.widget.TextView" content-desc="" clickable="true" bounds="[62,150][174,210]" />
<node index="2" text='Save "Moog Bass" as Mine' resource-id="save" class="android.widget.Button" content-desc="" clickable="true" bounds="[213,212][566,260]" />
<node index="3" text="AURORA BOREALIS" resource-id="" class="android.widget.TextView" content-desc="" clickable="true" bounds="[380,450][560,476]" />
<node index="4" text="" resource-id="" class="android.widget.ImageView" content-desc="Motion" clickable="true" bounds="[1400,390][1480,450]" />
<node index="5" text="Rock &amp; Roll" resource-id="" class="android.widget.TextView" content-desc="" clickable="false" bounds="[380,500][560,520]" />
</node></hierarchy>"""

DUMP_SCROLLED = DUMP_TOP.replace('AURORA BOREALIS', 'ORBIT')


class ParseTest(unittest.TestCase):
    def test_parse(self):
        nodes = parse_ui(DUMP_TOP)
        labels = [n.label for n in nodes]
        self.assertIn('Save "Moog Bass" as Mine', labels)
        self.assertIn('Motion', labels)          # content-desc when there's no text
        self.assertIn('Rock & Roll', labels)     # entities decoded
        save = next(n for n in nodes if n.resource_id == 'save')
        self.assertEqual(save.bounds, (213, 212, 566, 260))
        self.assertEqual(save.center, (389, 236))
        self.assertTrue(save.clickable)

    def test_find(self):
        d = Device(dry_run=True)
        nodes = parse_ui(DUMP_TOP)
        self.assertEqual(d.find('presets', nodes).center, (118, 180))      # case-insensitive
        self.assertIsNone(d.find('Moog', nodes))                            # exact by default
        self.assertIsNotNone(d.find('Moog', nodes, contains=True))
        self.assertIsNone(d.find('Presets', nodes, region=(300, 0, 1600, 720)))


class DeviceTest(unittest.TestCase):
    def test_scroll_to_swipes_until_found(self):
        d = Device(dry_run=True)
        d.fake_dumps = [DUMP_TOP, DUMP_TOP, DUMP_SCROLLED, DUMP_SCROLLED]
        n = d.scroll_to('ORBIT', (380, 330, 700, 700))
        self.assertEqual(n.label, 'ORBIT')
        self.assertEqual(sum('input swipe' in c for c in d.log), 2)

    def test_scroll_to_gives_up(self):
        d = Device(dry_run=True)
        with self.assertRaises(LookupError):
            d.scroll_to('NOPE', (380, 330, 700, 700), max_swipes=2)

    def test_commands(self):
        d = Device('ABC123', dry_run=True)
        d.hold(780, 640, 10000)
        d.drag_path([(508, 300), (508, 240), (508, 180)], 250)
        d.start_recording(20)
        self.assertEqual(d.log[0], 'adb -s ABC123 shell input swipe 780 640 780 640 10000')
        self.assertIn('input swipe 508 300 508 240 250 ; input swipe 508 240 508 180 250', d.log[1])
        self.assertTrue(any('screenrecord --time-limit 21 --bit-rate 6000000' in c for c in d.log))


SPEC = {
    'out': 'takes/orbit',
    'record': {'android': {'seconds': 20}, 'mac_window': {'title': 'Drone Synth', 'seconds': 18}},
    'steps': [
        {'lock_landscape': True},
        {'tap_label': 'Presets'},
        {'start': True},
        {'wait': 3},
        {'tap': [407, 452], 'mark': 'load'},
        {'hold': [780, 640, 10000], 'mark': 'key'},
        {'stop': True},
    ],
}


class TakeTest(unittest.TestCase):
    def test_validate(self):
        self.assertEqual(validate(SPEC), [])
        self.assertTrue(validate({'steps': []}))
        bad = json.loads(json.dumps(SPEC))
        bad['steps'][5]['hold'] = [1, 2]
        bad['steps'].append({'jump': True})
        problems = validate(bad)
        self.assertTrue(any('hold' in p for p in problems))
        self.assertTrue(any('jump' in p for p in problems))

    def test_dry_run(self):
        t = Take(SPEC, dry_run=True)
        t.device.fake_dumps = [DUMP_TOP]
        r = t.run()
        self.assertEqual(set(r['marks']), {'recording_started', 'load', 'key'})
        self.assertLessEqual(r['marks']['recording_started'], r['marks']['key'])
        self.assertEqual(r['files']['mac_window'], 'takes/orbit/window.mov')
        self.assertTrue(any(c.startswith('macwinrec --title Drone Synth --seconds 18') for c in t.log))
        self.assertTrue(any('input tap 118 180' in c for c in t.device.log))  # tapped Presets by its label

    def test_cli_validate(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'spec.json')
            json.dump(SPEC, open(path, 'w'))
            self.assertEqual(main(['take', path, '--validate']), 0)
            json.dump({'steps': [{'hold': [1]}]}, open(path, 'w'))
            self.assertEqual(main(['take', path, '--validate']), 1)


class SimulatorTest(unittest.TestCase):
    def test_commands(self):
        from promocap import Simulator
        s = Simulator(dry_run=True)
        s.status_bar()
        s.start_recording('out.mp4')
        self.assertIn('status_bar booted override --time 9:41', s.log[0])
        self.assertIn('--batteryLevel 100', s.log[0])
        self.assertEqual(s.log[1], 'xcrun simctl io booted recordVideo --codec=h264 --force out.mp4')


if __name__ == '__main__':
    unittest.main()
