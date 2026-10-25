import SwiftUI
import TabKit
import TranscriptionKit

/// "What is this?": two choices, nothing pre-selected unless the instrument is one that is written alone, then
/// Continue. The answer decides how the computer listens.
struct WhatIsThisView: View {
    @Environment(FretscribeModel.self) private var model
    let source: PendingSource
    @State private var choice: RecordingKind?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                if let name = source.name {
                    Label(name, systemImage: PlayIcon.file.systemName)
                        .font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                }
                Text("What is this?").font(Font.Scribe.display).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                Text("Your answer decides how Fretscribe listens.").font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted)
                VStack(spacing: Space.s3) {
                    option(.instrument, title: String(localized: "Just my instrument"),
                           detail: String(localized: "One instrument playing, with nothing else."))
                    option(.song, title: String(localized: "A full song"), detail: Self.songWords(model.instrument.instrument))
                }
                HelperLine(systemImage: PlayIcon.computer.systemName, text: model.whereItRuns())
                if !model.computerThere {
                    Text("Connect your computer to continue.").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.text)
                    ConnectionStatusRow()
                }
            }
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text("What is this?"))
        .toolbar(removing: .title)
        .safeAreaInset(edge: .bottom) {
            Button { if let choice { model.startTranscription(source, recording: choice) } } label: { Text("Continue") }
                .buttonStyle(.primaryWide)
                .disabled(choice == nil || !model.computerThere)
                .padding(Space.s5)
                .frame(maxWidth: ScribeDesign.Size.contentMaxWidth)
                .accessibilityIdentifier("fs-what-continue")
                .accessibilityHint(choice == nil ? Text("Choose one to continue.") : Text(verbatim: ""))
                .afterTheContentItIsDockedUnder()
        }
        .onAppear { if choice == nil, [.ukulele, .mandolin].contains(model.instrument.valid().instrument) { choice = .instrument } }
    }

    /// What "A full song" says for [instrument]: which instrument is picked out of it, and when that works.
    static func songWords(_ instrument: Instrument) -> String {
        switch instrument {
        case .guitar: String(localized: "A band or a record. Fretscribe picks out the guitar.")
        case .bass: String(localized: "A band or a record. Fretscribe picks out the bass.")
        case .ukulele: String(localized: "A band or a record. This only works when no guitar is playing: in a song, Fretscribe can't tell a ukulele from a guitar.")
        case .mandolin: String(localized: "A band or a record. This only works when no guitar is playing: in a song, Fretscribe can't tell a mandolin from a guitar.")
        }
    }

    private func option(_ kind: RecordingKind, title: String, detail: String) -> some View {
        Button { choice = kind } label: {
            HStack(alignment: .top, spacing: Space.s3) {
                Image(systemName: choice == kind ? "largecircle.fill.circle" : "circle")
                    .font(.title3).foregroundStyle(Color.Scribe.text).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text)
                    Text(detail).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .padding(Space.s4)
            .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading)
            .background(Color.Scribe.surface, in: RoundedRectangle(cornerRadius: Radius.md))
            .overlay(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(choice == kind ? Color.Scribe.text : Color.Scribe.border,
                                                                             lineWidth: choice == kind ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: Radius.md))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(choice == kind ? [.isSelected] : [])
        .accessibilityIdentifier("fs-what-\(kind.rawValue)")
    }
}

/// Writing down the notes: the computer's step in plain words, how far it is, and Stop.
struct TranscribingView: View {
    @Environment(FretscribeModel.self) private var model
    let jobID: UUID
    @State private var confirmStop = false

