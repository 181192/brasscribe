# capture: system and per-app audio on macOS

A Core Audio process tap that records what another application is playing, so a
transcription can start from the sound card instead of a microphone. Brasscribe
Play for macOS uses the `AudioCapture` library; `brasscribe-capture` is the same
code as a command-line tool.

macOS 15 or newer, Xcode 16 or newer.

## Build

```sh
make            # bin/brasscribe-capture, release, ad-hoc signed
make test       # swift test
make clean
```

The build embeds `Info.plist` in the executable so the
`NSAudioCaptureUsageDescription` prompt can name the tool. The first run asks
for audio-recording permission; grant it in System Settings → Privacy &
Security → Screen & System Audio Recording.

## Run

```sh
bin/brasscribe-capture --list                                   # apps that can be tapped, and what is playing
bin/brasscribe-capture --out take.wav                           # global stereo mixdown, stop with Ctrl-C
bin/brasscribe-capture --out take.wav --seconds 30              # stop after 30 s
bin/brasscribe-capture --out take.wav --bundle-id com.spotify.client
```

Without `--bundle-id` it records everything playing. It stops on `--seconds`,
SIGINT or SIGTERM, and prints the duration and peak level. A silent capture is
reported as a warning — it usually means permission was denied, nothing was
playing, or the source is protected content.

## End to end

```sh
make
bin/brasscribe-capture --out /tmp/take.wav --seconds 30
cd .. && pixi run brasscribe run /tmp/take.wav --out data/runs/capture-check
```
