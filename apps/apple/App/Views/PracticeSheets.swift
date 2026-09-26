import PlaybackKit
import ScoreKit
import SwiftUI
import TranscriptionKit
import UniformTypeIdentifiers

/// Per-part mute and solo, your part for play-along, transpose and room.
struct MixerView: View {
    @Bindable var model: PracticeModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker(selection: $model.myPart) {
                        ForEach(model.score.parts) { p in Text(p.name).tag(String?.some(p.id)) }
                    } label: { Text("My part") }
                    Toggle(isOn: $model.playAlong) { Text("Play along (mute my part)") }
                } header: { Text("Play along") }

                Section {
                    ForEach(model.score.parts) { p in
                        HStack {
                            Text(p.name).frame(maxWidth: .infinity, alignment: .leading)
                            Toggle(isOn: Binding(get: { model.isMuted(p.id) }, set: { model.setMuted(p.id, $0) })) { Text("Mute") }
                                .toggleStyle(.button)
                                .accessibilityLabel(Text("Mute \(p.name)"))
                            Toggle(isOn: Binding(get: { model.isSoloed(p.id) }, set: { model.setSoloed(p.id, $0) })) { Text("Solo") }
                                .toggleStyle(.button)
                                .accessibilityLabel(Text("Solo \(p.name)"))
                        }
                    }
                } header: { Text("Parts") }

                Section {
                    Stepper(value: $model.transpose, in: -12...12) {
                        Text("Transpose \(model.transpose > 0 ? "+" : "")\(model.transpose) semitones")
                    }
                    Toggle(isOn: $model.room) { Text("Concert hall and seating") }
                    LabeledContent { Text(model.soundDescription) } label: { Text("Sounds") }
                } header: { Text("Sound") }
            }
            .formStyle(.grouped)
            .navigationTitle(Text("Parts and sound"))
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .frame(minWidth: 420, minHeight: 520)
    }
}

/// The talking score: navigable by part and bar, with pitch, duration and confidence,
/// and a button to play each bar.
struct TalkingScoreView: View {
    @Bindable var model: PracticeModel
    @Environment(\.dismiss) private var dismiss
    @State private var partID: String = ""

    var body: some View {
        NavigationStack {
            List {
                Picker(selection: $partID) {
                    ForEach(model.score.parts) { p in Text(p.name).tag(p.id) }
                } label: { Text("Part") }
                ForEach(model.score.measures.indices, id: \.self) { i in
                    HStack(alignment: .top) {
                        Text(model.describe(partID: partID, bar: i))
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Button { model.goToBar(i); if !model.isPlaying { model.togglePlay() } } label: {
                            Image(systemName: "play.circle")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel(Text("Play \(model.barLabel(i))"))
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: Text("Play this bar")) { model.goToBar(i); if !model.isPlaying { model.togglePlay() } }
                }
            }
            .formStyle(.grouped)
            .navigationTitle(Text("Talking score"))
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .onAppear { if partID.isEmpty { partID = model.shownPart ?? model.myPart ?? model.score.parts.first?.id ?? "" } }
        }
        .frame(minWidth: 480, minHeight: 560)
    }
}

/// Exports: MusicXML, PDF, MIDI, audio, talking-score text and braille.
struct ExportView: View {
    @Bindable var model: PracticeModel
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var busy: String?
    @State private var document: ExportFile?
    @State private var message: String?

    var body: some View {
        NavigationStack {
            List {
                row(String(localized: "MusicXML (score and parts)"), "doc.richtext", kind: .musicXML)
                row(String(localized: "PDF"), "doc", kind: .pdf)
                row(String(localized: "MIDI"), "pianokeys", kind: .midi)
                row(String(localized: "Audio of the score"), "waveform", kind: .audio)
                row(String(localized: "Talking score (text)"), "text.bubble", kind: .talkingScore)
                row(String(localized: "Braille music (BRF)"), "hand.point.up.braille", kind: .brailleBRF)
                if let message { Text(message).foregroundStyle(.secondary) }
            }
            .formStyle(.grouped)
            .navigationTitle(Text("Export"))
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .fileExporter(isPresented: Binding(get: { document != nil }, set: { if !$0 { document = nil } }),
                          document: document, contentType: document?.type ?? .data, defaultFilename: document?.name) { result in
                if case .failure(let e) = result { message = e.localizedDescription }
                document = nil
            }
        }
        .frame(minWidth: 420, minHeight: 420)
    }

    func row(_ title: String, _ icon: String, kind: ArtifactKind) -> some View {
        Button { Task { await export(kind) } } label: {
            HStack {
                Label(title, systemImage: icon)
                Spacer()
                if busy == kind.rawValue { ProgressView() }
            }
        }
        .disabled(busy != nil)
        .accessibilityIdentifier("export-\(kind.rawValue)")
    }

    func export(_ kind: ArtifactKind) async {
        busy = kind.rawValue
        defer { busy = nil }
        let base = model.piece.title
        do {
            switch kind {
            case .musicXML:
                document = ExportFile(data: try Data(contentsOf: model.piece.scoreURL), type: UTType(filenameExtension: "musicxml") ?? .xml, name: base + ".musicxml")
            case .midi:
                let data = MIDIWriter.data(for: model.score, options: .init(transposeSemitones: model.transpose))
                document = ExportFile(data: data, type: .midi, name: base + ".mid")
            case .talkingScore:
                var t = model.talking
                t.pitchMode = model.pitchMode
                document = ExportFile(data: Data(t.text().utf8), type: .plainText, name: base + " – talking score.txt")
            case .audio:
                let url = FileManager.default.temporaryDirectory.appending(path: base + ".m4a")
                try? FileManager.default.removeItem(at: url)
                let score = model.score, tm = model.composition?.tempoMap
                let muted = model.score.parts.filter { model.isMuted($0.id) }.map(\.id)
                try await Task.detached {
                    let e = try PlaybackEngine(score: score, tempoMap: tm, soundBank: .locate(), offlineFormat: PlaybackEngine.offlineFormat())
                    for id in muted { e.setMuted(id, true) }
                    try e.exportScore(to: url)
                }.value
                document = ExportFile(data: try Data(contentsOf: url), type: .mpeg4Audio, name: base + ".m4a")
            case .pdf, .brailleBRF, .composition:
                document = ExportFile(data: try await remote(kind), type: kind == .pdf ? .pdf : .data, name: base + "." + kind.fileExtension)
            }
        } catch {
            message = error.localizedDescription
        }
    }

    /// PDF and BRF come from the engine (or the demo folder); the app does not engrave PDF or braille itself.
    func remote(_ kind: ArtifactKind) async throws -> Data {
        if let dir = model.piece.fixtureDirectory {
            return try await FixtureService(directory: URL(fileURLWithPath: dir), stepDelay: 0).artifact(kind, jobID: "fixture")
        }
        guard let job = model.piece.remoteJobID, model.piece.remoteArtifacts.contains(kind) else {
            throw TranscriptionError.artifactUnavailable(kind)
        }
        return try await app.service().artifact(kind, jobID: job)
    }
}

struct ExportFile: FileDocument {
    static var readableContentTypes: [UTType] { [.data] }
    var data: Data
    var type: UTType
    var name: String
    init(data: Data, type: UTType, name: String) { self.data = data; self.type = type; self.name = name }
    init(configuration: ReadConfiguration) throws { data = configuration.file.regularFileContents ?? Data(); type = .data; name = "file" }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}
