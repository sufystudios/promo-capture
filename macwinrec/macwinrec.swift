// macwinrec: records one macOS window, and its app's own audio, to a .mov (ScreenCaptureKit, macOS 15+).
//
//   macwinrec --list
//   macwinrec --title "Drone Synth" --seconds 20 --out take.mov [--app CrossOver] [--fps 30] [--scale 2] [--no-audio] [--cursor]
//
// Prints one JSON object per line: {"event":"window",...} {"event":"started","epoch":...} {"event":"finished",...}
// "epoch" (seconds since 1970) is when the first frame was written: line it up with timestamps
// your take script logs (time.time() in Python), or better, with events (see event-sync).
// The app's audio is captured before the system volume, so you can mute the Mac and still record it.
// Windows apps running in CrossOver/Wine are ordinary windows here.
import AppKit
import AVFoundation
import Foundation
import ScreenCaptureKit

let _app = NSApplication.shared  // ScreenCaptureKit needs a connection to the window server
setvbuf(stdout, nil, _IOLBF, 0)

func emit(_ d: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: d, options: [.sortedKeys]),
       let s = String(data: data, encoding: .utf8) { print(s) }
}

func fail(_ code: Int32, _ message: String) -> Never {
    emit(["event": "error", "message": message]); exit(code)
}

var opts: [String: String] = [:]
var flags = Set<String>()
var it = CommandLine.arguments.dropFirst().makeIterator()
while let a = it.next() {
    switch a {
    case "--list", "--no-audio", "--cursor", "--help", "-h": flags.insert(a)
    case "--title", "--app", "--seconds", "--out", "--fps", "--scale":
        guard let v = it.next() else { fail(1, "\(a) needs a value") }
        opts[a] = v
    default: fail(1, "unknown argument \(a)")
    }
}
if flags.contains("--help") || flags.contains("-h") {
    print("usage: macwinrec --list | --title TEXT [--app NAME] --seconds S --out FILE.mov [--fps 30] [--scale 2] [--no-audio] [--cursor]")
    exit(0)
}

final class Recorder: NSObject, SCRecordingOutputDelegate, SCStreamDelegate, SCStreamOutput {
    var out: URL?
    func recordingOutputDidStartRecording(_ r: SCRecordingOutput) {
        emit(["event": "started", "epoch": Date().timeIntervalSince1970])
    }
    func recordingOutput(_ r: SCRecordingOutput, didFailWithError e: Error) { fail(3, "recording failed: \(e)") }
    func recordingOutputDidFinishRecording(_ r: SCRecordingOutput) {
        emit(["event": "finished", "out": out?.path ?? ""]); exit(0)
    }
    func stream(_ s: SCStream, didStopWithError e: Error) { fail(3, "stream stopped: \(e)") }
    func stream(_ s: SCStream, didOutputSampleBuffer b: CMSampleBuffer, of t: SCStreamOutputType) {}
}

let recorder = Recorder()

Task {
    do {
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
        if flags.contains("--list") {
            for w in content.windows where (w.title ?? "").isEmpty == false && w.frame.width > 50 {
                emit(["event": "window", "id": Int(w.windowID), "title": w.title ?? "",
                      "app": w.owningApplication?.applicationName ?? "",
                      "frame": [w.frame.origin.x, w.frame.origin.y, w.frame.width, w.frame.height],
                      "on_screen": w.isOnScreen])
            }
            exit(0)
        }
        guard let title = opts["--title"], let secsText = opts["--seconds"], let secs = Double(secsText),
              let outPath = opts["--out"] else { fail(1, "need --title, --seconds and --out (or --list)") }
        let app = opts["--app"]
        let matches = content.windows.filter {
            ($0.title ?? "").localizedCaseInsensitiveContains(title) &&
            (app == nil || ($0.owningApplication?.applicationName ?? "").localizedCaseInsensitiveContains(app!))
        }.sorted { $0.frame.width * $0.frame.height > $1.frame.width * $1.frame.height }
        guard let w = matches.first else { fail(2, "no window whose title contains \"\(title)\"") }
        if CGDisplayIsAsleep(CGMainDisplayID()) != 0 {
            // Seen in practice: with the display asleep the first frame never comes, and
            // ScreenCaptureKit fails with RPRecordingErrorDomain -5822.
            fail(4, "the display is asleep, so there's nothing to record: wake it (e.g. caffeinate -u -t 2) and try again")
        }
        let scale = Double(opts["--scale"] ?? "2") ?? 2
        let fps = Int32(opts["--fps"] ?? "30") ?? 30
        emit(["event": "window", "id": Int(w.windowID), "title": w.title ?? "",
              "app": w.owningApplication?.applicationName ?? "",
              "frame": [w.frame.origin.x, w.frame.origin.y, w.frame.width, w.frame.height],
              "pixels": [Int(w.frame.width * scale), Int(w.frame.height * scale)]])

        let out = URL(fileURLWithPath: outPath)
        try? FileManager.default.removeItem(at: out)
        recorder.out = out
        let cfg = SCStreamConfiguration()
        cfg.width = Int(w.frame.width * scale)
        cfg.height = Int(w.frame.height * scale)
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: fps)
        cfg.capturesAudio = !flags.contains("--no-audio")
        cfg.sampleRate = 48000
        cfg.channelCount = 2
        cfg.showsCursor = flags.contains("--cursor")
        cfg.ignoreShadowsSingleWindow = true
        let stream = SCStream(filter: SCContentFilter(desktopIndependentWindow: w), configuration: cfg, delegate: recorder)
        try stream.addStreamOutput(recorder, type: .screen, sampleHandlerQueue: .global())
        if cfg.capturesAudio { try stream.addStreamOutput(recorder, type: .audio, sampleHandlerQueue: .global()) }
        let rc = SCRecordingOutputConfiguration()
        rc.outputURL = out
        rc.outputFileType = .mov
        rc.videoCodecType = .h264
        try stream.addRecordingOutput(SCRecordingOutput(configuration: rc, delegate: recorder))
        try await stream.startCapture()
        try await Task.sleep(nanoseconds: UInt64(secs * 1e9))
        try await stream.stopCapture()
        try await Task.sleep(nanoseconds: 3_000_000_000)
        fail(3, "the recording didn't finish")
    } catch {
        fail(3, "\(error)")
    }
}
RunLoop.main.run()
