import AVFoundation
import ImageIO
import PhotosUI
import SwiftUI
import TranscriptionKit
import UniformTypeIdentifiers
#if os(iOS)
import UIKit
#endif

// Printed music from a picture, a photo or a PDF: the pages in the order they are read, sending them to the computer,
// and what can go wrong, in the player's words. Each app says what becomes of the notes once they are read.

/// The pages in hand, in the order they will be read. Each is kept as it is sent (`Pages.prepare`): the picture or PDF
/// as it was, or another picture as an upright JPEG. They are kept on the device with their order (`pages.json`), so
/// they are still in hand when the system closed the app, until they are read or removed.
@Observable @MainActor
final class PageList {
    struct Page: Identifiable, Hashable {
        let id = UUID()
        let url: URL
        /// The file's name, as the player chose it ("IMG_2031.HEIC"), or "Sheet music" for a photo.
        let name: String
        /// How many pages it holds: a PDF's every page counts, as the engine counts them.
        var count: Int = 1
        var isPDF: Bool { url.pathExtension == "pdf" }
    }

    private(set) var pages: [Page] = [] { didSet { save() } }
    /// Pages in hand, every page of a PDF counted: at most `Pages.maxPages`.
    var pageCount: Int { pages.reduce(0) { $0 + $1.count } }
    /// Files are being made ready (converted, copied) off the main thread.
    private(set) var adding = 0
    /// What happened to the last pages added or moved, said under the list (and to a screen reader).
    var status: String?
    private let folder: URL

    /// Where an app keeps its pages: in its own support folder, so two apps on one Mac keep theirs apart.
    static var appFolder: URL {
        URL.applicationSupportDirectory.appending(path: Bundle.main.bundleIdentifier ?? "Play", directoryHint: .isDirectory)
            .appending(path: "Pages", directoryHint: .isDirectory)
    }

    /// The pages kept in `folder`, in their order. A page whose file is gone is left out. When the index was read, a
    /// file it does not name (left by an add that was cut short) is deleted; when it is missing or can't be read, no
    /// file is deleted: the pages found are kept, oldest first, under a plain name, and the index is written again.
    init(folder: URL = PageList.appFolder) {
        self.folder = folder
        let fm = FileManager.default
        let files = ((try? fm.contentsOfDirectory(atPath: folder.path)) ?? []).filter { $0 != Self.index }
        let indexURL = folder.appending(path: Self.index)
        if let data = try? Data(contentsOf: indexURL), let kept = try? JSONDecoder().decode([Kept].self, from: data) {
            let found = kept.filter { fm.fileExists(atPath: folder.appending(path: $0.file).path) }
            pages = found.map { Page(url: folder.appending(path: $0.file), name: $0.name, count: $0.count) }
            let named = Set(found.map(\.file))
            for file in files where !named.contains(file) { try? fm.removeItem(at: folder.appending(path: file)) }
        } else if !files.isEmpty {
            pages = Self.rebuilt(files.map { folder.appending(path: $0) })
            save()
        }
    }

