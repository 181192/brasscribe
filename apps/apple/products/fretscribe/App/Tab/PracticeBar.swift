import SwiftUI
import TabKit

/// The transport's targets: reachable with an instrument in the hands.
private let transport: CGFloat = 64

/// The player under the tab, in its order: Play, back to the start (of the repeat), a bar back and a bar on, where the
/// song is, the speed, the bars to repeat, and Sound (what is heard, the count-in and the metronome). It wraps onto
/// as many rows as it needs. A song whose recording is not on this device plays the tab's own notes, and Sound says
/// what became of the recording and offers to get it from the computer when the computer is there; a tab that cannot
/// be followed has no sound, and says so here.
///
/// `place`: the bar (counted from 0) and the beat the recording is at. `follows`: the tab has the beats to follow the
/// recording by.
struct PracticeBar: View {
    let practice: PracticeModel
    let measures: [TabMeasure]
    let place: (bar: Int, beat: Int)?
    let follows: Bool
    let canFetch: Bool
    let onFetch: () -> Void

    @State private var choosing = false
    @State private var sounds = false
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        let state = practice.recording
        // Nothing is said while it is still being found out what there is to play: the recording looked for, the tab's sound made.
        if follows && (state == .looking || (state != .here && practice.tabSoundLoading)) {
            EmptyView()
        } else {
            VStack(spacing: 0) {
                Divider().overlay(Color.Scribe.border)
                if let words = TabWords.says(state, follows: follows, canFetch: canFetch), !(follows && practice.tabSound) {
                    RecordingNote(words: words, state: state, follows: follows, canFetch: canFetch, onFetch: onFetch)
                        .padding(.horizontal, Space.s4)
                        .padding(.vertical, Space.s3)
                } else {
                    controls
                }
            }
            .frame(maxWidth: .infinity)
            .background(Color.Scribe.bg)
            .accessibilityIdentifier("fs-practice")
            .onChange(of: state) { _, now in
                // What became of the recording is said once when it changes: getting it, and how that went.
                if let words = TabWords.says(now, follows: follows, canFetch: canFetch) { AccessibilityNotifier.announce(words, polite: true) }
            }
        }
    }

    private func number(_ bar: Int) -> String { measures[safe: bar]?.number ?? "\(bar + 1)" }

    private var controls: some View {
        let repeating = practice.repeating
        let noBarOn = place.map { !practice.hasBarOn($0.bar) } ?? false
        let speed = percentText(Double(practice.speed))
        return FlowLayout(spacing: Space.s3, lineSpacing: Space.s1) {
            HStack(spacing: 0) {
                Button(action: practice.toggle) {
                    Image(systemName: (practice.playing ? PlayIcon.pause : PlayIcon.play).systemName)
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(Color.Scribe.onPrimary)
                        .frame(width: transport, height: transport)
                        .background(Color.Scribe.primary, in: Circle())
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.space, modifiers: [])
                .accessibilityLabel(practice.playing ? String(localized: "Pause") : String(localized: "Play"))
                .accessibilityIdentifier("fs-practice-play")
                transportButton(PlayIcon.restart, repeating != nil ? String(localized: "Back to the start of the repeat") : String(localized: "Back to the start"),
                                id: "fs-practice-start", action: practice.toStart)
                transportButton(PlayIcon.previousBar, String(localized: "Previous bar"), id: "fs-practice-previous") { practice.step(-1) }
                // In the last bar there is no bar on: Next bar says so and looks off, but it keeps its place in the focus
                // order and keeps the focus. While the recording plays the bar changes on its own, so the reason is only
                // given once it stops.
                transportButton(PlayIcon.nextBar, String(localized: "Next bar"), id: "fs-practice-next", dimmed: noBarOn) { practice.step(1) }
                    .accessibilityValue(noBarOn && !practice.playing
                                        ? (repeating != nil ? String(localized: "Last bar of the repeat") : String(localized: "Last bar")) : "")
            }
            Text(place.map { TabWords.place(measures[safe: $0.bar], beat: $0.beat) } ?? "")
                .font(Font.Scribe.numeric.weight(.semibold))
                .foregroundStyle(Color.Scribe.text)
                .frame(minHeight: 44)
                .accessibilityIdentifier("fs-practice-place")
            HStack(spacing: 0) {
                // The word is for the eye: the value's own name already says "Speed 100 %". With large text it is left out.
                if !typeSize.isAccessibilitySize {
                    Text("Speed").font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted)
                        .padding(.trailing, Space.s1)
                        .accessibilityHidden(true)
                }
                stepButton("−", String(localized: "Slower"), id: "fs-practice-slower", enabled: practice.speed > PracticeSpeed.min, action: practice.slower)
                Text(speed)
                    .font(Font.Scribe.numeric)
                    .foregroundStyle(Color.Scribe.text)
                    .frame(minWidth: 56)
                    .accessibilityLabel(String(localized: "Speed \(speed)"))
                    .accessibilityIdentifier("fs-practice-speed")
                stepButton("+", String(localized: "Faster"), id: "fs-practice-faster", enabled: practice.speed < PracticeSpeed.max, action: practice.faster)
            }
            Button { choosing = true } label: {
                Label(TabWords.repeatChip(repeating, number: number), systemImage: repeating != nil ? "checkmark" : PlayIcon.loop.systemName)
                    .font(Font.Scribe.label)
                    .foregroundStyle(repeating != nil ? Color.Scribe.onSecondary : Color.Scribe.text)
                    .padding(.horizontal, Space.s4)
                    .frame(minHeight: 48)
                    .background {
                        RoundedRectangle(cornerRadius: Radius.md)
                            .fill(repeating != nil ? Color.Scribe.secondary : Color.clear)
                            .overlay(RoundedRectangle(cornerRadius: Radius.md)
                                .strokeBorder(repeating != nil ? Color.Scribe.text : Color.Scribe.borderStrong, lineWidth: 1))
                    }
                    .contentShape(RoundedRectangle(cornerRadius: Radius.md))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("fs-practice-repeat")
            // (Also when the tab's sound could not be made: Sound says so.)
            if practice.tabSound || practice.tabSoundFailed { soundButton }
        }
        .padding(.horizontal, Space.s3)
        .padding(.vertical, Space.s2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .onChange(of: practice.playing) { was, now in
            // When the recording stops, the place it stopped at is said once.
            if was && !now, let place { AccessibilityNotifier.announce(TabWords.place(measures[safe: place.bar], beat: place.beat), polite: true) }
        }
        .sheet(isPresented: $choosing) {
            RepeatBarsSheet(measures: measures, repeating: repeating, bar: place?.bar ?? 0) { bars in
                practice.repeat(bars)
                choosing = false
            } close: { choosing = false }
        }
        .sheet(isPresented: $sounds) {
            SoundSheet(practice: practice, canFetch: canFetch, onFetch: onFetch) { sounds = false }
        }
    }

    /// Sound: one small button, so the tab keeps the room. Its name says what is on, and it is filled when anything but
    /// the recording alone is.
    private var soundButton: some View {
        let on = practice.tabSound && (practice.hears != .recording || practice.countIn || practice.metronome)
        return Button { sounds = true } label: {
            Image(systemName: "speaker.wave.2")
                .font(.body.weight(.medium))
                .foregroundStyle(on ? Color.Scribe.onSecondary : Color.Scribe.text)
                .frame(width: 48, height: 48)
                .background {
                    RoundedRectangle(cornerRadius: Radius.md)
                        .fill(on ? Color.Scribe.secondary : Color.clear)
                        .overlay(RoundedRectangle(cornerRadius: Radius.md)
                            .strokeBorder(on ? Color.Scribe.text : Color.Scribe.borderStrong, lineWidth: 1))
                }
                .contentShape(RoundedRectangle(cornerRadius: Radius.md))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(TabWords.soundButton(practice.hears, countIn: practice.countIn && practice.tabSound, metronome: practice.metronome && practice.tabSound))
        .accessibilityIdentifier("fs-practice-sound")
    }

    private func transportButton(_ icon: PlayIcon, _ name: String, id: String, dimmed: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon.systemName)
                .font(.title3.weight(.medium))
                .foregroundStyle(Color.Scribe.text.opacity(dimmed ? 0.38 : 1))
                .frame(width: transport, height: transport)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(name)
        .accessibilityIdentifier(id)
    }
}

