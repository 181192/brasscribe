import ScoreKit
import SwiftUI
import TranscriptionKit
import UniformTypeIdentifiers

struct HomeView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        @Bindable var app = app
        List {
            Section {
                Button { app.importing = true } label: {
                    Label("Import audio or video", systemImage: "square.and.arrow.down")
                }
                .accessibilityIdentifier("import")
                Button { app.showRecorder = true } label: { Label("Record with the microphone", systemImage: "mic") }
                    .accessibilityIdentifier("record")
                #if os(macOS)
                Button { app.showCapture = true } label: { Label("Record sound playing on this Mac", systemImage: "speaker.wave.2") }
                    .accessibilityIdentifier("capture")
                #endif
                if app.fixtureDirectory != nil {
                    Button { app.startDemo() } label: { Label("Try the demo (Mikkel)", systemImage: "music.note.list") }
                        .accessibilityIdentifier("demo")
                }
            } header: { Text("New score") } footer: {
                Text("Links to streaming sites can't be downloaded. Play the music and record it, or import a file you have.")
            }

            Section {
                if app.pieces.isEmpty {
                    Text("Your scores appear here.").foregroundStyle(.secondary)
                }
                ForEach(app.pieces) { p in
                    NavigationLink(value: Route.score(p)) {
                        VStack(alignment: .leading) {
                            Text(p.title).font(.headline)
                            Text(p.created, style: .date).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .contextMenu {
                        Button { app.path.append(.review(p)) } label: { Label("Review", systemImage: "checklist") }
                        Button(role: .destructive) { app.delete(p) } label: { Label("Delete", systemImage: "trash") }
                    }
                    .accessibilityIdentifier("piece-\(p.title)")
                }
                .onDelete { idx in idx.map { app.pieces[$0] }.forEach(app.delete) }
            } header: { Text("Scores") }
        }
        .navigationTitle(Text("Brasscribe Play"))
        .toolbar {
            ToolbarItem { Button { app.showSettings = true } label: { Label("Settings", systemImage: "gear") } }
        }
        .fileImporter(isPresented: $app.importing, allowedContentTypes: [.audio, .movie, .xml, UTType(filenameExtension: "musicxml") ?? .xml]) { result in
            if case .success(let url) = result { Task { await app.accept(url: url) } }
        }
    }
}

/// "What is this?" — the choice picks the pipeline profile; nothing is preselected.
/// Then the output: lineup, difficulty and key.
struct SourceSheet: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    let source: PendingSource
    @State private var profile: SourceProfile?
    @State private var output = OutputChoice()
    @State private var keepKey = true
    @State private var key = 0

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    ForEach(SourceProfile.allCases) { p in
                        Button { profile = p } label: {
                            HStack {
                                Image(systemName: p.symbol).frame(width: 28)
                                VStack(alignment: .leading) {
                                    Text(p.title).font(.headline)
                                    Text(p.detail).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if profile == p { Image(systemName: "checkmark.circle.fill").foregroundStyle(.tint) }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(profile == p ? .isSelected : [])
                        .accessibilityIdentifier("profile-\(p.rawValue)")
                    }
                } header: { Text("What is this?") } footer: {
                    Text("This decides how the music is taken apart. Brasscribe never guesses.")
                }

                Section {
                    Picker(selection: $output.lineup) {
                        Text("Full brass band").tag(Lineup.fullBand)
                        Text("Small band").tag(Lineup.minimalBand)
                    } label: { Text("Lineup") }
                    Picker(selection: $output.difficulty) {
                        Text("Faithful").tag(Difficulty.faithful)
                        Text("Standard").tag(Difficulty.standard)
                        Text("Easier").tag(Difficulty.easier)
                    } label: { Text("Difficulty") }
                    Toggle(isOn: $keepKey) { Text("Keep the original key") }
                    if !keepKey {
                        Picker(selection: $key) {
                            ForEach(-6...6, id: \.self) { f in Text(KeyNames.name(fifths: f)).tag(f) }
                        } label: { Text("Key (concert)") }
                    }
                } header: { Text("Score") } footer: {
                    Text("Lineup, difficulty and key are sent to your computer; older versions of Brasscribe may ignore them.")
                }
            }
            .formStyle(.grouped)
            .navigationTitle(Text(source.title))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { app.pending = nil } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Transcribe") {
                        guard let profile else { return }
                        output.keyFifths = keepKey ? nil : key
                        app.startTranscription(source, profile: profile, output: output)
                    }
                    .disabled(profile == nil)
                    .accessibilityIdentifier("transcribe")
                }
            }
        }
        .frame(minWidth: 460, minHeight: 560)
    }
}

extension SourceProfile {
    var title: String {
        switch self {
        case .solo: return String(localized: "One instrument")
        case .brassBand: return String(localized: "Brass band")
        case .orchestraWithSoloist: return String(localized: "Orchestra or band with a soloist")
        case .popRock: return String(localized: "Pop or rock")
        }
    }
    var detail: String {
        switch self {
        case .solo: return String(localized: "A single player, for example you practising.")
        case .brassBand: return String(localized: "A brass band playing together.")
        case .orchestraWithSoloist: return String(localized: "A soloist in front of an orchestra or band.")
        case .popRock: return String(localized: "Vocals or lead with bass, drums and keys.")
        }
    }
    var symbol: String {
        switch self {
        case .solo: return "person"
        case .brassBand: return "person.3"
        case .orchestraWithSoloist: return "person.2.wave.2"
        case .popRock: return "guitars"
        }
    }
}