    /// Pages from their files alone, when the index is gone: those that are a page the engine reads, oldest first.
    private static func rebuilt(_ urls: [URL]) -> [Page] {
        func made(_ url: URL) -> Date { (try? url.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? .distantPast }
        return urls.sorted { made($0) < made($1) }.compactMap { url in
            guard let reader = try? FileHandle(forReadingFrom: url) else { return nil }
            defer { try? reader.close() }
            guard let head = try? reader.read(upToCount: 12), let format = Pages.format(of: head) else { return nil }
            var count = 1
            if format == .pdf, case .pages(let n) = Pages.readPDF(url) { count = n }
            return Page(url: url, name: String(localized: "Sheet music"), count: count)
        }
    }

    /// One page as it is kept: its file in the folder, the name it is shown with, and how many pages it holds.
    private struct Kept: Codable { let file: String; let name: String; let count: Int }
    private static let index = "pages.json"

    private func save() {
        let kept = pages.map { Kept(file: $0.url.lastPathComponent, name: $0.name, count: $0.count) }
        Self.makeFolder(folder)
        try? JSONEncoder().encode(kept).write(to: folder.appending(path: Self.index), options: .atomic)
    }

    /// The folder, left out of the device's backups: the pages are working copies the player can choose again.
    private static func makeFolder(_ folder: URL) {
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        var url = folder
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try? url.setResourceValues(values)
    }

    /// Files chosen or shared, in their order. Each is made ready off the main thread and joins the list as it is
    /// ready, so the screen stays live with forty large photos. A file that is no page, a PDF that cannot be opened, or
    /// one too large is left out and said; pages past `Pages.maxPages` (a PDF's every page counted) are left out.
    func add(_ urls: [URL]) async {
        var notPages = 0, tooLarge = 0, locked = 0, damaged = 0, over = 0
        adding += 1
        defer { adding -= 1 }
        for url in urls {
            guard pageCount < Pages.maxPages else { over += 1; continue }
            let folder = self.folder
            let made = await Task.detached(priority: .userInitiated) { () -> Result<Pages.Prepared, Error> in
                let scoped = url.startAccessingSecurityScopedResource()
                defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                return Result { try Pages.prepare(url, into: folder) }
            }.value
            switch made {
            case .success(let page) where pageCount + page.pages > Pages.maxPages:
                try? FileManager.default.removeItem(at: page.url)
                over += 1
            case .success(let page):
                pages.append(Page(url: page.url, name: url.lastPathComponent, count: page.pages))
            case .failure(Pages.Refusal.tooLarge):
                tooLarge += 1
            case .failure(Pages.Refusal.lockedPDF):
                locked += 1
            case .failure(Pages.Refusal.damagedPDF):
                damaged += 1
            case .failure:
                notPages += 1
            }
        }
        status = PagesWords.added(notPages: notPages, tooLarge: tooLarge, locked: locked, damaged: damaged, over: over)
        if let status { AccessibilityNotifier.announce(status) }
    }

    /// A photo taken here or picked from the photo library, made an upright JPEG off the main thread.
    func add(photo data: Data) async {
        guard pageCount < Pages.maxPages else { status = PagesWords.added(over: 1); return }
        let folder = self.folder
        adding += 1
        defer { adding -= 1 }
        let made = await Task.detached(priority: .userInitiated) { Result { try Pages.photo(data, into: folder) } }.value
        switch made {
        case .success(let url) where pageCount < Pages.maxPages:
            pages.append(Page(url: url, name: String(localized: "Sheet music")))
            status = nil
        case .success(let url):
            try? FileManager.default.removeItem(at: url)
            status = PagesWords.added(over: 1)
        case .failure:
            status = PagesWords.added(notPages: 1)
        }
    }

    func move(_ i: Int, by step: Int) {
        let j = i + step
        guard pages.indices.contains(i), pages.indices.contains(j) else { return }
        pages.swapAt(i, j)
        status = String(localized: "Page \(i + 1) is now page \(j + 1).")
        AccessibilityNotifier.announce(status!)
    }

    func remove(_ i: Int) {
        guard pages.indices.contains(i) else { return }
        try? FileManager.default.removeItem(at: pages[i].url)
        pages.remove(at: i)
        status = String(localized: "Page \(i + 1) is removed.")
        AccessibilityNotifier.announce(status!)
    }

    /// The pages were read into a score or a tab: they are let go.
    func clear() {
        for p in pages { try? FileManager.default.removeItem(at: p.url) }
        pages = []
        status = nil
    }
}

/// What goes wrong with pages, in the player's words: the computer's refusals, a job that could not read them, and
/// what this device leaves out.
enum PagesWords {
    /// The words for `error` when it is about pages; nil for anything else (the app's own words then).
    static func of(_ error: Error) -> String? {
        if let e = error as? TranscriptionError {
            if let refused = e.pagesRefused { return words(refused) }
            if let failed = e.pagesFailure { return words(failed) }
            if case .http(413, _) = e { return words(Pages.Refused.tooManyPages) }
        }
        return nil
    }

