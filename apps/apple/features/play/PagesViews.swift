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
/// as it was, or another picture as an upright JPEG.
@Observable @MainActor
final class PageList {
    struct Page: Identifiable, Hashable {
        let id = UUID()
        let url: URL
        /// The file's name, as the player chose it ("IMG_2031.HEIC"), or "Sheet music" for a photo.
        let name: String
        var isPDF: Bool { url.pathExtension == "pdf" }
    }

    private(set) var pages: [Page] = []
    /// What happened to the last pages added or moved, said under the list (and to a screen reader).
    var status: String?
    private let folder = FileManager.default.temporaryDirectory.appending(path: "Pages", directoryHint: .isDirectory)

    /// Files chosen or shared, in their order. A file that is no page, or too large, is left out and said; past
    /// `Pages.maxPages` the rest are left out.
    func add(_ urls: [URL]) {
        var notPages = 0, tooLarge = 0, over = 0
        for url in urls {
            guard pages.count < Pages.maxPages else { over += 1; continue }
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            do {
                pages.append(Page(url: try Pages.prepare(url, into: folder), name: url.lastPathComponent))
            } catch Pages.Refusal.tooLarge {
                tooLarge += 1
            } catch {
                notPages += 1
            }
        }
        status = PagesWords.added(notPages: notPages, tooLarge: tooLarge, over: over)
        if let status { AccessibilityNotifier.announce(status) }
    }

    /// A photo taken here or picked from the photo library.
    func add(photo data: Data) {
        guard pages.count < Pages.maxPages else { status = PagesWords.added(notPages: 0, tooLarge: 0, over: 1); return }
        do {
            pages.append(Page(url: try Pages.photo(data, into: folder), name: String(localized: "Sheet music")))
            status = nil
        } catch {
            status = PagesWords.added(notPages: 1, tooLarge: 0, over: 0)
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

    /// What was left out of the pages just added, or nil when nothing was.
    static func added(notPages: Int, tooLarge: Int, over: Int) -> String? {
        var said: [String] = []
        if notPages == 1 { said.append(String(localized: "One file is not a picture or a PDF, so it was left out.")) }
        if notPages > 1 { said.append(String(localized: "\(notPages) files are not pictures or PDFs, so they were left out.")) }
        if tooLarge > 0 { said.append(words(Pages.Refused.pageTooLarge)) }
        if over > 0 { said.append(String(localized: "At most 40 pages can be read at once. The rest were left out.")) }
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
    let onRead: () -> Void

    @State private var choosingFiles = false
    @State private var photos: [PhotosPickerItem] = []
    @State private var takingPhoto = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.s5) {
                Text("Sheet music from a picture").font(Font.Scribe.display).foregroundStyle(Color.Scribe.text)
                    .accessibilityAddTraits(.isHeader)
                Text(lead).font(Font.Scribe.body).foregroundStyle(Color.Scribe.textMuted).fixedSize(horizontal: false, vertical: true)
                adding
                if !list.pages.isEmpty { pageRows }
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
            if case .success(let urls) = result { list.add(urls) }
        }
        .onChange(of: photos) { _, picked in
            guard !picked.isEmpty else { return }
            Task {
                // in the order they were picked
                for item in picked { if let data = try? await item.loadTransferable(type: Data.self) { list.add(photo: data) } }
                photos = []
            }
        }
        #if os(iOS)
        .fullScreenCover(isPresented: $takingPhoto) {
            CameraPicker { data in list.add(photo: data) }.ignoresSafeArea()
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
                .disabled(list.pages.isEmpty || !computerThere)
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
            PhotosPicker(selection: $photos, maxSelectionCount: max(1, Pages.maxPages - list.pages.count), selectionBehavior: .ordered,
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
                         subtitle: first ? String(localized: "Straight on, in good light, with the whole page in the picture") : nil) { takingPhoto = true }
                    .accessibilityIdentifier("pages-camera")
            }
            #endif
        }
        .card(padding: 0)
        .disabled(list.pages.count >= Pages.maxPages)
    }

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

/// One page: a small picture of it, its place and name, and the buttons that move it or take it out. The whole row is
/// one element for a screen reader, with its moves as actions; the buttons are there for touch and the keyboard.
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
                Text(page.name).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted).lineLimit(2)
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
