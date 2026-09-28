import NotationKit
import PlaybackKit
import ScoreKit
import SwiftUI
import TranscriptionKit
import UniformTypeIdentifiers
#if os(macOS)
import PDFKit
#endif

/// Read aloud: the talking score, navigable by part and bar, with pitch, duration and
/// how sure Brasscribe is, and a button to play each bar.
struct TalkingScoreView: View {
    @Bindable var model: PracticeModel
    @Environment(\.dismiss) private var dismiss
    @State private var partID: String = ""

    var body: some View {
        NavigationStack {
            List {
                Picker(selection: $partID) {
                    ForEach(model.score.parts) { p in Text(p.displayName).tag(p.id) }
                } label: { Text("Part") }
                ForEach(model.score.measures.indices, id: \.self) { i in
                    HStack(alignment: .top) {
                        Text(model.describe(partID: partID, bar: i))
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Button { model.goToBar(i); if !model.isPlaying { model.togglePlay() } } label: {
                            Image(systemName: BrasscribeIcon.play.systemName).hitTarget()
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel(Text("Play \(model.barLabel(i))"))
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: Text("Play this bar")) { model.goToBar(i); if !model.isPlaying { model.togglePlay() } }
                }
            }
            .navigationTitle(Text("Read aloud"))
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .onAppear { if partID.isEmpty { partID = model.shownPart ?? model.myPart ?? model.score.parts.first?.id ?? "" } }
        }
        .frame(minWidth: 480, minHeight: 560)
    }
}

/// Share or print: what (your part, every part, the conductor's score) and as what (PDF
/// by default; audio; more formats), with or without the "?" marks. Print is the primary.
struct ExportView: View {
    enum Scope: Hashable { case mine, every, conductor }
    enum Format: String, CaseIterable, Identifiable {
        case pdf, audio, musicXML, midi, talkingScore, braille
        var id: String { rawValue }
        var title: String {
            switch self {
            case .pdf: return "PDF"
            case .audio: return String(localized: "Audio")
            case .musicXML: return "MusicXML"
            case .midi: return "MIDI"
            case .talkingScore: return String(localized: "Talking score")
            case .braille: return String(localized: "Braille music")
            }
        }
        var detail: String {
            switch self {
            case .pdf: return String(localized: "For printing and the music stand")
            case .audio: return String(localized: "The band playing the score, to practise with")
            case .musicXML: return String(localized: "Edit in MuseScore, Sibelius or Dorico")
            case .midi: return String(localized: "For other music apps")
            case .talkingScore: return String(localized: "Text a screen reader can read aloud")
            case .braille: return String(localized: "BRF file for a braille display or embosser")
            }
        }
    }

    @Bindable var model: PracticeModel
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @Environment(\.horizontalSizeClass) private var hsize
    @State private var scope: Scope = .mine
    @State private var formats: Set<Format> = [.pdf]
    @State private var marks = true
    @State private var moreFormats = false
    @State private var busy = false
    @State private var message: String?
    @State private var saving: ExportFolder?
    @State private var shareURLs: [URL] = []
    @State private var sharing = false

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    private var myPart: Part? { model.myPart.flatMap { model.score.part(id: $0) } }

    var body: some View {
        // the Mac sheet has no title bar: its title is the display heading
        #if os(macOS)
        sheet
        #else
        NavigationStack { sheet }
        #endif
    }