    /// A title more specific than the app's "couldn't be made", where there is one.
    static func title(_ error: Error) -> String? {
        switch (error as? TranscriptionError)?.pagesFailure {
        case .noMusic: String(localized: "No notes were found on the page")
        case .onlyTab: String(localized: "Only a tab staff was found")
        case nil: (error as? TranscriptionError)?.pagesRefused == .notAPage ? String(localized: "That isn't a picture or a PDF") : nil
        default: String(localized: "The notes couldn't be read")
        }
    }

    static func words(_ refused: Pages.Refused) -> String {
        switch refused {
        case .notAPage: String(localized: "One of the pages is not a picture or a PDF that Bandroom can read.")
        case .wrongInput: String(localized: "Bandroom on your computer can't read sheet music yet. Update Bandroom there, then try again.")
        case .pageTooLarge: String(localized: "One of the pages is too large for Bandroom to read: a file can be 50 MB at most. Split a large PDF into parts.")
        case .tooManyPages: String(localized: "There are more than 40 pages in all (every page of a PDF counts). Send fewer at a time.")
        case .readerMissing: String(localized: "The reader of printed music is not installed on your computer. In Bandroom there, open Settings, find Sheet music from pictures and choose Install the reader. Then try again.")
        }
    }

    static func words(_ failure: Pages.Failure) -> String {
        switch failure {
        case .noMusic: String(localized: "Bandroom reads printed notes on a staff. Take the picture straight on, in good light, with the whole page sharp. Handwritten music and tab are not read.")
        case .onlyTab: String(localized: "Only a tab staff was found on the page. Bandroom reads notes on a staff, not tab.")
        case .tooManyPages: words(Pages.Refused.tooManyPages)
        case .pageTooLarge: words(Pages.Refused.pageTooLarge)
        case .readerFilesMissing: String(localized: "Your computer couldn't download the files its reader of printed music needs. Check its internet connection, then send the pages again.")
        case .diskFull: String(localized: "Your computer's disk is full. Free some space on it, then send the pages again.")
        case .notRead: String(localized: "Something went wrong while Bandroom on your computer was reading the pages. Try a sharper, straighter picture, or a scan.")
        }
    }

    /// "3 pages waiting" on Home's way in, when pages are kept from before; nil when there are none.
    static func waiting(_ count: Int) -> String? {
        switch count {
        case 0: nil
        case 1: String(localized: "1 page waiting")
        default: String(localized: "\(count) pages waiting")
        }
    }

    /// What was left out of the pages just added, or nil when nothing was.
    static func added(notPages: Int = 0, tooLarge: Int = 0, locked: Int = 0, damaged: Int = 0, over: Int = 0) -> String? {
        var said: [String] = []
        if notPages == 1 { said.append(String(localized: "One file is not a picture or a PDF, so it was left out.")) }
        if notPages > 1 { said.append(String(localized: "\(notPages) files are not pictures or PDFs, so they were left out.")) }
        // Told apart, as on the other apps: the player can unlock the first, not the second.
        if locked > 0 { said.append(String(localized: "A PDF is locked with a password, so it can't be read and was left out. Open it in another app and save it without the password.")) }
        if damaged > 0 { said.append(String(localized: "A PDF is damaged, so it can't be opened and was left out. Get it again from where it came from.")) }
        if tooLarge > 0 { said.append(words(Pages.Refused.pageTooLarge)) }
        if over > 0 { said.append(String(localized: "At most 40 pages can be read at once, every page of a PDF counted. The rest were left out.")) }
        return said.isEmpty ? nil : said.joined(separator: " ")
    }
}

/// "Sheet music from a picture": the pages in order, ways to add more (pictures or a PDF, the photo library, the
/// camera), each page moved or removed, and Read the notes, which needs the computer.
struct PagesView: View {
    @Bindable var list: PageList
    /// What the app makes of the pages: "… a score you can play from", "… a tab for your instrument".
    let lead: String
    let computerThere: Bool
    /// Whether the camera may be used, asked of the system (a parameter so the screen catalogue can show a refusal).
    var cameraStatus: () -> AVAuthorizationStatus = { AVCaptureDevice.authorizationStatus(for: .video) }
    let onRead: () -> Void

