# promo-capture

Script the footage for app promo videos: the same tap, scroll and key press in every take, with every recorder started together and every moment written down.

- **Android** over adb: find things on screen by their label, tap, scroll a list until an item appears, hold a key, lock the orientation, tidy the status bar (demo mode), screenshots and screen recording.
- **iOS Simulator**: Apple's 9:41 status bar, dark/light mode, launch, screenshots, video.
- **macOS windows, with the app's own audio** (`macwinrec`, ScreenCaptureKit): a desktop app or plugin window, or a **Windows** app running in CrossOver/Wine. The audio is taken before the system volume, so you can mute the Mac and still record.
- **Takes from a JSON spec**: steps run in order, recorders start and stop around them, and `take.json` records when each step happened.

```
promocap android scroll-to "ORBIT" --region 380,330,700,700
promocap android tap-label "ORBIT"
promocap ios status-bar
macwinrec/macwinrec --title "Drone Synth" --seconds 20 --out plugin.mov
promocap take examples/take-android-plus-window.json      # a whole take
promocap take examples/take-android-plus-window.json --dry-run   # what it would do
```

Made for the promo videos of [DroneSynth](https://play.google.com/store/apps/details?id=xyz.sufystudios.synthguide): an Android phone playing the free DroneSynth desktop plugin over Wi-Fi, recorded on both ends. Pair it with [event-sync](https://github.com/sufystudios/event-sync) to line the recordings up, and [promo-composer](https://github.com/sufystudios/promo-composer) to cut them into videos.

## Install

- Python 3.9+, no Python dependencies. `pip install git+https://github.com/sufystudios/promo-capture`, or run `python3 -m promocap` in a clone.
- Android: `adb` (Android SDK platform-tools), USB debugging on.
- iOS Simulator: Xcode (`xcrun simctl`).
- macOS windows: `sh macwinrec/build.sh` (Xcode command line tools), macOS 15+. The first recording asks for Screen Recording permission for your terminal.

## Commands

| Command | Does |
|---|---|
| `promocap android dump` | everything labelled on screen, with centres and bounds |
| `promocap android find LABEL [--contains] [--region l,t,r,b]` | where one element is |
| `promocap android tap-label LABEL` | tap it by its text or content description |
| `promocap android scroll-to LABEL --region l,t,r,b` | scroll that list until LABEL is fully in view |
| `promocap android landscape\|portrait` | lock the orientation (retries until it holds) |
| `promocap android demo-mode on\|off [--clock 0900]` | tidy status bar |
| `promocap android screenshot OUT.png` / `record OUT.mp4 --seconds 20` | capture |
| `promocap ios status-bar [clear]` / `appearance dark\|light` / `screenshot OUT.png` / `record OUT.mp4 --seconds 10` | Simulator |
| `promocap take SPEC.json [--dry-run\|--validate]` | run a scripted take |
| `macwinrec --list` / `macwinrec --title T --seconds S --out F.mov [--app A] [--no-audio]` | record a window and its audio |

All print JSON. See [AGENTS.md](AGENTS.md) for the take spec, and for what goes wrong on real devices.

## Tests

```
python3 -m unittest discover -s tests -v
```

They need no device: dry-run devices and sample UI dumps.

## License

MIT. See [LICENSE](LICENSE).
