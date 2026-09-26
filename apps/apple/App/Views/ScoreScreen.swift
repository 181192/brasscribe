import AVKit
import ScoreKit
import SwiftUI

/// Score, parts and practice: notation with cursor, transport, mixer, loop, speed,
/// count-in, metronome, transpose, play-along and original-vs-score with synced video.
struct ScoreScreen: View {
    let piece: Piece
    @State private var model: PracticeModel?
    @State private var error: String?

    var body: some View {
        Group {
            if let model {
                PracticeView(model: model)
            } else if let error {
                ContentUnavailableView(String(localized: "Couldn't open the score"), systemImage: "exclamationmark.triangle", description: Text(error))
            } else {
                ProgressView()
            }
        }
        .navigationTitle(piece.title)
        .task {
            guard model == nil else { return }
            do {
                let m = try PracticeModel(piece: piece)
                m.start()
                model = m
            } catch { self.error = error.localizedDescription }
        }
        .onDisappear { model?.stopAll() }
    }
}

struct PracticeView: View {
    @Bindable var model: PracticeModel
    @State private var showMixer = false
    @State private var showTalking = false
    @State private var showExport = false
    @State private var showVideo = true
    @Environment(\.horizontalSizeClass) private var hsize

    var body: some View {
        VStack(spacing: 0) {
            ScoreToolbar(model: model, showMixer: $showMixer, showTalking: $showTalking, showExport: $showExport)
            Divider()
            ZStack(alignment: .bottomTrailing) {
                NotationView(model: model)
                if let player = model.video, showVideo {
                    VideoPiP(player: player)
                        .frame(width: hsize == .compact ? 160 : 280, height: hsize == .compact ? 90 : 158)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .shadow(radius: 4)
                        .padding(12)
                        .accessibilityLabel(Text("Video of the performance, synced to the score"))
                }
            }
            Divider()
            TransportBar(model: model)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(model.piece.title))
        .sheet(isPresented: $showMixer) { MixerView(model: model) }
        .sheet(isPresented: $showTalking) { TalkingScoreView(model: model) }
        .sheet(isPresented: $showExport) { ExportView(model: model) }
        .alert(String(localized: "Playback problem"), isPresented: Binding(get: { model.loadError != nil }, set: { _ in })) {
            Button("OK") {}
        } message: { Text(model.loadError ?? "") }
    }
}

struct ScoreToolbar: View {
    @Bindable var model: PracticeModel
    @Binding var showMixer: Bool
    @Binding var showTalking: Bool
    @Binding var showExport: Bool

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { controls }.padding(.horizontal).padding(.vertical, 8)
            ScrollView(.horizontal) { HStack(spacing: 12) { controls }.padding(.horizontal).padding(.vertical, 8) }
        }
    }

    @ViewBuilder var controls: some View {
        Picker(selection: $model.shownPart) {
            Text("All parts").tag(String?.none)
            ForEach(model.score.parts) { p in Text(p.name).tag(String?.some(p.id)) }
        } label: { Text("Show") }
        .pickerStyle(.menu)
        .accessibilityIdentifier("partPicker")
        .fixedSize()

        Picker(selection: $model.pitchMode) {
            Text("Written").tag(PitchMode.written)
            Text("Concert").tag(PitchMode.concert)
        } label: { Text("Pitch") }
        .pickerStyle(.segmented)
        .fixedSize()
        .accessibilityIdentifier("pitchMode")

        HStack(spacing: 4) {
            Button { model.zoom = max(0.5, model.zoom - 0.25) } label: { Image(systemName: "minus.magnifyingglass").hitTarget() }
                .accessibilityLabel(Text("Zoom out"))
                .keyboardShortcut("-", modifiers: .command)
            Text("\(Int(model.zoom * 100)) %").monospacedDigit().frame(minWidth: 48)
                .accessibilityLabel(Text("Zoom \(Int(model.zoom * 100)) percent"))
            Button { model.zoom = min(4, model.zoom + 0.25) } label: { Image(systemName: "plus.magnifyingglass").hitTarget() }
                .accessibilityLabel(Text("Zoom in"))
                .keyboardShortcut("+", modifiers: .command)
        }
        .fixedSize()

        Spacer(minLength: 8)
        Button { showMixer = true } label: { Label("Parts and sound", systemImage: "slider.horizontal.3") }
            .keyboardShortcut("p", modifiers: [.command, .shift])
        Button { showTalking = true } label: { Label("Talking score", systemImage: "text.bubble") }
            .keyboardShortcut("t", modifiers: [.command, .shift])
        Button { showExport = true } label: { Label("Export", systemImage: "square.and.arrow.up") }
            .keyboardShortcut("e", modifiers: [.command, .shift])
    }
}