    @State private var choosingFiles = false
    @State private var photos: [PhotosPickerItem] = []
    @State private var takingPhoto = false
    /// The camera was refused for this app: the camera row says so and leads to Settings instead.
    @State private var cameraRefused = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                Text("Sheet music from a picture").font(Font.Scribe.display).foregroundStyle(Color.Scribe.text)
                    .accessibilityAddTraits(.isHeader)
                Text(lead).font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
                adding
                if !list.pages.isEmpty { pageRows }
                if list.adding > 0 {
                    HStack(spacing: Space.s2) {
                        ProgressView().controlSize(.small)
                        Text("Getting the pages ready…").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.text)
                    }
                    .accessibilityElement(children: .combine)
                }
                if let status = list.status {
                    Text(status).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.text).fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("pages-status")
                }
                // the way to connect; the reason is docked with Read the notes
                if !computerThere { ConnectionStatusRow() }
                if PageActions.followContent { readRow }
            }
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text("Sheet music from a picture"))
        .toolbar(removing: .title)
        .bottomActions { readRow.padding(.horizontal, Space.s5).padding(.vertical, Space.s3).readingColumn() }
        .fileImporter(isPresented: $choosingFiles, allowedContentTypes: [.image, .pdf], allowsMultipleSelection: true) { result in
            if case .success(let urls) = result { Task { await list.add(urls) } }
        }
        .onChange(of: photos) { _, picked in
            guard !picked.isEmpty else { return }
            Task {
                // in the order they were picked
                for item in picked { if let data = try? await item.loadTransferable(type: Data.self) { await list.add(photo: data) } }
                photos = []
            }
        }
        #if os(iOS)
        .onAppear { cameraRefused = CameraAccess.of(cameraStatus()) == .refused }
        .fullScreenCover(isPresented: $takingPhoto) {
            CameraPicker { data in Task { await list.add(photo: data) } }.ignoresSafeArea()
        }
        #endif
    }

    /// Read the notes, with why it can't be pressed yet beside it: docked at the bottom on iPhone and iPad, after the
    /// content on the Mac.
    private var readRow: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            if !computerThere {
                Text("Reading sheet music needs Bandroom on your computer.").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.text)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Button(action: onRead) { Text("Read the notes") }
                .buttonStyle(PrimaryButtonStyle(fullWidth: !PageActions.followContent))
                .disabled(list.pages.isEmpty || !computerThere || list.adding > 0)
                .accessibilityHint(list.pages.isEmpty ? Text("Add a page first.")
                                   : computerThere ? Text(verbatim: "") : Text("Reading sheet music needs Bandroom on your computer."))
                .accessibilityIdentifier("pages-read")
                .frame(maxWidth: .infinity, alignment: PageActions.followContent ? .trailing : .center)
        }
    }

    /// Above the list, so they stay in reach with forty pages; once a page is in hand they say "add" and lose their
    /// second line.
    private var adding: some View {
        let first = list.pages.isEmpty
        return VStack(spacing: 0) {
            WayInRow(icon: PlayIcon.importFile.systemName,
                     title: first ? String(localized: "Choose pictures or a PDF") : String(localized: "Add pictures or a PDF"),
                     subtitle: first ? String(localized: "Several pages become one piece, in the order you set") : nil) { choosingFiles = true }
                .accessibilityIdentifier("pages-choose")
            Divider().overlay(Color.Scribe.border)
            PhotosPicker(selection: $photos, maxSelectionCount: max(1, Pages.maxPages - list.pageCount), selectionBehavior: .ordered,
                         matching: .images) {
                WayInLabel(icon: PlayIcon.score.systemName, title: String(localized: "Choose from your photos"),
                           subtitle: first ? String(localized: "A screenshot or a photo of the notes") : nil)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("pages-photos")
            #if os(iOS)
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
                Divider().overlay(Color.Scribe.border)
                WayInRow(icon: PlayIcon.takePhoto.systemName,
                         title: first ? String(localized: "Take a photo of a page") : String(localized: "Take a photo of the next page"),
                         subtitle: cameraRefused ? CameraAccess.refusedWords
                            : first ? String(localized: "Straight on, in good light, with the whole page in the picture") : nil) { useCamera() }
                    .accessibilityIdentifier("pages-camera")
                    .accessibilityHint(cameraRefused ? Text("Opens Settings for this app") : Text(verbatim: ""))
                if cameraRefused {
                    Button { CameraAccess.openSettings() } label: { Text("Open Settings") }
                        .buttonStyle(.outline)
                        .padding(.horizontal, Space.s4)
                        .padding(.bottom, Space.s3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier("pages-camera-settings")
                }
            }
            #endif
        }
        .card(padding: 0)
        .disabled(list.pageCount >= Pages.maxPages)
    }

    #if os(iOS)
    /// The camera row: the camera when it is allowed; the system's question the first time; Settings once refused.
    private func useCamera() {
        switch CameraAccess.of(cameraStatus()) {
        case .open: takingPhoto = true
        case .ask:
            AVCaptureDevice.requestAccess(for: .video) { granted in
                Task { @MainActor in
                    if granted { takingPhoto = true } else { cameraRefused = true; AccessibilityNotifier.announce(CameraAccess.refusedWords) }
                }
            }
        case .refused:
            if cameraRefused { CameraAccess.openSettings() } else { cameraRefused = true; AccessibilityNotifier.announce(CameraAccess.refusedWords) }
        }
    }
    #endif

    private var pageRows: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            SectionLabel(String(localized: "Pages, in the order they are read"))
            if list.pages.count > 1 {
                Text("The pages are read in this order. Move a page to change it.")
                    .font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
            }
            VStack(spacing: 0) {
                ForEach(Array(list.pages.enumerated()), id: \.element.id) { i, page in
                    if i > 0 { Divider().overlay(Color.Scribe.border) }
                    PageRow(page: page, place: i + 1, last: i == list.pages.count - 1,
                            up: { list.move(i, by: -1) }, down: { list.move(i, by: 1) }, remove: { list.remove(i) })
                }
            }
            .card(padding: 0)
        }
    }
}