    var body: some View {
        let job = model.jobs[jobID]
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                if let job, let which = job.needsUpdate {
                    failed(job, title: String(localized: "The tab couldn't be made"), words: ConnectionCopy.update(which))
                } else if let job, let failure = job.failure {
                    failed(job, title: String(localized: "The tab couldn't be made"), words: TabErrorWords.specific(failure))
                } else if let job, job.cancelled {
                    Text("Stopped. You can start again from the recording.").font(Font.Scribe.body)
                    Button("Back to Home") { model.goHome() }.buttonStyle(.outline)
                } else if let job {
                    Text(job.source.title).font(Font.Scribe.title2).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                    Text(Self.stage(job.progress.stage)).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text)
                        .accessibilityIdentifier("fs-transcribe-stage")
                    ProgressView(value: job.progress.fraction)
                        .tint(Color.Scribe.brand)
                        .accessibilityLabel(Text("Progress"))
                        .accessibilityValue(Text(percentText(job.progress.fraction * 100)))
                    Text("\(percentText(job.progress.fraction * 100)). You can switch to another app: when the tab is ready, it is in Your songs while this device is connected to your computer.")
                        .font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
                    HelperLine(systemImage: PlayIcon.computer.systemName, text: String(localized: "Bandroom on your computer is writing down the notes"))
                    Button(role: .destructive) { confirmStop = true } label: { Text("Stop") }
                        .buttonStyle(.outline)
                        .accessibilityIdentifier("fs-transcribe-stop")
                }
            }
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text("Writing down the notes"))
        .toolbar(removing: .title)
        .navigationBarBackButtonHidden(job?.failure == nil && job?.cancelled != true && job?.needsUpdate == nil)
        .confirmationDialog(Text("Stop writing down the notes?"), isPresented: $confirmStop, titleVisibility: .visible) {
            Button("Stop", role: .destructive) { job?.cancel() }
            Button("Keep going", role: .cancel) {}
        } message: {
            Text("The recording is kept. You can start again from it.")
        }
    }

    private func failed(_ job: TabJob, title: String, words: String) -> some View {
        VStack(alignment: .leading, spacing: Space.s4) {
            Text(title).font(Font.Scribe.title2).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
            Text(words).font(Font.Scribe.body).foregroundStyle(Color.Scribe.text).fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Space.s3) {
                Button("Try again") { model.retry(job) }.buttonStyle(.primary)
                Button("Back") { model.backToSource(job) }.buttonStyle(.outline)
            }
            if let failure = job.failure {
                DisclosureGroup { Text(verbatim: failure).font(Font.Scribe.caption).textSelection(.enabled) } label: { Text("Technical details") }
            }
        }
    }

    /// The computer's step for a tab, in plain words.
    static func stage(_ stage: StageKind) -> String {
        switch stage {
        case .uploading: String(localized: "Sending the recording to your computer")
        case .preparing: String(localized: "Getting the recording ready")
        case .separating: String(localized: "Picking out your instrument")
        case .findingBeat: String(localized: "Listening for the beat")
        case .transcribing: String(localized: "Writing down the notes")
        case .arranging: String(localized: "Choosing strings and frets")
        case .engraving, .rendering: String(localized: "Laying out the tab")
        case .working: String(localized: "Getting ready")
        }
    }
}

/// What went wrong while a tab was made, in the player's words.
enum TabErrorWords {
    static func specific(_ failure: String) -> String {
        let f = failure.lowercased()
        if f.contains("can't reach") || f.contains("unreachable") { return String(localized: "Can't reach Bandroom on your computer. Check that it is running and on the same network.") }
        if f.contains("422") { return String(localized: "Bandroom on your computer didn't accept these choices. It may need an update.") }
        return String(localized: "Bandroom on your computer couldn't finish the tab. Try again.")
    }
}

/// What the computer said about the song it wrote down: read from its `tab.json`.
struct SongFacts: Decodable {
    struct Instrument: Decodable { let name: String; let capo: Int?; let tuning: Tuning? }
    struct Tuning: Decodable { let name: String }
    struct Suggestion: Decodable { let preset: String; let tuning: String }
    struct Key: Decodable { let name: String; let mode: String? }
    struct Meter: Decodable { let beats: Int; let beatUnit: Int; enum CodingKeys: String, CodingKey { case beats; case beatUnit = "beat_unit" } }
    struct Reference: Decodable { let cents: Double; let retuned: Bool? }
    struct Note: Decodable { let confidence: Double?; let outOfRange: Bool?; let fret: Int?
        enum CodingKeys: String, CodingKey { case confidence, fret; case outOfRange = "out_of_range" } }
    let preset: String
    let instrument: Instrument
    let tuningSuggestions: [Suggestion]?
    let octaveShift: Int?
    let octaveSource: String?
    let octaveNotesMoved: Int?
    let referencePitch: Reference?
    let tempoBpm: Double?
    let key: Key?
    let meter: Meter?
    let notes: [Note]
    let unplayableDropped: Int?
    let inferredNotes: Int?