    private var sheet: some View {
        Group {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.s5) {
                    if wide { DisplayTitle(text: String(localized: "Share or print"), size: 34) }
                    what
                    asWhat
                    marksSwitch
                    if let message { NoticeBox(systemImage: BrasscribeIcon.info.systemName, text: message) }
                }
                .padding(Space.s5)
            }
            .pageBackground()
            .safeAreaInset(edge: .bottom) { actions }
            .navigationTitle(Text("Share or print"))
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(wide ? .hidden : .visible, for: .navigationBar)
            #endif
            .fileExporter(isPresented: Binding(get: { saving != nil }, set: { if !$0 { saving = nil } }),
                          document: saving, contentType: saving?.type ?? .folder, defaultFilename: saving?.name) { result in
                if case .failure(let e) = result { message = e.localizedDescription } else { dismiss() }
                saving = nil
            }
            #if os(iOS)
            .sheet(isPresented: $sharing) { ShareSheet(items: shareURLs).appAppearance() }
            #endif
        }
        .onAppear {
            if myPart == nil { scope = .conductor }
            marks = (model.piece.toCheck ?? 1) > 0
        }
        #if os(macOS)
        .frame(width: 620, height: 720)
        #else
        .presentationDetents([.large])
        #endif
    }

    // MARK: what

    private var myLabel: String { myPart.map { String(localized: "\($0.displayName) (you)") } ?? String(localized: "My part") }

    /// A quartet has no conductor: its whole score is the four parts.
    private var scoreLabel: String {
        model.piece.output?.lineup == .quartet ? String(localized: "Score (all 4 parts)") : String(localized: "Conductor's score")
    }

    @ViewBuilder private var what: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            SectionLabel(String(localized: "What"))
            if wide {
                Segmented(label: String(localized: "What"), selection: $scope,
                          options: (myPart != nil ? [(Scope.mine, myLabel)] : [])
                            + [(Scope.every, String(localized: "Every part")), (Scope.conductor, scoreLabel)])
                if scope == .every {
                    Text("Every part: one PDF per player.").font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted)
                }
            } else {
                VStack(spacing: 0) {
                    if myPart != nil { radio(myLabel, nil, .mine); Divider().overlay(Color.Brasscribe.border) }
                    radio(String(localized: "Every part"), String(localized: "one PDF per player"), .every)
                    Divider().overlay(Color.Brasscribe.border)
                    radio(scoreLabel, nil, .conductor)
                }
                .card(padding: 0)
            }
        }
    }

    private func radio(_ title: String, _ note: String?, _ s: Scope) -> some View {
        Button { scope = s } label: {
            HStack(spacing: Space.s3) {
                Image(systemName: scope == s ? "largecircle.fill.circle" : "circle").font(.title2)
                    .foregroundStyle(scope == s ? Color.Brasscribe.text : Color.Brasscribe.borderStrong)
                    .accessibilityHidden(true)
                Text("\(Text(title).font(Font.Brasscribe.headline))\(note.map { Text(verbatim: " · ") + Text($0).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted) } ?? Text(verbatim: ""))")
                    .foregroundStyle(Color.Brasscribe.text)
                Spacer()
            }
            .padding(.horizontal, Space.s4)
            .frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(scope == s ? [.isSelected] : [])
    }

    // MARK: as

    private var shownFormats: [Format] {
        wide || moreFormats ? Format.allCases : [.pdf, .audio]
    }

    private var asWhat: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            SectionLabel(String(localized: "As"))
            VStack(spacing: 0) {
                ForEach(Array(shownFormats.enumerated()), id: \.element) { i, f in
                    if i > 0 { Divider().overlay(Color.Brasscribe.border) }
                    formatRow(f)
                }
                if !wide && !moreFormats {
                    Divider().overlay(Color.Brasscribe.border)
                    Button { moreFormats = true } label: {
                        HStack(spacing: Space.s3) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("More formats").font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                                Text("MusicXML, MIDI and 2 more").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted).lineLimit(1)
                            }
                            Spacer()
                            Image(systemName: BrasscribeIcon.open.systemName).foregroundStyle(Color.Brasscribe.textMuted)
                        }
                        .padding(.horizontal, Space.s4).padding(.leading, 40).frame(minHeight: 60).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .card(padding: 0)
        }
    }

    private func formatRow(_ f: Format) -> some View {
        let reason = unavailable(f)
        let on = formats.contains(f) && reason == nil
        return Button {
            if formats.contains(f) { formats.remove(f) } else { formats.insert(f) }
        } label: {
            HStack(spacing: Space.s3) {
                Image(systemName: on ? "checkmark.square.fill" : "square").font(.title2)
                    .foregroundStyle(on ? Color.Brasscribe.text : Color.Brasscribe.borderStrong)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(f.title).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                    Text(reason ?? f.detail).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                }
                Spacer()
            }
            .padding(.horizontal, Space.s4)
            .frame(minHeight: 60)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(reason != nil)
        .accessibilityAddTraits(on ? [.isSelected] : [])
        .accessibilityIdentifier("export-\(f.rawValue)")
    }

    private var marksSwitch: some View {
        Toggle(isOn: $marks) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Show ? marks").font(Font.Brasscribe.headline)
                Text("A note at the bottom of each page explains them").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
            }
        }
        .toggleStyle(.switch)
        .tint(Color.Brasscribe.primary)
        .card()
    }

    // MARK: actions

    private var fileCount: Int {
        let n = partsInScope.count
        return formats.filter { unavailable($0) == nil }.reduce(0) { c, f in
            switch f {
            case .pdf, .musicXML, .braille: return c + (scope == .every ? n : 1)
            case .audio, .midi, .talkingScore: return c + 1
            }
        }
    }

    private var actions: some View {
        let canPrint = formats.contains(.pdf)
        let count = Text(fileCount == 1 ? String(localized: "1 file") : String(localized: "\(fileCount) files"))
            .font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted)
        return Group {
            if wide {
                HStack(spacing: Space.s3) {
                    count
                    Spacer()
                    Button("Cancel") { dismiss() }.buttonStyle(.plainText).keyboardShortcut(.cancelAction)
                    Button { Task { await save() } } label: { Text("Save…") }
                        .buttonStyle(SecondaryButtonStyle(minHeight: 44))
                        .disabled(fileCount == 0 || busy)
                        .accessibilityIdentifier("saveExport")
                    if canPrint {
                        Button { Task { await print() } } label: { Label("Print…", systemImage: BrasscribeIcon.print.systemName) }
                            .buttonStyle(.primary)
                            .disabled(busy)
                            .keyboardShortcut(.defaultAction)
                            .accessibilityIdentifier("printExport")
                    }
                }
            } else {
                VStack(spacing: Space.s3) {
                    if canPrint {
                        Button { Task { await print() } } label: { Label("Print", systemImage: BrasscribeIcon.print.systemName) }
                            .buttonStyle(.primaryWide).disabled(busy)
                            .accessibilityIdentifier("printExport")
                    }
                    HStack(spacing: Space.s3) {
                        Button { Task { await share() } } label: { Label("Share…", systemImage: BrasscribeIcon.export.systemName) }
                            .buttonStyle(canPrint ? SecondaryButtonStyle(fullWidth: true) : SecondaryButtonStyle(fullWidth: true))
                            .disabled(fileCount == 0 || busy)
                        Button { Task { await save() } } label: { Label("Save to Files", systemImage: BrasscribeIcon.folder.systemName) }
                            .buttonStyle(SecondaryButtonStyle(fullWidth: true))
                            .disabled(fileCount == 0 || busy)
                            .accessibilityIdentifier("saveExport")
                    }
                    count
                }
            }
        }
        .overlay { if busy { ProgressView() } }
        .padding(Space.s5)
        .background(Color.Brasscribe.bg)
        .overlay(alignment: .top) { Divider().overlay(Color.Brasscribe.border) }
    }

    private var partsInScope: [Part] {
        switch scope {
        case .mine: return myPart.map { [$0] } ?? []
        case .every: return model.score.parts
        case .conductor: return model.score.parts
        }
    }

    /// Why a format can't be made for this scope, or nil.
    private func unavailable(_ f: Format) -> String? {
        guard f == .braille else { return nil }
        if scope == .conductor, remoteAvailable(.brailleBRF) { return nil }
        if scope != .conductor, fixturePartsDirectory != nil { return nil }
        return String(localized: "Needs Brasscribe on your computer")
    }

    private var fixturePartsDirectory: URL? {
        guard let d = model.piece.fixtureDirectory else { return nil }
        let u = URL(fileURLWithPath: d).appending(path: "parts")
        return FileManager.default.fileExists(atPath: u.path) ? u : nil
    }

    private func remoteAvailable(_ k: ArtifactKind) -> Bool {
        model.piece.fixtureDirectory != nil || (model.piece.remoteJobID != nil && model.piece.remoteArtifacts.contains(k))
    }

    private func print() async {
        guard let pdfs = await make([.pdf])?.filter({ $0.pathExtension == "pdf" }), !pdfs.isEmpty else { return }
        #if os(iOS)
        let c = UIPrintInteractionController.shared
        let info = UIPrintInfo(dictionary: nil)
        info.jobName = model.piece.title
        info.outputType = .grayscale
        c.printInfo = info
        c.printingItems = pdfs
        c.present(animated: true)
        #else
        let doc = PDFDocument()
        for u in pdfs { if let d = PDFDocument(url: u) { for i in 0..<d.pageCount { if let p = d.page(at: i) { doc.insert(p, at: doc.pageCount) } } } }
        doc.printOperation(for: NSPrintInfo.shared, scalingMode: .pageScaleToFit, autoRotate: true)?.run()
        #endif
    }

    private func share() async {
        guard let files = await make(formats), !files.isEmpty else { return }
        shareURLs = files
        sharing = true
    }

    private func save() async {
        guard let files = await make(formats), !files.isEmpty else { return }
        saving = ExportFolder(files: files, name: files.count == 1 ? files[0].lastPathComponent : model.piece.title)
    }

    /// Writes the chosen files into a fresh temporary folder.
    private func make(_ kinds: Set<Format>) async -> [URL]? {
        busy = true
        defer { busy = false }
        message = nil
        let dir = FileManager.default.temporaryDirectory.appending(path: "Share-\(UUID().uuidString)", directoryHint: .isDirectory)
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let title = model.piece.title
            let xml = try model.piece.musicXML()
            let marks = self.marks
            let parts: [Part?] = scope == .conductor ? [nil] : partsInScope.map { Optional($0) }
            var out: [URL] = []
            func name(_ part: Part?, _ ext: String) -> URL {
                dir.appending(path: part.map { "\(title) – \($0.displayName).\(ext)" } ?? "\(title).\(ext)")
            }
            for f in Format.allCases where kinds.contains(f) && unavailable(f) == nil {
                switch f {
                case .pdf:
                    for p in parts {
                        let data = try await Task.detached {
                            try PDFMaker.pdf(musicXML: xml, parts: p.map { [$0.id] }, title: title, subtitle: p?.displayName, marks: marks)
                        }.value
                        let u = name(p, "pdf"); try data.write(to: u); out.append(u)
                    }
                case .musicXML:
                    for p in parts {
                        var s = p.map { MusicXMLFilter.keepingParts([$0.id], in: xml) } ?? xml
                        if !marks { s = ScoreRenderer.removingUncertainty(s) }
                        let u = name(p, "musicxml"); try Data(s.utf8).write(to: u); out.append(u)
                    }
                case .midi:
                    var s = model.score
                    if scope == .mine, let mine = myPart { s.parts = s.parts.filter { $0.id == mine.id } }
                    let u = name(scope == .mine ? myPart : nil, "mid")
                    try MIDIWriter.data(for: s, options: .init(transposeSemitones: model.transpose)).write(to: u); out.append(u)
                case .talkingScore:
                    var t = model.talking
                    t.pitchMode = model.pitchMode
                    let u = dir.appending(path: "\(title) – " + String(localized: "talking score") + ".txt")
                    try Data(t.text(parts: scope == .mine ? myPart.map { [$0] } : nil).utf8).write(to: u); out.append(u)
                case .audio:
                    let u = name(nil, "m4a")
                    let score = model.score, tm = model.composition?.tempoMap
                    let muted = model.score.parts.filter { model.isMuted($0.id) }.map(\.id)
                    try await Task.detached {
                        let e = try PlaybackEngine(score: score, tempoMap: tm, soundBank: .locate(), offlineFormat: PlaybackEngine.offlineFormat())
                        for id in muted { e.setMuted(id, true) }
                        try e.exportScore(to: u)
                    }.value
                    out.append(u)
                case .braille:
                    if scope == .conductor {
                        let data = try await remote(.brailleBRF)
                        let u = name(nil, "brf"); try data.write(to: u); out.append(u)
                    } else if let pdir = fixturePartsDirectory {
                        let files = (try? FileManager.default.contentsOfDirectory(atPath: pdir.path)) ?? []
                        for p in parts.compactMap({ $0 }) {
                            guard let i = model.score.parts.firstIndex(where: { $0.id == p.id }),
                                  let f = files.first(where: { $0.hasPrefix(String(format: "%02d-", i + 1)) && $0.hasSuffix(".brf") }) else { continue }
                            let u = name(p, "brf")
                            try FileManager.default.copyItem(at: pdir.appending(path: f), to: u); out.append(u)
                        }
                    }
                }
            }
            return out
        } catch {
            message = String(localized: "These files couldn't be made. Try fewer formats, or try again.")
            return nil
        }
    }

    /// Braille comes from Brasscribe on your computer (or the fixture folder in UI tests).
    private func remote(_ kind: ArtifactKind) async throws -> Data {
        if let dir = model.piece.fixtureDirectory {
            return try await FixtureService(directory: URL(fileURLWithPath: dir), stepDelay: 0).artifact(kind, jobID: "fixture")
        }
        guard let job = model.piece.remoteJobID, model.piece.remoteArtifacts.contains(kind) else {
            throw TranscriptionError.artifactUnavailable(kind)
        }
        return try await app.service().artifact(kind, jobID: job)
    }
}

/// One file, or a folder of files, for the save panel.
struct ExportFolder: FileDocument {
    static var readableContentTypes: [UTType] { [.folder, .data] }
    var files: [URL]
    var name: String
    var type: UTType { files.count == 1 ? (UTType(filenameExtension: files[0].pathExtension) ?? .data) : .folder }

    init(files: [URL], name: String) { self.files = files; self.name = name }
    init(configuration: ReadConfiguration) throws { files = []; name = "" }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        if files.count == 1 { return try FileWrapper(url: files[0]) }
        var children: [String: FileWrapper] = [:]
        for u in files { children[u.lastPathComponent] = try FileWrapper(url: u) }
        return FileWrapper(directoryWithFileWrappers: children)
    }
}

#if os(iOS)
struct ShareSheet: UIViewControllerRepresentable {
    let items: [URL]
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: items, applicationActivities: nil) }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
#endif