/// One page: a small picture of it, its place and name, and the buttons that move it or take it out. The place and name
/// are one element for a screen reader; each button is its own, named with the page's place.
private struct PageRow: View {
    let page: PageList.Page
    let place: Int
    let last: Bool
    let up: () -> Void
    let down: () -> Void
    let remove: () -> Void
    @State private var thumbnail: CGImage?

    var body: some View {
        HStack(spacing: Space.s3) {
            Group {
                if let thumbnail { Image(decorative: thumbnail, scale: 1).resizable().scaledToFit() }
                else { Image(systemName: PlayIcon.file.systemName).foregroundStyle(Color.Scribe.textMuted) }
            }
            .frame(width: 44, height: 56)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 4))
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Page \(place)").font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text)
                Text(page.count > 1 ? String(localized: "\(page.name) · \(page.count) pages") : page.name)
                    .font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted).lineLimit(2)
            }
            .accessibilityElement(children: .combine)
            Spacer(minLength: Space.s2)
            HStack(spacing: 0) {
                button(PlayIcon.choose.systemName, rotated: true, String(localized: "Move page \(place) up"), disabled: place == 1, up)
                button(PlayIcon.choose.systemName, rotated: false, String(localized: "Move page \(place) down"), disabled: last, down)
                button(PlayIcon.delete.systemName, rotated: false, String(localized: "Remove page \(place)"), disabled: false, remove)
            }
        }
        .padding(.leading, Space.s4)
        .padding(.trailing, Space.s2)
        .padding(.vertical, Space.s2)
        .frame(minHeight: 64)
        .accessibilityIdentifier("page-\(place)")
        .task(id: page.url) { thumbnail = await Self.thumbnail(of: page.url) }
    }

    private func button(_ icon: String, rotated: Bool, _ label: String, disabled: Bool, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon).rotationEffect(.degrees(rotated ? 180 : 0)).frame(width: 44, height: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(disabled ? Color.Scribe.borderStrong : Color.Scribe.text)
        .disabled(disabled)
        .accessibilityLabel(Text(label))
        .help(Text(label))
    }

    /// A picture's small version, read off the main thread and never whole; a PDF's first page.
    nonisolated static func thumbnail(of url: URL) async -> CGImage? {
        await Task.detached(priority: .utility) {
            if url.pathExtension == "pdf" {
                guard let doc = CGPDFDocument(url as CFURL), let page = doc.page(at: 1) else { return nil }
                let box = page.getBoxRect(.mediaBox)
                let scale = 112 / max(box.width, box.height, 1)
                let w = Int(box.width * scale), h = Int(box.height * scale)
                guard let ctx = CGContext(data: nil, width: max(w, 1), height: max(h, 1), bitsPerComponent: 8, bytesPerRow: 0,
                                          space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
                ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
                ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
                ctx.scaleBy(x: scale, y: scale)
                ctx.drawPDFPage(page)
                return ctx.makeImage()
            }
            guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
            return CGImageSourceCreateThumbnailAtIndex(src, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                                                kCGImageSourceCreateThumbnailWithTransform: true,
                                                                kCGImageSourceThumbnailMaxPixelSize: 112] as CFDictionary)
        }.value
    }
}