enum KeyNames {
    static func name(fifths: Int) -> String {
        let en = ["G♭", "D♭", "A♭", "E♭", "B♭", "F", "C", "G", "D", "A", "E", "B", "F♯"]
        let nb = ["Gess", "Dess", "Ass", "Ess", "B", "F", "C", "G", "D", "A", "E", "H", "Fiss"]
        let i = max(0, min(12, fifths + 6))
        let names = ScoreLanguage.current == .norwegian ? nb : en
        return names[i] + (ScoreLanguage.current == .norwegian ? "-dur" : " major")
    }
}

/// Plain-language progress with estimated time and cancel.
struct TranscribeView: View {
    @Environment(AppModel.self) private var app
    let jobID: UUID

    var body: some View {
        if let job = app.jobs[jobID] {
            VStack(spacing: 20) {
                Spacer()
                ProgressView(value: job.progress.fraction) {
                    Text(job.progress.stage.plain).font(.title3)
                } currentValueLabel: {
                    Text(eta(job.progress)).monospacedDigit()
                }
                .frame(maxWidth: 480)
                .accessibilityIdentifier("transcriptionProgress")
                Text("Transcribing on \(job.service.displayName)").font(.caption).foregroundStyle(.secondary)
                if let f = job.failure {
                    Text(f).foregroundStyle(.red).multilineTextAlignment(.center)
                    Button("Back") { app.path.removeLast() }
                } else if job.cancelled {
                    Text("Cancelled.")
                    Button("Back") { app.path.removeLast() }
                } else {
                    Button(role: .cancel) { job.cancel() } label: { Text("Cancel") }
                        .keyboardShortcut(.cancelAction)
                        .accessibilityIdentifier("cancelTranscription")
                }
                Spacer()
            }
            .padding()
            .navigationTitle(job.source.title)
            .onChange(of: job.progress.stage) { _, s in AccessibilityNotifier.announce(s.plain) }
        } else {
            ProgressView()
        }
    }

    func eta(_ p: TranscriptionProgress) -> String {
        guard let s = p.etaSeconds else { return String(localized: "Estimating time…") }
        if s < 60 { return String(localized: "Less than a minute left") }
        return String(localized: "About \(Int((s / 60).rounded())) min left")
    }
}

extension StageKind {
    var plain: String {
        switch self {
        case .uploading: return String(localized: "Sending the recording")
        case .preparing: return String(localized: "Getting the recording ready")
        case .separating: return String(localized: "Separating the instruments")
        case .findingBeat: return String(localized: "Finding the beat")
        case .transcribing: return String(localized: "Writing down the notes")
        case .arranging: return String(localized: "Arranging for brass band")
        case .engraving: return String(localized: "Engraving the score")
        case .rendering: return String(localized: "Making the audio")
        case .working: return String(localized: "Working")
        }
    }
}

/// Review before practising: uncertain notes per bar (colour and shape), free-time
/// passages as ad lib, and "listen to this bar" from the original and the score.
struct ReviewView: View {
    @Environment(AppModel.self) private var app
    let piece: Piece
    @State private var model: PracticeModel?

    var body: some View {
        Group {
            if let model {
                List {
                    Section {
                        LabeledContent { Text("\(model.score.parts.count)") } label: { Text("Parts") }
                        LabeledContent { Text("\(model.score.measures.count)") } label: { Text("Bars") }
                        LabeledContent { Text("\(uncertainBars(model).count)") } label: { Text("Bars with uncertain notes") }
                        HStack(spacing: 6) {
                            Diamond().stroke(Color(red: 0.835, green: 0.369, blue: 0), lineWidth: 1.5).frame(width: 10, height: 10)
                            Text("Uncertain notes are marked with an open diamond and an orange colour.")
                                .font(.caption)
                        }
                        .accessibilityElement(children: .combine)
                    }
                    if let free = model.composition?.freeTimeBeats, !free.isEmpty {
                        Section {
                            ForEach(Array(free.enumerated()), id: \.offset) { _, r in
                                let a = model.score.position(atTick: Int(r.lowerBound * 960)).bar
                                let b = model.score.position(atTick: Int(r.upperBound * 960)).bar
                                Text("Bars \(a)–\(b): ad lib (free time)").italic()
                            }
                        } header: { Text("Free time") } footer: {
                            Text("The performer did not keep a steady beat here, so rhythms are approximate.")
                        }
                    }
                    Section {
                        ForEach(uncertainBars(model), id: \.self) { bar in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(model.barLabel(bar)).font(.headline)
                                    Text("\(model.uncertainCount(bar: bar)) uncertain notes").font(.caption)
                                }
                                Spacer()
                                Button { model.listen(toBar: bar, original: true) } label: { Label("Original", systemImage: "waveform") }
                                    .disabled(!model.hasOriginal)
                                Button { model.listen(toBar: bar, original: false) } label: { Label("Score", systemImage: "music.note") }
                            }
                            .buttonStyle(.bordered)
                            .accessibilityElement(children: .contain)
                        }
                    } header: { Text("Listen to uncertain bars") }
                }
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Open score") { model.stopAll(); app.path.append(.score(piece)) }
                            .accessibilityIdentifier("openScore")
                    }
                }
            } else { ProgressView() }
        }
        .navigationTitle(Text("Review"))
        .task {
            if model == nil, let m = try? PracticeModel(piece: piece) { m.start(); model = m }
        }
        .onDisappear { model?.stopAll() }
    }

    func uncertainBars(_ m: PracticeModel) -> [Int] {
        m.score.measures.indices.filter { m.uncertainCount(bar: $0) > 0 }
    }
}

enum AccessibilityNotifier {
    @MainActor static func announce(_ s: String) {
        #if os(iOS)
        UIAccessibility.post(notification: .announcement, argument: s)
        #else
        NSAccessibility.post(element: NSApp as Any, notification: .announcementRequested,
                             userInfo: [.announcement: s, .priority: NSAccessibilityPriorityLevel.high.rawValue])
        #endif
    }
}