    enum CodingKeys: String, CodingKey {
        case preset, instrument, key, meter, notes
        case tuningSuggestions = "tuning_suggestions", octaveShift = "octave_shift", octaveSource = "octave_source"
        case octaveNotesMoved = "octave_notes_moved", referencePitch = "reference_pitch", tempoBpm = "tempo_bpm"
        case unplayableDropped = "unplayable_dropped", inferredNotes = "inferred_notes"
    }

    static func of(_ song: TabSong) -> SongFacts? {
        (try? Data(contentsOf: song.tabURL)).flatMap { try? JSONDecoder().decode(SongFacts.self, from: $0) }
    }

    var tuningName: String { instrument.tuning?.name ?? preset }
    /// The tuning the notes fit better, when there is one.
    var soundsLike: Suggestion? { tuningSuggestions?.first.flatMap { $0.preset == preset ? nil : $0 } }
    var doubtful: Int { notes.filter { ($0.confidence ?? 1) < SongMarks.doubt }.count }
    var noPlace: Int { notes.filter { $0.outOfRange == true || $0.fret == nil }.count }
}

/// "Check the song": what Fretscribe heard. If something here is wrong, the frets are wrong too.
struct CheckTheSongView: View {
    @Environment(FretscribeModel.self) private var model
    let song: TabSong

    var body: some View {
        let facts = SongFacts.of(song)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                Text("Check the song").font(Font.Scribe.display).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                Text("This is what Fretscribe heard. If something here is wrong, the frets are wrong too.")
                    .font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
                if let facts {
                    VStack(spacing: 0) {
                        row(String(localized: "Tuning"), facts.soundsLike.map {
                            String(localized: "Sounds like \($0.tuning). Written for \(facts.tuningName).")
                        } ?? facts.tuningName, id: "fs-check-tuning")
                        if let capo = facts.instrument.capo, capo > 0 {
                            Divider().overlay(Color.Scribe.border)
                            row(String(localized: "Capo"), String(localized: "capo \(capo)"), id: "fs-check-capo")
                        }
                        if let shift = facts.octaveShift, shift != 0 || (facts.octaveNotesMoved ?? 0) > 0 {
                            Divider().overlay(Color.Scribe.border)
                            row(String(localized: "Octave"), Self.octaveWords(shift: shift, chosen: facts.octaveSource == "chosen",
                                                                            moved: facts.octaveNotesMoved ?? 0), id: "fs-check-octave")
                        }
                        if let r = facts.referencePitch, abs(r.cents) > 10 {
                            Divider().overlay(Color.Scribe.border)
                            let cents = Int(abs(r.cents).rounded())
                            row(String(localized: "Reference pitch"), (r.cents > 0
                                ? String(localized: "A little sharp of concert pitch (A = 440): \(cents) cents.")
                                : String(localized: "A little flat of concert pitch (A = 440): \(cents) cents."))
                                + (r.retuned == true ? " " + String(localized: "Fretscribe allowed for it.") : ""), id: "fs-check-reference")
                        }
                        if let key = facts.key, let bpm = facts.tempoBpm, let meter = facts.meter {
                            Divider().overlay(Color.Scribe.border)
                            row(String(localized: "Key and tempo"), "\(key.name) · ♩ = \(Int(bpm.rounded())) · \(meter.beats)/\(meter.beatUnit)",
                                id: "fs-check-key-tempo")
                        }
                        if facts.doubtful > 0 {
                            Divider().overlay(Color.Scribe.border)
                            row(String(localized: "Notes to check"), String(localized: "\(facts.doubtful) notes marked ?"), id: "fs-check-notes")
                        }
                        if facts.noPlace > 0 {
                            Divider().overlay(Color.Scribe.border)
                            row(String(localized: "Notes with no place"),
                                String(localized: "\(facts.noPlace) notes with no place on your instrument. Is the tuning right?"), id: "fs-check-no-place")
                        }
                    }
                    .card(padding: 0)
                } else {
                    Text("What Fretscribe heard can't be shown right now. You can still open the tab.")
                        .font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted)
                }
                Text("You can change this later.").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
            }
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text("Check the song"))
        .toolbar(removing: .title)
        .safeAreaInset(edge: .bottom) {
            Button { model.path = [.tab(song)] } label: { Text("Show the tab") }
                .buttonStyle(.primaryWide)
                .padding(Space.s5)
                .frame(maxWidth: ScribeDesign.Size.contentMaxWidth)
                .accessibilityIdentifier("fs-show-tab")
                .afterTheContentItIsDockedUnder()
        }
    }

    static func octaveWords(shift: Int, chosen: Bool, moved: Int) -> String {
        if chosen {
            if shift < 0 { return String(localized: "Written one octave lower, as you chose.") }
            if shift > 0 { return String(localized: "Written one octave higher, as you chose.") }
            return String(localized: "Written as it was heard, as you chose.")
        }
        if shift <= -24 { return String(localized: "Written two octaves lower than it was heard.") }
        if shift < 0 { return String(localized: "Written one octave lower than it was heard.") }
        if shift > 0 { return String(localized: "Written one octave higher than it was heard.") }
        return String(localized: "\(moved) notes are written an octave lower than they were heard.")
    }

    private func row(_ title: String, _ value: String, id: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text)
            Text(value).font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
        }
        .padding(Space.s4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(id)
    }
}

