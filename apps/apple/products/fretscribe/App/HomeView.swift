import SwiftUI
import TabKit
import UniformTypeIdentifiers

/// Home: one primary way in (open a recording), the other ways in, and Your songs.
struct HomeView: View {
    @Environment(FretscribeModel.self) private var model
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
        @Bindable var model = model
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s6) {
                VStack(alignment: .leading, spacing: Space.s3) {
                    Text("\(Text("Turn a recording into")) \(Text("tab.").foregroundStyle(Color.Scribe.brandText))")
                        .font(Font.Scribe.display)
                        .foregroundStyle(Color.Scribe.text)
                        .accessibilityAddTraits(.isHeader)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Play it, record it, or open a file. Bandroom on your computer writes down the notes.")
                        .font(Font.Scribe.body)
                        .foregroundStyle(Color.Scribe.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ConnectionStatusRow()
                    .padding(.horizontal, Space.s4)
                    .padding(.vertical, Space.s2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.Scribe.surface, in: RoundedRectangle(cornerRadius: Radius.md))
                    .overlay(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Color.Scribe.border))
                waysIn
                songs
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
        .refreshable { await model.refreshComputerSongs() }
        .task { await model.refreshComputerSongs() }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { model.showSettings = true } label: { Label("Settings", systemImage: PlayIcon.settings.systemName) }
                    .accessibilityIdentifier("settings")
            }
        }
        .fileImporter(isPresented: $model.importing, allowedContentTypes: [.audio, .movie]) { result in
            if case .success(let url) = result { Task { await model.accept(url: url) } }
        }
        .dropDestination(for: URL.self) { urls, _ in
            guard let url = urls.first else { return false }
            Task { await model.accept(url: url) }
            return true
        } isTargeted: { dropTargeted = $0 }
        .confirmationDialog(Text("Delete this song?"), isPresented: Binding(get: { model.deleteTarget != nil },
                                                                             set: { if !$0 { model.deleteTarget = nil } }),
                            titleVisibility: .visible, presenting: model.deleteTarget) { entry in
            Button("Delete", role: .destructive) { model.delete(entry) }
            Button("Cancel", role: .cancel) {}
        } message: { entry in
            switch entry.location {
            case .local: Text("The song is removed from this device.")
            case .computer: Text("The song is removed from your computer.")
            }
        }
    }

    private var openButton: some View {
        Button { model.importing = true } label: {
            Label("Open a recording", systemImage: PlayIcon.importFile.systemName)
        }
        .accessibilityIdentifier("import")
    }

    @ViewBuilder private var waysIn: some View {
        if wide {
            VStack(spacing: Space.s4) {
                HStack(spacing: Space.s4) {
                    IconWell(systemName: PlayIcon.importFile.systemName)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Drop a recording here").font(Font.Scribe.headline)
                        Text("MP3, WAV, M4A, MP4 and most other formats").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                    }
                    Spacer(minLength: Space.s4)
                    openButton.buttonStyle(.primary)
                }
                .padding(Space.s6)
                .background(Color.Scribe.surfaceRaised, in: RoundedRectangle(cornerRadius: Radius.lg))
                .overlay(RoundedRectangle(cornerRadius: Radius.lg).strokeBorder(dropTargeted ? Color.Scribe.text : Color.Scribe.borderStrong,
                                                                                 lineWidth: dropTargeted ? 2 : 1))
                HStack(spacing: Space.s4) {
                    WayInCard(icon: PlayIcon.recordMic.systemName, title: String(localized: "Record with the microphone"),
                              subtitle: String(localized: "Play a riff or a whole song")) { model.showRecorder = true }
                        .accessibilityIdentifier("record")
                    #if os(macOS)
                    WayInCard(icon: PlayIcon.recordDevice.systemName, title: String(localized: "Record what's playing"),
                              subtitle: String(localized: "Sound from another app on this Mac")) { model.showCapture = true }
                        .accessibilityIdentifier("capture")
                    #endif
                }
            }
        } else {
            VStack(spacing: Space.s4) {
                openButton.buttonStyle(.primaryWide)
                WayInRow(icon: PlayIcon.recordMic.systemName, title: String(localized: "Record with the microphone"),
                         subtitle: String(localized: "Play a riff or a whole song")) { model.showRecorder = true }
                    .accessibilityIdentifier("record")
                    .card(padding: 0)
            }
        }
    }

    @ViewBuilder private var songs: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            SectionLabel(String(localized: "Your songs"))
            if model.songs.isEmpty {
                Text("Nothing written down yet. Record a riff or open a recording.")
                    .font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted)
                    .padding(.vertical, Space.s2)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(model.songs.enumerated()), id: \.element.id) { i, entry in
                        if i > 0 { Divider().overlay(Color.Scribe.border) }
                        SongRow(entry: entry)
                    }
                }
                .card(padding: 0)
            }
        }
    }
}

/// One song in Your songs: its title, what it is written for and the notes to check, or where it is.
struct SongRow: View {
    @Environment(FretscribeModel.self) private var model
    let entry: SongEntry

    var body: some View {
        HStack(spacing: Space.s2) {
            Button { model.open(entry) } label: {
                HStack(spacing: Space.s3) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.title).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text)
                        Text(SongWords.subtitle(entry)).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                    }
                    Spacer(minLength: Space.s2)
                    if model.openingSong == entry.id { ProgressView().controlSize(.small) }
                }
                .padding(.vertical, Space.s3)
                .frame(minHeight: 64)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("song-\(entry.title)")
            Menu {
                Button(role: .destructive) { model.deleteTarget = entry } label: { Label("Delete…", systemImage: PlayIcon.delete.systemName) }
            } label: {
                Image(systemName: PlayIcon.more.systemName).frame(width: 44, height: 44).contentShape(Rectangle())
            }
            .menuStyle(.button)
            .buttonStyle(.plain)
            .menuIndicator(.hidden)
            .accessibilityLabel(Text("More for \(entry.title)"))
        }
        .padding(.leading, Space.s4)
        .padding(.trailing, Space.s2)
        .contextMenu {
            Button(role: .destructive) { model.deleteTarget = entry } label: { Label("Delete…", systemImage: PlayIcon.delete.systemName) }
        }
    }
}

/// What a song's row and header say about it, in the player's words.
enum SongWords {
    static func subtitle(_ entry: SongEntry) -> String {
        let when = entry.date.formatted(.relative(presentation: .named, unitsStyle: .wide))
        var parts: [String] = [String(localized: "Tab"), when.prefix(1).uppercased() + when.dropFirst()]
        if case .computer = entry.location { parts.append(String(localized: "On your computer")) }
        if entry.toCheck > 0 { parts.append(String(localized: "\(entry.toCheck) notes to check")) }
        return parts.joined(separator: " · ")
    }
}