/// A way-in row's look, for a control that is not a plain button (the photo picker).
private struct WayInLabel: View {
    let icon: String
    let title: String
    let subtitle: String?
    var body: some View {
        HStack(spacing: Space.s4) {
            IconWell(systemName: icon)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text)
                if let subtitle { Text(subtitle).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted) }
            }
            Spacer(minLength: Space.s2)
            Image(systemName: PlayIcon.open.systemName).foregroundStyle(Color.Scribe.textMuted).accessibilityHidden(true)
        }
        .padding(.horizontal, Space.s4)
        .padding(.vertical, Space.s3)
        .frame(minHeight: 60)
        .contentShape(Rectangle())
    }
}

/// What the camera row does, by what the system says of the camera for this app.
enum CameraAccess: Equatable {
    /// Allowed: the camera opens.
    case open
    /// Not asked yet: the system asks, and the camera opens if the player allows it.
    case ask
    /// Refused (by the player, or by a restriction such as Screen Time): the row says so and leads to Settings.
    case refused

    static func of(_ status: AVAuthorizationStatus) -> CameraAccess {
        switch status {
        case .authorized: .open
        case .notDetermined: .ask
        default: .refused
        }
    }

    static var refusedWords: String {
        String(localized: "The camera isn't allowed, so a photo of a page can't be taken. Allow it in Settings, or choose a picture you already have.")
    }

    #if os(iOS)
    /// This app's page in the Settings app, where the camera is allowed.
    @MainActor static func openSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
    }
    #endif
}

#if os(iOS)
/// The system camera, for one photo of a page. Its JPEG is passed on as it was taken; `Pages.photo` turns it upright.
struct CameraPicker: UIViewControllerRepresentable {
    let took: (Data) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ vc: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(took: took, dismiss: { dismiss() }) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let took: (Data) -> Void
        let dismiss: () -> Void
        init(took: @escaping (Data) -> Void, dismiss: @escaping () -> Void) { self.took = took; self.dismiss = dismiss }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage, let data = image.jpegData(compressionQuality: 0.9) { took(data) }
            dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { dismiss() }
    }
}
#endif

/// Pages being read on the computer: the step in plain words, how far it is, Stop; then what became of them.
@Observable @MainActor
final class PagesJob: Identifiable {
    let id = UUID()
    let request: TranscriptionRequest
    let service: TranscriptionService
    var progress = TranscriptionProgress(stage: .uploading, fraction: 0, etaSeconds: nil)
    var error: Error?
    var cancelled = false
    /// The computer refused this device (401), or its interface version is not this app's.
    var onRefused: (@MainActor () -> Void)?
    private var task: Task<Void, Never>?

