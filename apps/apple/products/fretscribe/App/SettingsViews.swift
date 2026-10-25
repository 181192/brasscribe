import SwiftUI
import TabKit

/// Settings: what you play, your computer (connection and pairing), help and about.
struct SettingsView: View {
    @Environment(FretscribeModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    NavigationLink {
                        YourInstrumentView(fromSettings: true)
                    } label: {
                        LabeledContent { Text(InstrumentWords.summary(model.instrument)).foregroundStyle(Color.Scribe.textMuted) } label: {
                            Label { Text("Your instrument") } icon: { Image(systemName: PlayIcon.parts.systemName) }
                        }
                    }
                    .accessibilityIdentifier("fs-settings-instrument")
                } header: { Text("What you play") } footer: {
                    Text("Fretscribe remembers this for your tabs.").foregroundStyle(Color.Scribe.textMuted)
                }

                YourComputerSection()

                Section {
                    NavigationLink { HelpView() } label: { Label { Text("Help") } icon: { Image(systemName: PlayIcon.help.systemName) } }
                        .accessibilityIdentifier("fs-settings-help")
                    NavigationLink { AboutView() } label: { Label { Text("About") } icon: { Image(systemName: PlayIcon.info.systemName) } }
                        .accessibilityIdentifier("fs-settings-about")
                }
            }
            .formStyle(.grouped)
            .scrollContentBackground(.hidden)
            .pageBackground()
            .navigationTitle(Text("Settings"))
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        #if os(macOS)
        .sheetSize(minWidth: 520, idealWidth: 600, maxWidth: 720, minHeight: 480)
        #endif
    }
}

/// The words for the player's instrument.
enum InstrumentWords {
    static func name(_ instrument: Instrument) -> String {
        switch instrument {
        case .guitar: String(localized: "Guitar")
        case .bass: String(localized: "Bass")
        case .ukulele: String(localized: "Ukulele")
        case .mandolin: String(localized: "Mandolin")
        }
    }

    /// A kind of an instrument, by its strings or its size: "6-string guitar", "Baritone ukulele".
    static func kind(_ kind: FrettedInstrument) -> String {
        switch kind {
        case .guitar6, .guitar7, .guitar8: String(localized: "\(YourInstrument.stringsOf(kind) ?? 6)-string guitar")
        case .bass4, .bass5, .bass6: String(localized: "\(YourInstrument.stringsOf(kind) ?? 4)-string bass")
        case .ukulele: String(localized: "Ukulele")
        case .ukuleleBaritone: String(localized: "Baritone ukulele")
        case .mandolin: String(localized: "Mandolin")
        }
    }

    static func reads(_ reads: Reads) -> String {
        switch reads {
        case .tab: String(localized: "Tab")
        case .tabAndNotation: String(localized: "Tab and notation")
        case .notation: String(localized: "Notation")
        }
    }

    static func hand(_ hand: FrettingHand) -> String {
        switch hand {
        case .left: String(localized: "Left hand on the neck (most players)")
        case .right: String(localized: "Right hand on the neck (left-handed instrument)")
        case .rightUpsideDown: String(localized: "Right hand on the neck (instrument upside down)")
        }
    }

    /// Settings: "6-string guitar · Standard · Tab"
    static func summary(_ i: YourInstrument) -> String {
        let v = i.valid()
        return String(localized: "\(kind(v.kind)) · \(TabWords.tuning(v.tuning, kind: v.kind)) · \(reads(v.reads))")
    }
}

/// "Your instrument": the instrument, its strings or size, its usual tuning, which hand frets and what the player
/// reads. Saved when the player says so; leaving without saving keeps what was there.
struct YourInstrumentView: View {
    @Environment(FretscribeModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    var fromSettings = false
    var onSave: (() -> Void)?
    @State private var draft: YourInstrument?

    var body: some View {
        let value = (draft ?? model.instrument).valid()
        Form {
            Section {
                Text(fromSettings ? "Fretscribe remembers this for your tabs."
                     : "Fretscribe remembers this for your tabs. You can change it in Settings.")
                    .foregroundStyle(Color.Scribe.textMuted)
            }
            Section {
                Picker(selection: Binding(get: { value.instrument }, set: { draft = value.withInstrument($0) })) {
                    ForEach(Instrument.allCases, id: \.self) { Text(InstrumentWords.name($0)).tag($0) }
                } label: { Text("Instrument") }
                .accessibilityIdentifier("fs-instrument")
                if value.instrument.kinds.count > 1 {
                    Picker(selection: Binding(get: { value.kind }, set: { draft = value.withKind($0) })) {
                        ForEach(value.instrument.kinds, id: \.self) { Text(InstrumentWords.kind($0)).tag($0) }
                    } label: { Text(value.instrument == .ukulele ? "Size" : "Strings") }
                    .accessibilityIdentifier("fs-strings")
                }
                if value.tunings.count > 1 {
                    Picker(selection: Binding(get: { value.tuning }, set: { var d = value; d.tuning = $0; draft = d })) {
                        ForEach(value.tunings, id: \.self) { Text(TabWords.tuning($0, kind: value.kind)).tag($0) }
                    } label: { Text("Usual tuning") }
                    .accessibilityIdentifier("fs-tuning")
                }
            }
            Section {
                ChoiceList(title: String(localized: "Which hand is on the neck?"), choices: FrettingHand.allCases, chosen: value.hand,
                           words: InstrumentWords.hand) { var d = value; d.hand = $0; draft = d }
                    .accessibilityIdentifier("fs-hand")
            } footer: { Text("Tab looks the same either way.").foregroundStyle(Color.Scribe.textMuted) }
            Section {
                ChoiceList(title: String(localized: "You read"), choices: Reads.allCases, chosen: value.reads,
                           words: InstrumentWords.reads) { var d = value; d.reads = $0; draft = d }
                    .accessibilityIdentifier("fs-reads")
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .pageBackground()
        .navigationTitle(Text("Your instrument"))
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    model.instrument = value
                    onSave?()
                    if onSave == nil { dismiss() }
                }
                .accessibilityIdentifier("fs-instrument-save")
            }
        }
    }
}

