import AVFoundation
import ScoreKit
import SwiftUI
import TranscriptionKit

/// "What is this?": four choices, nothing pre-selected, then Continue. The choice decides
/// how Brasscribe listens. The band, how hard and the key come after the review.
struct SourceView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.horizontalSizeClass) private var hsize
    let source: PendingSource
    @State private var profile: SourceProfile?
    @State private var output = OutputChoice()
    @State private var duration: String?
    @Environment(\.dynamicTypeSize) private var typeSize

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                if let meta {
                    HelperLine(systemImage: BrasscribeIcon.file.systemName, text: meta)
                }
                VStack(alignment: .leading, spacing: Space.s2) {
                    DisplayTitle(text: String(localized: "What is this?"))
                    Text("Your answer decides how Brasscribe listens. It never guesses.")
                        .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                }
                LazyVGrid(columns: wide ? [GridItem(.flexible(), spacing: Space.s4), GridItem(.flexible(), spacing: Space.s4)] : [GridItem(.flexible())],
                          spacing: Space.s4) {
                    ForEach(SourceProfile.allCases) { p in choice(p) }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(Text("What is this?"))
                Text("Not sure? Choose Brass band.")
                    .font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)

                whereItRuns
                if PageActions.followContent { actionButtons.padding(.top, Space.s2).layoutProbe("pageActions") }
                if !wide { Color.clear.frame(height: Space.s2) }
            }
            .padding(.horizontal, wide ? Space.s8 : Space.s5)
            .padding(.vertical, Space.s6)
            .layoutProbe("pageColumn")
            .readingColumn()
        }
        .pageBackground()
        .bottomActions { actions }
        .navigationTitle(Text(source.title))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { duration = await Self.duration(of: source.audioURL) }
    }

    private var meta: String? {
        let bits = [source.name, duration].compactMap { $0 }
        return bits.isEmpty ? nil : bits.joined(separator: " · ")
    }

    private func choice(_ p: SourceProfile) -> some View {
        let on = profile == p
        return Button { profile = p } label: {
            HStack(alignment: .top, spacing: Space.s3) {
                VStack(alignment: .leading, spacing: Space.s1) {
                    Text(p.title).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                    Text(p.detail).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: Space.s2)
                Image(systemName: on ? "largecircle.fill.circle" : "circle")
                    .font(.title2)
                    .foregroundStyle(on ? Color.Brasscribe.text : Color.Brasscribe.borderStrong)
                    .accessibilityHidden(true)
            }
            .padding(Space.s4)
            .frame(maxWidth: .infinity, minHeight: 88, maxHeight: .infinity, alignment: .topLeading)
            .background(Color.Brasscribe.surfaceRaised, in: RoundedRectangle(cornerRadius: Radius.lg))
            .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(on ? Color.Brasscribe.text : Color.Brasscribe.borderStrong,
                                                                            lineWidth: on ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: Radius.lg))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? [.isSelected] : [])
        .accessibilityIdentifier("profile-\(p.rawValue)")
        .layoutProbe("profile-\(p.rawValue)")
    }

    /// Where the listening happens, and a way to change it. At large text sizes the
    /// Change button moves under the text, so the text never squeezes into a column.
    private var whereItRuns: some View {
        let text = Text(app.whereItRuns(for: profile))
            .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.text)
            .fixedSize(horizontal: false, vertical: true)
        let change = Button { app.showSettings = true } label: { Text("Change") }
            .buttonStyle(SecondaryButtonStyle(outline: true, minHeight: 44))
        return Group {
            if typeSize >= .xxxLarge {
                VStack(alignment: .leading, spacing: Space.s3) {
                    HStack(spacing: Space.s3) { IconWell(systemName: BrasscribeIcon.computer.systemName); text }
                    change
                }
            } else {
                HStack(spacing: Space.s3) {
                    IconWell(systemName: BrasscribeIcon.computer.systemName)
                    text
                    Spacer(minLength: Space.s2)
                    change
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .card()
    }

    private var actions: some View {
        actionButtons
            .padding(.horizontal, wide ? Space.s8 : Space.s5)
            .padding(.vertical, Space.s3)
            .readingColumn()
            .background(Color.Brasscribe.bg)
    }

    private var actionButtons: some View {
        let cont = Button {
            guard let profile else { return }
            app.startTranscription(source, profile: profile, output: output)
        } label: { Text("Continue") }
            .disabled(profile == nil)
            .accessibilityIdentifier("transcribe")
            .accessibilityHint(profile == nil ? Text("Choose one to continue.") : Text(""))
        return VStack(alignment: wide ? .trailing : .center, spacing: Space.s2) {
            if profile == nil {
                Text("Choose one to continue.").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                    .accessibilityHidden(true)
            }
            if wide {
                ActionRow {
                    Button { app.path.removeLast() } label: { Text("Cancel") }.buttonStyle(.plainText)
                        .keyboardShortcut(.cancelAction)
                    cont.buttonStyle(.primary).keyboardShortcut(.defaultAction)
                }
            } else {
                cont.buttonStyle(.primaryWide)
            }
        }
        .frame(maxWidth: .infinity, alignment: wide ? .trailing : .center)
    }

    static func duration(of url: URL) async -> String? {
        guard let d = try? await AVURLAsset(url: url).load(.duration), d.seconds.isFinite, d.seconds > 0 else { return nil }
        return Duration.seconds(d.seconds.rounded()).formatted(.units(allowed: [.minutes, .seconds], width: .abbreviated))
    }
}

extension SourceProfile {
    var title: String {
        switch self {
        case .solo: return String(localized: "One instrument")
        case .brassBand: return String(localized: "Brass band")
        case .orchestraWithSoloist: return String(localized: "Soloist with orchestra or band")
        case .popRock: return String(localized: "Pop or rock")
        }
    }
    var detail: String {
        switch self {
        case .solo: return String(localized: "One player on their own, like you practising the cornet.")
        case .brassBand: return String(localized: "A whole band playing together, with no other instruments.")
        case .orchestraWithSoloist: return String(localized: "You get the solo part, plus the accompaniment arranged for brass band.")
        case .popRock: return String(localized: "Singing, guitars, keys, bass and drums.")
        }
    }
    /// For the library row: "Brass band · 64 bars · Today".
    var shortTitle: String {
        switch self {
        case .solo: return String(localized: "One instrument")
        case .brassBand: return String(localized: "Brass band")
        case .orchestraWithSoloist: return String(localized: "Soloist with band")
        case .popRock: return String(localized: "Pop or rock")
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

/// The steps in plain words, the current one as the heading, a percentage and the time
/// left, and Cancel (with a confirmation). Announced at most every 10 % or 10 s.
struct TranscribeView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.horizontalSizeClass) private var hsize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let jobID: UUID
    @State private var confirmCancel = LaunchOptions.screen == "transcribing-cancel"
    @State private var lastAnnounced: (fraction: Double, at: Date) = (0, .distantPast)

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    var body: some View {
        Group {
            if let job = app.jobs[jobID] {
                if let f = job.failure {
                    failed(job, reason: f)
                } else {
                    progress(job)
                }
            } else {
                ProgressView()
            }
        }
        .pageBackground()
        .navigationTitle(app.jobs[jobID]?.source.title ?? "")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }

    private func steps(for job: TranscriptionJob) -> [StageKind] {
        var s: [StageKind] = []
        if job.service is CompanionService { s.append(.uploading) }
        s.append(.preparing)
        s.append(.findingBeat)
        if job.profile != .solo { s.append(.separating) }
        s += [.transcribing, .arranging, .engraving]
        return s
    }

    @ViewBuilder private func progress(_ job: TranscriptionJob) -> some View {
        let steps = steps(for: job)
        let current = steps.firstIndex(of: job.progress.stage) ?? 0
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                BrandMark(size: 40)
                VStack(alignment: .leading, spacing: Space.s2) {
                    SectionLabel(wide ? String(localized: "Step \(current + 1) of \(steps.count) · \(job.profile.title)")
                                      : String(localized: "Step \(current + 1) of \(steps.count)"))
                    DisplayTitle(text: job.progress.stage.plain)
                }
                VStack(spacing: Space.s2) {
                    ProgressView(value: job.progress.fraction)
                        .tint(Color.Brasscribe.brass)
                        .animation(reduceMotion ? nil : BrasscribeDesign.Motion.animation(reduceMotion: false), value: job.progress.fraction)
                        .accessibilityLabel(Text(job.progress.stage.plain))
                        .accessibilityValue(Text("\(percentText(job.progress.fraction * 100)), \(eta(job.progress))"))
                        .accessibilityIdentifier("transcriptionProgress")
                    HStack {
                        Text(percentText(job.progress.fraction * 100)).monospacedDigit()
                        Spacer()
                        Text(eta(job.progress))
                    }
                    .font(Font.Brasscribe.callout)
                    .foregroundStyle(Color.Brasscribe.textMuted)
                    .accessibilityHidden(true)
                }
                VStack(alignment: .leading, spacing: Space.s4) {
                    ForEach(Array(steps.enumerated()), id: \.offset) { i, s in
                        HStack(spacing: Space.s3) {
                            Image(systemName: i < current ? "checkmark.circle.fill" : i == current ? "smallcircle.filled.circle" : "circle")
                                .font(.title2)
                                .foregroundStyle(i <= current ? Color.Brasscribe.text : Color.Brasscribe.borderStrong)
                                .accessibilityHidden(true)
                            Text(s.plain)
                                .font(i == current ? Font.Brasscribe.headline : Font.Brasscribe.body)
                                .foregroundStyle(i == current ? Color.Brasscribe.text : Color.Brasscribe.textMuted)
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilityValue(i < current ? Text("Done") : i == current ? Text("Now") : Text("Next"))
                    }
                }
                NoticeBox(systemImage: BrasscribeIcon.computer.systemName,
                          text: "\(app.whereItRuns(for: job.profile)) " + String(localized: "You can leave this screen. Brasscribe will tell you when the score is ready."))
                if PageActions.followContent { cancelRow(job).layoutProbe("pageActions") }
            }
            .padding(.horizontal, wide ? Space.s8 : Space.s5)
            .padding(.vertical, Space.s6)
            .layoutProbe("pageColumn")
            .readingColumn()
        }
        .bottomActions {
            cancelRow(job)
                .padding(.horizontal, wide ? Space.s8 : Space.s5)
                .padding(.vertical, Space.s3)
                .readingColumn()
        }
        .onChange(of: job.progress.stage) { _, s in announce(s.plain, fraction: job.progress.fraction, force: true) }
        .onChange(of: job.progress.fraction) { _, f in announce(nil, fraction: f, force: false) }
    }

    private func cancelRow(_ job: TranscriptionJob) -> some View {
        HStack {
            if wide { Spacer() }
            Button { confirmCancel = true } label: { Text("Cancel") }
                .buttonStyle(SecondaryButtonStyle(outline: true, fullWidth: !wide))
                .keyboardShortcut(.cancelAction)
                .accessibilityIdentifier("cancelTranscription")
                .confirmationDialog(String(localized: "Stop making this score?"), isPresented: $confirmCancel, titleVisibility: .visible) {
                    Button(String(localized: "Stop making the score"), role: .destructive) { job.cancel(); app.goHome() }
                    Button(String(localized: "Keep going")) {}
                } message: { Text("You can start again from the recording.") }
        }
    }

    /// Announce the step when it changes, and the percentage at most every 10 % or 10 s.
    private func announce(_ step: String?, fraction: Double, force: Bool) {
        let now = Date()
        guard force || fraction - lastAnnounced.fraction >= 0.1 || now.timeIntervalSince(lastAnnounced.at) >= 10 else { return }
        lastAnnounced = (fraction, now)
        AccessibilityNotifier.announce([step, percentText(fraction * 100)].compactMap { $0 }.joined(separator: ", "))
    }

    private func failed(_ job: TranscriptionJob, reason: String) -> some View {
        ProblemContent(title: String(localized: "The score couldn't be made"),
                       lead: nil,
                       reasons: [String(localized: "Brasscribe stopped before the notes were written down. Your recording is safe.")],
                       hint: nil, detail: reason) {
            let full = !PageActions.followContent
            if PageActions.followContent {
                Button { app.goHome() } label: { Text("Back to Home") }
                    .buttonStyle(SecondaryButtonStyle(fullWidth: full))
            }
            Button { app.startTranscription(job.source, profile: job.profile, output: job.output) } label: {
                Label("Try again", systemImage: BrasscribeIcon.retry.systemName)
            }
            .buttonStyle(PrimaryButtonStyle(fullWidth: full))
            if !PageActions.followContent {
                Button { app.goHome() } label: { Text("Back to Home") }
                    .buttonStyle(SecondaryButtonStyle(fullWidth: full))
            }
        }
    }

    func eta(_ p: TranscriptionProgress) -> String {
        guard let s = p.etaSeconds else { return String(localized: "Working out the time left…") }
        if s < 60 { return String(localized: "Less than a minute left") }
        let m = Int((s / 60).rounded())
        return m == 1 ? String(localized: "About 1 minute left") : String(localized: "About \(m) minutes left")
    }
}

extension StageKind {
    var plain: String {
        switch self {
        case .uploading: return String(localized: "Sending the recording")
        case .preparing: return String(localized: "Getting the recording ready")
        case .separating: return String(localized: "Separating the soloist from the band")
        case .findingBeat: return String(localized: "Finding the beat")
        case .transcribing: return String(localized: "Writing down the notes")
        case .arranging: return String(localized: "Arranging for brass band")
        case .engraving: return String(localized: "Laying out the pages")
        case .rendering: return String(localized: "Making the audio")
        case .working: return String(localized: "Working")
        }
    }
}

/// A problem with its way forward (mockups/png/error-*).
struct ProblemView: View {
    @Environment(AppModel.self) private var app
    let problem: Problem

    var body: some View {
        ProblemContent(title: problem.title, lead: problem.lead, reasons: problem.reasons, hint: problem.hint, detail: problem.detail) {
            // phone: the way forward on top, full width; Mac: a row with the primary last, on the right
            let wide = !PageActions.followContent
            let actions = Array(problem.actions.enumerated())
            ForEach(PageActions.followContent ? actions.reversed() : actions, id: \.offset) { i, a in
                let button = Button { run(a) } label: { label(a) }
                if i == 0 { button.buttonStyle(PrimaryButtonStyle(fullWidth: wide)) } else { button.buttonStyle(SecondaryButtonStyle(fullWidth: wide)) }
            }
        }
        .navigationTitle(Text(problem.title))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar(removing: .title)
    }

    @ViewBuilder private func label(_ a: Problem.Action) -> some View {
        switch a {
        case .importFile:
            if case .cantOpenFile = problem { Label("Choose another file", systemImage: BrasscribeIcon.importFile.systemName) }
            else { Label("Open a recording instead", systemImage: BrasscribeIcon.importFile.systemName) }
        case .recordMic: Label("Record with the microphone", systemImage: BrasscribeIcon.recordMic.systemName)
        case .home: Text("Back to Home")
        }
    }

    private func run(_ a: Problem.Action) {
        app.goHome()
        switch a {
        case .importFile: app.importing = true
        case .recordMic: app.showRecorder = true
        case .home: break
        }
    }
}

/// Title (what happened), one or two reasons, an optional hint, the recovery buttons, and
/// the technical detail folded under "Details for the band's tech person".
struct ProblemContent<Actions: View>: View {
    let title: String
    let lead: String?
    let reasons: [String]
    let hint: String?
    let detail: String?
    @ViewBuilder let actions: Actions
    @Environment(\.horizontalSizeClass) private var hsize

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                Image(systemName: BrasscribeIcon.error.systemName)
                    .font(.title)
                    .foregroundStyle(Color.Brasscribe.error)
                    .frame(width: 56, height: 56)
                    .background(Color.Brasscribe.surface, in: RoundedRectangle(cornerRadius: Radius.lg))
                    .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(Color.Brasscribe.border))
                    .accessibilityHidden(true)
                DisplayTitle(text: title)
                if let lead { Text(lead).font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.text) }
                VStack(alignment: .leading, spacing: Space.s2) {
                    ForEach(reasons, id: \.self) { r in
                        HStack(alignment: .firstTextBaseline, spacing: Space.s2) {
                            Text(verbatim: "•").accessibilityHidden(true)
                            Text(r).fixedSize(horizontal: false, vertical: true)
                        }
                        .font(Font.Brasscribe.body)
                        .foregroundStyle(reasons.count > 1 || lead != nil ? Color.Brasscribe.textMuted : Color.Brasscribe.text)
                    }
                }
                if let hint { NoticeBox(systemImage: BrasscribeIcon.info.systemName, text: hint) }
                if let detail {
                    DisclosureGroup {
                        Text(detail).font(.footnote.monospaced()).foregroundStyle(Color.Brasscribe.textMuted).textSelection(.enabled)
                            .padding(.top, Space.s2)
                    } label: { Text("Details for the band's tech person").font(Font.Brasscribe.callout) }
                    .tint(Color.Brasscribe.text)
                }
                if PageActions.followContent {
                    ActionRow { actions }
                        .padding(.top, Space.s2)
                        .layoutProbe("pageActions")
                }
            }
            .padding(.horizontal, Space.s5)
            .padding(.vertical, Space.s6)
            .layoutProbe("pageColumn")
            .readingColumn()
        }
        .pageBackground()
        .bottomActions {
            VStack(spacing: Space.s3) { actions }
                .padding(.horizontal, Space.s5)
                .padding(.vertical, Space.s3)
                .frame(maxWidth: 480)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .onAppear { AccessibilityNotifier.announce(title) }
    }
}

enum AccessibilityNotifier {
    /// VoiceOver is on (or a test says so with `-stand-assistive`).
    @MainActor static var screenReaderRunning: Bool {
        if LaunchOptions.standAssistive { return true }
        #if os(iOS)
        return UIAccessibility.isVoiceOverRunning
        #else
        return NSWorkspace.shared.isVoiceOverEnabled
        #endif
    }

    /// `polite`: queued after what is being read, for background changes such as the connection.
    @MainActor static func announce(_ s: String, polite: Bool = false) {
        #if os(iOS)
        if polite {
            var text = AttributedString(s)
            text.accessibilitySpeechAnnouncementPriority = .low
            AccessibilityNotification.Announcement(text).post()
        } else {
            UIAccessibility.post(notification: .announcement, argument: s)
        }
        #else
        NSAccessibility.post(element: NSApp as Any, notification: .announcementRequested,
                             userInfo: [.announcement: s,
                                        .priority: (polite ? NSAccessibilityPriorityLevel.medium : .high).rawValue])
        #endif
    }
}