    init(request: TranscriptionRequest, service: TranscriptionService) { self.request = request; self.service = service }

    func start(onDone: @escaping @MainActor (TranscriptionResult) async throws -> Void) {
        let service = self.service, req = request
        task = Task { [weak self] in
            do {
                for try await ev in service.transcribe(req) {
                    switch ev {
                    case .progress(let p): self?.progress = p
                    case .finished(let r): try await onDone(r)
                    }
                }
            } catch {
                guard let self else { return }
                if case TranscriptionError.notPaired = error { self.onRefused?() }
                if case TranscriptionError.interfaceMismatch = error { self.onRefused?() }
                if case TranscriptionError.cancelled = error { self.cancelled = true } else if !Task.isCancelled { self.error = error }
            }
        }
    }

    func cancel() {
        task?.cancel()
        cancelled = true
    }
}

/// Reading the pages: the computer's step, how far it is and Stop; a failure says why in the player's words, and the
/// pages stay in hand to change or send again.
struct ReadingPagesView: View {
    let job: PagesJob
    /// The app's words for an error that is not about the pages (the connection, an update).
    let otherWords: (Error) -> String
    /// What the last step makes: "Laying out the score", "Laying out the tab".
    let layingOut: String
    let tryAgain: () -> Void
    let changePages: () -> Void
    @State private var confirmStop = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                if let error = job.error {
                    Text(PagesWords.title(error) ?? String(localized: "The notes couldn't be read"))
                        .font(Font.Scribe.title2).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                    Text(PagesWords.of(error) ?? otherWords(error))
                        .font(Font.Scribe.body).foregroundStyle(Color.Scribe.text).fixedSize(horizontal: false, vertical: true)
                    Text("Your pages are still here. You can try again.").font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                    HStack(spacing: Space.s3) {
                        Button(action: tryAgain) { Label("Try again", systemImage: PlayIcon.retry.systemName) }.buttonStyle(.primary)
                        Button(action: changePages) { Text("Change the pages") }.buttonStyle(.outline)
                    }
                    DisclosureGroup {
                        Text(verbatim: error.localizedDescription).font(Font.Scribe.caption).textSelection(.enabled)
                    } label: { Text("Technical details") }
                } else if job.cancelled {
                    Text("Stopped. The pages are still here.").font(Font.Scribe.body)
                    Button(action: changePages) { Text("Change the pages") }.buttonStyle(.outline)
                } else {
                    Text(stage).font(Font.Scribe.title2).foregroundStyle(Color.Scribe.text).accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("pages-stage")
                    ProgressView(value: job.progress.fraction)
                        .tint(Color.Scribe.brand)
                        .accessibilityLabel(Text(stage))
                        .accessibilityValue(Text(percentText(job.progress.fraction * 100)))
                    SettingUpLine(active: job.progress.settingUp)
                    HelperLine(systemImage: PlayIcon.computer.systemName, text: String(localized: "Bandroom on your computer reads the pages. You can switch to another app while it does."))
                    Button(role: .destructive) { confirmStop = true } label: { Text("Stop") }
                        .buttonStyle(.outline)
                        .accessibilityIdentifier("pages-stop")
                }
            }
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text("Reading the notes"))
        .toolbar(removing: .title)
        .navigationBarBackButtonHidden(job.error == nil && !job.cancelled)
        .onChange(of: job.progress.stage) { _, _ in AccessibilityNotifier.announce(stage) }
        .confirmationDialog(Text("Stop reading the notes?"), isPresented: $confirmStop, titleVisibility: .visible) {
            Button("Stop", role: .destructive) { job.cancel() }
            Button("Keep going", role: .cancel) {}
        } message: {
            Text("The pages are kept. You can send them again.")
        }
    }

    private var stage: String {
        switch job.progress.stage {
        case .uploading: String(localized: "Sending the pages to your computer")
        case .engraving, .rendering, .arranging: layingOut
        default: String(localized: "Reading the notes on the pages")
        }
    }
}