/// One of a few choices, as rows at least 44 pt tall: the one chosen is marked, and read as selected.
struct ChoiceList<Choice: Hashable>: View {
    let title: String
    let choices: [Choice]
    let chosen: Choice
    let words: (Choice) -> String
    let choose: (Choice) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                .padding(.bottom, Space.s2)
            ForEach(choices, id: \.self) { c in
                Button { choose(c) } label: {
                    HStack(spacing: Space.s3) {
                        Image(systemName: c == chosen ? "largecircle.fill.circle" : "circle").foregroundStyle(Color.Scribe.text)
                            .accessibilityHidden(true)
                        Text(words(c)).foregroundStyle(Color.Scribe.text).fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(c == chosen ? [.isSelected] : [])
            }
        }
        .accessibilityElement(children: .contain)
    }
}

/// Help: what this app does, in its own words.
struct HelpView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                item("Write down a tab", "Open a recording, or record with the microphone. Say what it is, and Bandroom on your computer writes down the notes as tab for your instrument.")
                item("Check the notes marked ?", "A “?” above a note means Fretscribe wasn't sure of it. A boxed “!” marks a note your instrument can't play there. Listen to that bar of the recording to check it.")
                item("Practise with the tab", "Slow the recording down, and repeat the hard bars.")
                item("Your songs", "Every tab you make is kept under Your songs, on this device and on your computer.")
                item("Tabs are written on your computer", "Bandroom on your computer writes down the notes. Open it there, and connect in Settings.")
                item("Keys", "Space plays and pauses the recording. While the tab has the keyboard's focus, the right arrow goes a bar on, and the left arrow a bar back or to the start of the bars being repeated.")
            }
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text("Help"))
    }

    private func item(_ title: LocalizedStringKey, _ text: LocalizedStringKey) -> some View {
        VStack(alignment: .leading, spacing: Space.s1) {
            Text(title).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
            Text(text).font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// About: the version, and what the app is built with.
struct AboutView: View {
    private var version: String {
        let info = Bundle.main.infoDictionary
        return "\(info?["CFBundleShortVersionString"] as? String ?? "?") (\(info?["CFBundleVersion"] as? String ?? "?"))"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s4) {
                Text(verbatim: "Fretscribe").font(Font.Scribe.display).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                Text("Version \(version)").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                Text("Fretscribe is a non-commercial project. It uses alphaTab (MPL-2.0) with the Bravura font (SIL OFL 1.1) to draw the tab. Bandroom on your computer writes down the notes.")
                    .font(Font.Scribe.body).fixedSize(horizontal: false, vertical: true)
                Text("Titles are set in Atkinson Hyperlegible Next, and fret numbers in Fretscribe Tab (both SIL Open Font License 1.1).")
                    .font(Font.Scribe.body).fixedSize(horizontal: false, vertical: true)
                Link(destination: URL(string: "https://github.com/181192/brasscribe")!) { Text("Source code and licences") }
            }
            .foregroundStyle(Color.Scribe.text)
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text("About"))
    }
}

/// The first run: what the app does in three points, then Your instrument. Permissions are asked when first needed.
struct FirstRunView: View {
    @Environment(FretscribeModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var asking = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.s6) {
                    Text("\(Text("Tab from")) \(Text("any recording.").foregroundStyle(Color.Scribe.brandText))")
                        .font(Font.Scribe.display).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                        .fixedSize(horizontal: false, vertical: true)
                    point(PlayIcon.recordMic, "Record or open a recording",
                          "Play it, or open a song you have. Bandroom on your computer writes down the notes.")
                    point(PlayIcon.nextUncertain, "Check the notes marked ?",
                          "Notes Fretscribe isn't sure about get a “?”. Listen to the bar and decide.")
                    point(PlayIcon.loop, "Practise with the tab", "Slow it down and repeat the hard bars.")
                    HelperLine(systemImage: PlayIcon.info.systemName,
                               text: String(localized: "Your recordings stay on your own devices. Free, with nothing locked."))
                }
                .padding(Space.s5)
                .readingColumn()
            }
            .pageBackground()
            .safeAreaInset(edge: .bottom) {
                Button { asking = true } label: { Text("Get started") }
                    .buttonStyle(.primaryWide)
                    .padding(Space.s5)
                    .frame(maxWidth: ScribeDesign.Size.contentMaxWidth)
                    .accessibilityIdentifier("getStarted")
                    .afterTheContentItIsDockedUnder()
            }
            .navigationDestination(isPresented: $asking) {
                YourInstrumentView { model.firstRunDone = true; dismiss() }
            }
        }
        .interactiveDismissDisabled()
        #if os(macOS)
        .sheetSize(minWidth: 520, idealWidth: 600, maxWidth: 680, minHeight: 520)
        #endif
    }

    private func point(_ icon: PlayIcon, _ title: LocalizedStringKey, _ text: LocalizedStringKey) -> some View {
        HStack(alignment: .top, spacing: Space.s4) {
            Image(systemName: icon.systemName)
                .font(.title3).foregroundStyle(Color.Scribe.text)
                .frame(width: 44, height: 44)
                .background(Color.Scribe.secondary, in: RoundedRectangle(cornerRadius: Radius.md))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Space.s1) {
                Text(title).font(Font.Scribe.headline)
                Text(text).font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
