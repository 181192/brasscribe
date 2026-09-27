import SwiftUI
import UniformTypeIdentifiers

/// Home: one primary way in (open a recording), the other ways in as rows, and the scores.
struct HomeView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.horizontalSizeClass) private var hsize
    @State private var dropTargeted = false

    private var wide: Bool {
        #if os(macOS)
        true
        #else
        hsize == .regular
        #endif
    }

    var body: some View {
        @Bindable var app = app
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s6) {
                VStack(alignment: .leading, spacing: Space.s3) {
                    DisplayTitle(text: String(localized: "Turn a recording into"), emphasis: String(localized: "a score."), size: wide ? 48 : 40)
                    Text("Play it, record it, or open a file. Brasscribe writes the parts for your band.")
                        .font(Font.Brasscribe.body)
                        .foregroundStyle(Color.Brasscribe.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ConnectionStatusRow()
                    .padding(.horizontal, Space.s4)
                    .padding(.vertical, Space.s2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.Brasscribe.surface, in: RoundedRectangle(cornerRadius: Radius.md))
                    .overlay(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Brasscribe.border))
                if wide { wideWaysIn } else { phoneWaysIn }
                HelperLine(systemImage: BrasscribeIcon.info.systemName,
                           text: String(localized: "Links to streaming sites can't be downloaded. Play the music and record it instead."))
                scores
            }
            .padding(.horizontal, wide ? Space.s10 : Space.s5)
            .padding(.vertical, Space.s6)
            .frame(maxWidth: wide ? 920 : .infinity, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .pageBackground()
        .navigationTitle(Text("Home"))
        .toolbar(removing: .title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .refreshable { await app.refreshComputerScores() }
        .task { await app.refreshComputerScores() }
        .toolbar {
            #if os(iOS)
            if !wide {
                ToolbarItem(placement: .topBarLeading) { Lockup(product: false).fixedSize() }
            }
            #endif
            ToolbarItemGroup(placement: .primaryAction) {
                Button { app.showSettings = true } label: { Label("Settings", systemImage: BrasscribeIcon.settings.systemName) }
            }
        }
        .fileImporter(isPresented: $app.importing, allowedContentTypes: [.audio, .movie, .xml, .json, UTType(filenameExtension: "musicxml") ?? .xml]) { result in
            if case .success(let url) = result { Task { await app.accept(url: url) } }
        }
        .dropDestination(for: URL.self) { urls, _ in
            guard let url = urls.first else { return false }
            Task { await app.accept(url: url) }
            return true
        } isTargeted: { dropTargeted = $0 }
    }

    // MARK: ways in

    private var openButton: some View {
        Button { app.importing = true } label: {
            Label("Open a recording", systemImage: BrasscribeIcon.importFile.systemName)
        }
        .accessibilityIdentifier("import")
    }

    private var phoneWaysIn: some View {
        VStack(spacing: Space.s4) {
            openButton.buttonStyle(.primaryWide)
            VStack(spacing: 0) {
                WayInRow(icon: BrasscribeIcon.recordMic.systemName, title: String(localized: "Record with the microphone"),
                         subtitle: String(localized: "Play your part in the room")) { app.showRecorder = true }
                    .accessibilityIdentifier("record")
                if app.fixtureDirectory != nil {
                    Divider().overlay(Color.Brasscribe.border)
                    WayInRow(icon: BrasscribeIcon.score.systemName, title: String(localized: "Try the demo"),
                             subtitle: String(localized: "“Mikkel”, cornet solo with band")) { app.startDemo() }
                        .accessibilityIdentifier("demo")
                }
            }
            .card(padding: 0)
        }
    }

    private var wideWaysIn: some View {
        VStack(spacing: Space.s4) {
            HStack(spacing: Space.s4) {
                IconWell(systemName: BrasscribeIcon.importFile.systemName)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Drop a recording here").font(Font.Brasscribe.headline)
                    Text("MP3, WAV, M4A, MP4 and most other formats").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                }
                Spacer(minLength: Space.s4)
                openButton.buttonStyle(.primary)
            }
            .padding(Space.s6)
            .background(Color.Brasscribe.surfaceRaised, in: RoundedRectangle(cornerRadius: Radius.lg))
            .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(dropTargeted ? Color.Brasscribe.text : Color.Brasscribe.borderStrong,
                                                                             lineWidth: dropTargeted ? 2 : 1))
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: Space.s4)], spacing: Space.s4) {
                WayInCard(icon: BrasscribeIcon.recordMic.systemName, title: String(localized: "Record with the microphone"),
                          subtitle: String(localized: "Play your part in the room")) { app.showRecorder = true }
                    .accessibilityIdentifier("record")
                #if os(macOS)
                WayInCard(icon: BrasscribeIcon.recordDevice.systemName, title: String(localized: "Record what's playing"),
                          subtitle: String(localized: "Sound from another app on this Mac")) { app.showCapture = true }
                    .accessibilityIdentifier("capture")
                #endif
                if app.fixtureDirectory != nil {
                    WayInCard(icon: BrasscribeIcon.score.systemName, title: String(localized: "Try the demo"),
                              subtitle: String(localized: "“Mikkel”, cornet solo with band")) { app.startDemo() }
                        .accessibilityIdentifier("demo")
                }
            }
        }
    }

    // MARK: scores

    @ViewBuilder private var scores: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            SectionLabel(String(localized: "Your scores"))
            if app.scores.isEmpty {
                HStack(spacing: Space.s3) {
                    BrandMark(size: 32)
                    Text("Your scores appear here after the first recording.")
                        .font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                }
                .padding(.vertical, Space.s2)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(app.scores.enumerated()), id: \.element.id) { i, entry in
                        if i > 0 { Divider().overlay(Color.Brasscribe.border) }
                        HStack(spacing: Space.s2) {
                            Button { app.open(entry) } label: {
                                HStack(spacing: Space.s3) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(entry.title).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                                        Text(entry.summary).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                                    }
                                    Spacer(minLength: Space.s2)
                                    if app.openingScore == entry.id { ProgressView().controlSize(.small) }
                                }
                                .padding(.vertical, Space.s3)
                                .frame(minHeight: 64)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("piece-\(entry.title)")
                            ScoreOptionsMenu(entry: entry)
                        }
                        .padding(.leading, Space.s4)
                        .padding(.trailing, Space.s2)
                        .contextMenu { ScoreOptionItems(entry: entry) }
                    }
                }
                .card(padding: 0)
            }
        }
    }
}