/// What became of the recording when it is not played: where it is, getting it, and how that went; with the button
/// that gets it.
struct RecordingNote: View {
    let words: String
    let state: RecordingState
    let follows: Bool
    let canFetch: Bool
    let onFetch: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            Text(words)
                .font(Font.Scribe.body)
                .foregroundStyle(Color.Scribe.text)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("fs-practice-says")
            if follows && state == .getting {
                ProgressView().progressViewStyle(.linear).tint(Color.Scribe.brand)
            }
            if follows && canFetch && TabWords.offersFetch(state) {
                Button(action: onFetch) {
                    Label(state == .notHere ? String(localized: "Get it from your computer") : String(localized: "Try again"),
                          systemImage: PlayIcon.download.systemName)
                }
                .buttonStyle(.outline)
                .accessibilityIdentifier("fs-practice-get")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Sound: what is heard (the recording, the tab's own notes, or both), whether a bar is counted in before the song
/// plays, and whether the beats tick. A choice is heard at once and the sheet stays open, so it can be tried. Without
/// the recording on the device only the tab's notes can be heard, and the sheet says how to get the recording.
struct SoundSheet: View {
    let practice: PracticeModel
    let canFetch: Bool
    let onFetch: () -> Void
    let close: () -> Void

    var body: some View {
        let here = practice.recording == .here
        let tab = practice.tabSound
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s3) {
                Text("Sound").font(Font.Scribe.title2).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                VStack(spacing: 0) {
                    ForEach(PracticeSound.allCases, id: \.self) { sound in
                        let on = practice.hears == sound
                        let can = sound == .recording ? here : tab && (here || sound == .tab)
                        Button { practice.hear(sound) } label: {
                            HStack(spacing: Space.s3) {
                                Image(systemName: on ? "largecircle.fill.circle" : "circle")
                                    .foregroundStyle(on ? Color.Scribe.text : Color.Scribe.borderStrong)
                                Text(TabWords.sound(sound)).font(Font.Scribe.body).foregroundStyle(Color.Scribe.text)
                                Spacer(minLength: 0)
                            }
                            .frame(minHeight: 48)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(!can)
                        .opacity(can ? 1 : 0.38)
                        .accessibilityAddTraits(on ? .isSelected : [])
                        .accessibilityIdentifier("fs-sound-\(sound.rawValue)")
                    }
                }
                if !here, let words = TabWords.says(practice.recording, follows: true, canFetch: canFetch) {
                    RecordingNote(words: words, state: practice.recording, follows: true, canFetch: canFetch, onFetch: onFetch)
                }
                // The tab's notes, the count-in and the metronome are one sound: without it they are off, and it says why.
                if !tab {
                    Text("This device couldn't make the sound for the tab's notes, the count-in and the metronome.")
                        .font(Font.Scribe.body).foregroundStyle(Color.Scribe.text).fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("fs-sound-failed")
                }
                Divider().overlay(Color.Scribe.border)
                toggle("Count-in", "One bar of clicks before it plays.", id: "fs-sound-count-in",
                       Binding(get: { practice.countIn }, set: { practice.countIn($0) }))
                toggle("Metronome", "A click on every beat.", id: "fs-sound-metronome",
                       Binding(get: { practice.metronome }, set: { practice.metronome($0) }))
                HStack {
                    Spacer()
                    Button("Done", action: close).buttonStyle(.plainText).keyboardShortcut(.cancelAction)
                        .accessibilityIdentifier("fs-sound-done")
                }
            }
            .padding(Space.s5)
        }
        .frame(minWidth: 320, idealWidth: 400)
        .pageBackground()
        .presentationDetents([.medium, .large])
    }

    private func toggle(_ label: LocalizedStringKey, _ tip: LocalizedStringKey, id: String, _ on: Binding<Bool>) -> some View {
        Toggle(isOn: on) {
            VStack(alignment: .leading, spacing: 2) {
                Text(label).font(Font.Scribe.body).foregroundStyle(Color.Scribe.text)
                Text(tip).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
            }
        }
        .tint(Color.Scribe.primary)
        .frame(minHeight: 48)
        .disabled(!practice.tabSound)
        .accessibilityIdentifier(id)
    }
}

/// A step down or up: a 44 pt button with a plain sign, named by what it does. Held down, it steps again and again.
@MainActor func stepButton(_ sign: String, _ name: String, id: String, enabled: Bool, action: @escaping () -> Void) -> some View {
    Button(action: action) {
        Text(verbatim: sign)
            .font(.title2)
            .foregroundStyle(Color.Scribe.text)
            .frame(width: 44, height: 44)
            .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .buttonRepeatBehavior(.enabled)
    .disabled(!enabled)
    .opacity(enabled ? 1 : 0.38)
    .accessibilityLabel(name)
    .accessibilityIdentifier(id)
}

/// The bars to repeat, chosen by their numbers with a step down and a step up each (nothing is dragged). It opens on the
/// repeat there is, or on four bars from the bar the song is in.
struct RepeatBarsSheet: View {
    let measures: [TabMeasure]
    let repeating: RepeatBars?
    let onSet: (RepeatBars?) -> Void
    let close: () -> Void
    @State private var from: Int
    @State private var to: Int

    init(measures: [TabMeasure], repeating: RepeatBars?, bar: Int, onSet: @escaping (RepeatBars?) -> Void, close: @escaping () -> Void) {
        self.measures = measures
        self.repeating = repeating
        self.onSet = onSet
        self.close = close
        let last = max(measures.count - 1, 0)
        let first = min(max(repeating?.first ?? bar, 0), last)
        _from = State(initialValue: first)
        _to = State(initialValue: min(max(repeating?.last ?? (bar + 3), first), last))
    }

    private var last: Int { max(measures.count - 1, 0) }
    private func number(_ i: Int) -> String { measures[safe: i]?.number ?? "\(i + 1)" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s3) {
                Text("Repeat bars").font(Font.Scribe.title2).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                Text("The recording plays these bars again and again.")
                    .font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
                stepper(String(localized: "From bar"), number(from), id: "from", down: from > 0, up: from < last,
                        { from -= 1 }, { from += 1; if to < from { to = from } })
                stepper(String(localized: "To bar"), number(to), id: "to", down: to > 0, up: to < last,
                        { to -= 1; if from > to { from = to } }, { to += 1 })
                if measures.first?.pickup == true {
                    Text("Bar 0 is the pickup bar.").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                }
                Button { onSet(RepeatBars(first: from, last: to)) } label: {
                    Text(from == to ? String(localized: "Repeat bar \(number(from))") : String(localized: "Repeat bars \(number(from)) to \(number(to))"))
                }
                .buttonStyle(.primaryWide)
                .padding(.top, Space.s2)
                .accessibilityIdentifier("fs-practice-repeat-set")
                HStack {
                    Spacer()
                    if repeating != nil {
                        Button("Stop repeating") { onSet(nil) }.buttonStyle(.plainText).accessibilityIdentifier("fs-practice-repeat-stop")
                    }
                    Button("Cancel", action: close).buttonStyle(.plainText).keyboardShortcut(.cancelAction)
                        .accessibilityIdentifier("fs-practice-repeat-cancel")
                }
            }
            .padding(Space.s5)
        }
        .frame(minWidth: 320, idealWidth: 400)
        .pageBackground()
        .presentationDetents([.medium, .large])
    }

    private func stepper(_ label: String, _ value: String, id: String, down: Bool, up: Bool,
                         _ earlier: @escaping () -> Void, _ later: @escaping () -> Void) -> some View {
        HStack(spacing: 0) {
            Text(label).font(Font.Scribe.body).foregroundStyle(Color.Scribe.text).frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityHidden(true)
            stepButton("−", String(localized: "\(label): one bar earlier"), id: "fs-practice-\(id)-down", enabled: down, action: earlier)
            Text(value)
                .font(Font.Scribe.headline.monospacedDigit())
                .foregroundStyle(Color.Scribe.text)
                .frame(minWidth: 40)
                .accessibilityLabel(Text(verbatim: "\(label) \(value)"))
                .accessibilityIdentifier("fs-practice-\(id)")
            stepButton("+", String(localized: "\(label): one bar later"), id: "fs-practice-\(id)-up", enabled: up, action: later)
        }
    }
}

/// Lays its children out in rows, left to right, starting a new row where the next one does not fit.
struct FlowLayout: Layout {
    var spacing: CGFloat
    var lineSpacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(subviews, width: proposal.width ?? .infinity)
        let width = rows.map(\.width).max() ?? 0
        let height = rows.reduce(0) { $0 + $1.height } + lineSpacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(subviews, width: bounds.width) {
            var x = bounds.minX
            for i in row.items {
                let size = subviews[i].sizeThatFits(.unspecified)
                subviews[i].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + lineSpacing
        }
    }

    private struct Row { var items: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> [Row] {
        var rows: [Row] = []
        var row = Row()
        for i in subviews.indices {
            let size = subviews[i].sizeThatFits(.unspecified)
            let needed = row.items.isEmpty ? size.width : row.width + spacing + size.width
            if !row.items.isEmpty && needed > width {
                rows.append(row)
                row = Row()
            }
            row.width = row.items.isEmpty ? size.width : row.width + spacing + size.width
            row.height = max(row.height, size.height)
            row.items.append(i)
        }
        if !row.items.isEmpty { rows.append(row) }
        return rows
    }
}