struct TransportBar: View {
    @Bindable var model: PracticeModel
    @Environment(\.horizontalSizeClass) private var hsize

    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 16) {
                Button { model.previousBar() } label: { Image(systemName: "backward.end.fill").hitTarget() }
                    .accessibilityLabel(Text("Previous bar"))
                    .keyboardShortcut(.leftArrow, modifiers: [])
                    .accessibilityIdentifier("previousBar")
                Button { model.togglePlay() } label: {
                    Image(systemName: model.isPlaying ? "pause.fill" : "play.fill").font(.title2).frame(minWidth: 44, minHeight: 44)
                }
                .accessibilityLabel(model.isPlaying ? Text("Pause") : Text("Play"))
                .keyboardShortcut(.space, modifiers: [])
                .accessibilityIdentifier("playPause")
                Button { model.nextBar() } label: { Image(systemName: "forward.end.fill").hitTarget() }
                    .accessibilityLabel(Text("Next bar"))
                    .keyboardShortcut(.rightArrow, modifiers: [])
                    .accessibilityIdentifier("nextBar")

                VStack(alignment: .leading, spacing: 0) {
                    if let b = model.countInBeat {
                        Text("Count-in \(b)").font(.headline)
                    } else {
                        Text(model.positionDescription).font(.headline).monospacedDigit().fixedSize()
                    }
                    Text(model.hearOriginal ? String(localized: "Original recording") : String(localized: "Score"))
                        .font(.caption.weight(.semibold))
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("position")
                .accessibilityValue(Text("\(model.currentBar + 1)"))
                .accessibilityAddTraits(.updatesFrequently)

                Spacer()

                Toggle(isOn: $model.hearOriginal) { Label("Original", systemImage: "waveform").hitTarget() }
                    .toggleStyle(.button)
                    .disabled(!model.hasOriginal)
                    .keyboardShortcut("o", modifiers: [])
                    .accessibilityHint(Text("Switch between the score and the original recording at the same place."))
                    .accessibilityIdentifier("originalToggle")
            }
            .labelStyle(AdaptiveLabelStyle(compact: hsize == .compact))

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 16) { practiceControls }
                VStack(alignment: .leading, spacing: 8) { practiceControls }
            }
        }
        .labelStyle(AdaptiveLabelStyle(compact: hsize == .compact))
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(.background)   // opaque, so text contrast does not depend on the score behind it
    }

    @ViewBuilder var practiceControls: some View {
        HStack {
            Button { model.changeSpeed(by: -5) } label: { Image(systemName: "tortoise").hitTarget() }
                .accessibilityLabel(Text("Slower"))
                .keyboardShortcut("[", modifiers: [])
            Slider(value: $model.speedPercent, in: 25...150, step: 5) { Text("Speed") }
                .frame(minWidth: 100, maxWidth: 180)
                .accessibilityValue(Text("\(Int(model.speedPercent)) percent"))
                .accessibilityIdentifier("speed")
            Button { model.changeSpeed(by: 5) } label: { Image(systemName: "hare").hitTarget() }
                .accessibilityLabel(Text("Faster"))
                .keyboardShortcut("]", modifiers: [])
            Text("\(Int(model.speedPercent)) %").monospacedDigit().frame(minWidth: 44).accessibilityHidden(true)
        }
        HStack(spacing: 6) {
            Toggle(isOn: Binding(get: { model.looping }, set: { model.setLoop($0) })) { Label("Loop", systemImage: "repeat").hitTarget() }
                .toggleStyle(.button)
                .keyboardShortcut("l", modifiers: [.shift])
                .accessibilityIdentifier("loopToggle")
            Stepper(value: $model.loopFrom, in: 0...(model.score.measures.count - 1)) {
                Text("from \(model.loopFrom + 1)").monospacedDigit()
            }
            .accessibilityLabel(Text("Loop from bar"))
            .accessibilityValue(Text("\(model.loopFrom + 1)"))
            .onChange(of: model.loopFrom) { if model.looping { model.setLoop(true) } }
            Stepper(value: $model.loopTo, in: 0...(model.score.measures.count - 1)) {
                Text("to \(model.loopTo + 1)").monospacedDigit()
            }
            .accessibilityLabel(Text("Loop to bar"))
            .accessibilityValue(Text("\(model.loopTo + 1)"))
            .onChange(of: model.loopTo) { if model.looping { model.setLoop(true) } }
        }
        .fixedSize()
        HStack {
            Toggle(isOn: $model.countIn) { Label("Count-in", systemImage: "1.circle").hitTarget() }.toggleStyle(.button)
                .keyboardShortcut("c", modifiers: [])
            Toggle(isOn: $model.metronome) { Label("Metronome", systemImage: "metronome").hitTarget() }.toggleStyle(.button)
                .keyboardShortcut("m", modifiers: [])
            Toggle(isOn: $model.playAlong) { Label("Play along", systemImage: "music.mic").hitTarget() }.toggleStyle(.button)
                .accessibilityHint(Text("Mutes your part so you can play it."))
                .keyboardShortcut("a", modifiers: [])
        }
        .fixedSize()
        // hidden button so plain L loops the current bar
        Button("") { model.toggleLoopCurrentBar() }.keyboardShortcut("l", modifiers: []).hidden().frame(width: 0).accessibilityHidden(true)
    }
}

