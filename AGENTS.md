# AGENTS.md — promo-capture

Instructions for AI agents recording app footage with this repository.

## Contract

- `python3 -m promocap <android|ios|take> ...` (or `promocap` if installed). One JSON object on stdout.
- Exit codes: `0` ok · `1` failed (`{"error": "failed", "message": ...}`, includes adb errors and invalid specs) · `2` not found (a label or list item).
- `macwinrec` prints JSON lines: `{"event":"window"...}`, `{"event":"started","epoch":...}`, `{"event":"finished"}`, or `{"event":"error","message":...}`. Exit codes: 0 ok, 1 usage, 2 no such window, 3 recording failed, 4 display asleep.
- Android coordinates are pixels in the current orientation. Get them from `promocap android dump` or a screenshot, never by guessing from another device.

## Before a session

1. `adb devices` shows the phone; the screen is on and unlocked (`promocap android dump` fails clearly if not).
2. Lock the orientation (`promocap android landscape`) and repeat that right before each take: some phones (seen on a Moto E7) turn auto-rotate back on by themselves.
3. `promocap android demo-mode on` for a clean status bar; `off` afterwards.
4. For a desktop window: `macwinrec --list`, pick a title substring, and check the display is awake (exit 4 otherwise).
5. Tell the user what they'll notice: sounds playing, the phone's screen changing, windows appearing.

## The take spec

```json
{
  "out": "takes/orbit",
  "android": {"serial": null, "adb": "adb"},
  "ios_sim": {"udid": "booted"},
  "record": {
    "android": {"seconds": 20, "bitrate": 6000000},
    "ios_sim": {},
    "mac_window": {"title": "Drone Synth", "app": null, "seconds": 18, "binary": "macwinrec/macwinrec"}
  },
  "steps": [
    {"lock_landscape": true},
    {"tap_label": "Presets"},
    {"scroll_to": "ORBIT", "region": [380, 330, 700, 700]},
    {"start": true},
    {"wait": 3},
    {"tap_label": "ORBIT", "mark": "load"},
    {"hold": [780, 640, 10000], "mark": "key"},
    {"stop": true}
  ]
}
```

Step keys (several may share one step; they run in this order): `wait` s · `lock_landscape` / `lock_portrait` · `demo_mode` (+`clock`) · `launch` package · `scroll_to` label + `region` · `tap_label` (+`contains`) · `tap` [x,y] · `swipe` [x1,y1,x2,y2,ms] · `drag_path` [[x,y],...] (+`ms`) · `hold` [x,y,ms] · `shell` [args] · `screenshot` file · `start` · `stop`. Add `"mark": "name"` to any step to log the time just before it runs.

Always `--validate`, then `--dry-run`, before the first real run. Output: `<out>/take.json` with `marks` (epoch seconds), `files`, and `recorders` (macwinrec's events, including its `started.epoch`).

## Lessons from real takes

- **Don't trust clocks to line recordings up.** A phone playing a desktop app over Wi-Fi was heard 0.84–1.14 s late, different every take. The marks tell you roughly where to look; measure the real offset with event-sync (`offset`, or `align` on a moving knob).
- **Check the app's state before every take, not once.** Pressing a key closed an open drawer in one app, so the next take's search ran on the wrong screen for minutes. Re-open what you need at the start of each take, and check the result (e.g. the loaded item's name) after it.
- **`screenrecord` bitrate:** 6 Mbps. At 16 Mbps a low-end phone's UI dropped to ~3 fps and taps were lost.
- **adb has no multi-touch or curved gestures** without root (`sendevent` is denied). Chain short swipes (`drag_path`). Many knob controls are vertical drags (up = more), not angle-following: test on one knob first.
- **The UI dump can contain text in single quotes** (`text='Save "X" as Mine'`) and HTML entities: `parse_ui` handles both; regexes written by hand often don't.
- **`uiautomator dump` takes about a second** and fails on a locked or sleeping screen.
- **macwinrec needs the display awake.** With it asleep, ScreenCaptureKit fails on the first frame (RPRecordingErrorDomain -5822); macwinrec checks first and exits 4.
- **Several things on the same MIDI/network session hear each other.** A test client sending into a shared session changed the phone's own sound. Keep test traffic off sessions a real device is on, or put the app's state back afterwards.
- **Disk space:** video takes add up. Check free space before a batch; a full disk fails silently in places.

## Changing the code

`promocap/android.py` (Device, parse_ui), `promocap/ios.py` (Simulator), `promocap/take.py` (spec, validate, Take), `promocap/cli.py`, `macwinrec/macwinrec.swift`. Every Device/Simulator call must work in `dry_run` (append to `.log`, touch nothing), so it can be tested. Add tests in `tests/test_promocap.py`.