/// Something went wrong: what happened, why, and the ways forward. The player's songs are never touched.
struct ProblemView: View {
    @Environment(FretscribeModel.self) private var model
    let problem: FretscribeProblem

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s4) {
                Image(systemName: PlayIcon.error.systemName).font(.largeTitle).foregroundStyle(Color.Scribe.error).accessibilityHidden(true)
                Text(title).font(Font.Scribe.title1).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                Text(text).font(Font.Scribe.body).foregroundStyle(Color.Scribe.text).fixedSize(horizontal: false, vertical: true)
                if case .needsUpdate(let which) = problem { UpdateAction(which: which, place: "problem") }
                HStack(spacing: Space.s3) {
                    Button { model.goHome(); model.importing = true } label: { Text("Open a recording") }.buttonStyle(.primary)
                    Button { model.goHome(); model.showRecorder = true } label: { Text("Record with the microphone") }.buttonStyle(.outline)
                }
                if let details {
                    DisclosureGroup { Text(verbatim: details).font(Font.Scribe.caption).textSelection(.enabled) } label: { Text("Technical details") }
                }
            }
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text(title))
        .toolbar(removing: .title)
        .onAppear { AccessibilityNotifier.announce(title) }
    }

    private var title: String {
        switch problem {
        case .cantOpenFile: String(localized: "This file couldn't be opened")
        case .sheetMusic: String(localized: "Fretscribe can't open sheet music yet")
        case .copyProtected: String(localized: "This recording is protected")
        case .silence: String(localized: "Nothing was heard")
        case .tabFailed: String(localized: "The tab couldn't be made")
        case .cantOpenTab, .needsUpdate: String(localized: "This tab couldn't be opened")
        }
    }

    private var text: String {
        switch problem {
        case .cantOpenFile: String(localized: "Fretscribe couldn't read the sound in it.")
        case .sheetMusic: String(localized: "It makes tabs from recordings. Open a recording, or record what you play.")
        case .copyProtected: String(localized: "Fretscribe can't use it: it is copy-protected. Play it and record it instead.")
        case .silence: String(localized: "The recording is silent. Check the microphone and try again.")
        case .tabFailed: String(localized: "Something went wrong while Bandroom on your computer was working on it.")
        case .cantOpenTab: String(localized: "Fretscribe couldn't get it from your computer.")
        case .needsUpdate(let which): ConnectionCopy.update(which)
        }
    }

    private var details: String? {
        switch problem {
        case .cantOpenFile(let d), .tabFailed(let d), .cantOpenTab(let d): d.isEmpty ? nil : d
        default: nil
        }
    }
}