/// Icon only in compact width (VoiceOver still reads the title), title and icon otherwise.
struct AdaptiveLabelStyle: LabelStyle {
    let compact: Bool
    func makeBody(configuration: Configuration) -> some View {
        if compact { Label(configuration).labelStyle(.iconOnly) } else { Label(configuration).labelStyle(.titleAndIcon) }
    }
}

/// Muted, synced video of the original performance with system picture-in-picture.
/// The synced video in a player layer with system picture in picture
/// (AVPictureInPictureController, iOS/iPadOS and macOS) and an explicit, labelled button
/// to start it. The video stays muted; the app's audio engine plays.
struct VideoPiP: View {
    let player: AVPlayer
    @State private var pip = PiPModel()

    var body: some View {
        ZStack(alignment: .topTrailing) {
            PlayerLayerView(player: player, pip: pip)
            Button {
                pip.toggle()
            } label: {
                Image(systemName: pip.active ? "pip.exit" : "pip.enter")
                    .padding(8)
                    .background(.ultraThinMaterial, in: Circle())
                    .hitTarget()
            }
            .buttonStyle(.plain)
            .disabled(!pip.possible)
            .accessibilityLabel(pip.active ? Text("Stop picture in picture") : Text("Picture in picture"))
            .accessibilityValue(Text(pip.possible ? "available" : "unavailable"))
            .accessibilityIdentifier("pipButton")
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("videoPlayer")
    }
}

@Observable @MainActor
final class PiPModel: NSObject, AVPictureInPictureControllerDelegate {
    var controller: AVPictureInPictureController?
    var possible = false
    var active = false
    private var observation: NSKeyValueObservation?

    func attach(_ layer: AVPlayerLayer) {
        guard controller == nil, AVPictureInPictureController.isPictureInPictureSupported(),
              let c = AVPictureInPictureController(playerLayer: layer) else { return }
        c.delegate = self
        controller = c
        observation = c.observe(\.isPictureInPicturePossible, options: [.initial, .new]) { [weak self] c, _ in
            let p = c.isPictureInPicturePossible
            Task { @MainActor in self?.possible = p }
        }
    }

    func toggle() {
        guard let c = controller else { return }
        if c.isPictureInPictureActive { c.stopPictureInPicture() } else { c.startPictureInPicture() }
    }

    nonisolated func pictureInPictureControllerDidStartPictureInPicture(_ c: AVPictureInPictureController) {
        Task { @MainActor in self.active = true }
    }
    nonisolated func pictureInPictureControllerDidStopPictureInPicture(_ c: AVPictureInPictureController) {
        Task { @MainActor in self.active = false }
    }
}

#if os(iOS)
final class PlayerLayerUIView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }
    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
}

struct PlayerLayerView: UIViewRepresentable {
    let player: AVPlayer
    let pip: PiPModel
    func makeUIView(context: Context) -> PlayerLayerUIView {
        let v = PlayerLayerUIView()
        v.playerLayer.player = player
        v.playerLayer.videoGravity = .resizeAspect
        v.backgroundColor = .black
        pip.attach(v.playerLayer)
        return v
    }
    func updateUIView(_ v: PlayerLayerUIView, context: Context) { v.playerLayer.player = player }
}
#else
final class PlayerLayerNSView: NSView {
    let playerLayer = AVPlayerLayer()
    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer = playerLayer
        playerLayer.backgroundColor = NSColor.black.cgColor
        playerLayer.videoGravity = .resizeAspect
    }
    required init?(coder: NSCoder) { fatalError() }
}

struct PlayerLayerView: NSViewRepresentable {
    let player: AVPlayer
    let pip: PiPModel
    func makeNSView(context: Context) -> PlayerLayerNSView {
        let v = PlayerLayerNSView()
        v.playerLayer.player = player
        pip.attach(v.playerLayer)
        return v
    }
    func updateNSView(_ v: PlayerLayerNSView, context: Context) { v.playerLayer.player = player }
}
#endif

extension View {
    /// At least 44 × 44 pt to hit (WCAG 2.5.8 asks for 24; Apple's guideline is 44).
    func hitTarget() -> some View { frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
}