/// A list row that leads somewhere: icon well, title, subtitle, chevron. At least 60 pt tall.
struct WayInRow: View {
    let icon: String
    let title: String
    var subtitle: String?
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: Space.s4) {
                IconWell(systemName: icon)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                    if let subtitle { Text(subtitle).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted) }
                }
                Spacer(minLength: Space.s2)
                Image(systemName: BrasscribeIcon.open.systemName).foregroundStyle(Color.Brasscribe.textMuted).accessibilityHidden(true)
            }
            .padding(.horizontal, Space.s4)
            .padding(.vertical, Space.s3)
            .frame(minHeight: 60)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// The desktop version of a way in: a card with an icon well, title and subtitle.
struct WayInCard: View {
    let icon: String
    let title: String
    let subtitle: String
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: Space.s3) {
                IconWell(systemName: icon)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Font.Brasscribe.headline).foregroundStyle(Color.Brasscribe.text)
                    Text(subtitle).font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .card()
            .contentShape(RoundedRectangle(cornerRadius: Radius.lg))
        }
        .buttonStyle(.plain)
    }
}

/// First run: three points and Get started. Permissions are asked when first needed.
struct FirstRunView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: Space.s6) {
                    BrandMark(size: 56)
                    DisplayTitle(text: String(localized: "Scores for your band, from"), emphasis: String(localized: "any recording."), size: 44)
                }
                .padding(.horizontal, Space.s5)
                .padding(.top, Space.s10)
                .padding(.bottom, Space.s8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.Brasscribe.brassTint)

                VStack(alignment: .leading, spacing: Space.s6) {
                    point(icon: Image(systemName: BrasscribeIcon.recordMic.systemName), title: String(localized: "Record or import"),
                          text: String(localized: "Play the piece, record a rehearsal, or open a file you have."))
                    point(icon: UncertainMark(level: .veryUncertain), title: String(localized: "Check the marked notes"),
                          text: String(localized: "Notes Brasscribe isn't sure about get a “?”. You decide."))
                    point(icon: Image(systemName: BrasscribeIcon.playAlong.systemName), title: String(localized: "Practise with the band"),
                          text: String(localized: "Mute your part, slow it down, loop the hard bars."))
                    HelperLine(systemImage: BrasscribeIcon.info.systemName,
                               text: String(localized: "Recordings stay on your own devices."))
                }
                .padding(Space.s5)
            }
            .readingColumn()
        }
        .pageBackground()
        .safeAreaInset(edge: .bottom) {
            Button {
                UserDefaults.standard.set(true, forKey: "firstRunDone")
                dismiss()
            } label: { Text("Get started") }
            .buttonStyle(.primaryWide)
            .padding(Space.s5)
            .frame(maxWidth: BrasscribeDesign.Size.contentMaxWidth)
            .accessibilityIdentifier("getStarted")
        }
        .interactiveDismissDisabled()
        #if os(macOS)
        .frame(minWidth: 520, minHeight: 640)
        #endif
    }

    private func point(icon: some View, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: Space.s4) {
            icon
                .font(.title3)
                .foregroundStyle(Color.Brasscribe.text)
                .frame(width: 44, height: 44)
                .background(Color.Brasscribe.secondary, in: RoundedRectangle(cornerRadius: Radius.md))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Space.s1) {
                Text(title).font(Font.Brasscribe.headline)
                Text(text).font(Font.Brasscribe.body).foregroundStyle(Color.Brasscribe.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
