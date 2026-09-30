import SwiftUI
import TranscriptionKit
#if os(iOS)
import VisionKit
#endif

/// Settings › Your computer: how this device stands with its computer, and the three ways to pair
/// (choose the computer and allow it there, scan or paste the pairing link, or type the six digits).
struct YourComputerSection: View {
    @Environment(AppModel.self) private var app
    @State private var browser = EngineBrowser()
    @State private var code = ""
    @State private var linkText = ""
    @State private var message: String?
    @State private var busy = false
    @State private var approval: Approval?
    @State private var scanning = false
    @State private var confirmForget = false
    /// A pairing link opened from outside the app, waiting for the player to say yes.
    @State private var confirmLink: PairingLink?

    /// Waiting for the computer to allow this device.
    struct Approval: Equatable {
        var engineName: String
        var address: URL
        var requestID: String
        var matchCode: String
        var outcome: Outcome = .waiting
        enum Outcome: Equatable { case waiting, expired, denied }
    }

    private var paired: Bool { app.connection.record?.token != nil }
    private var showPairing: Bool {
        switch app.connection.state {
        case .needsPairing: return true
        // Brasscribe on this same Mac needs no pairing
        case .connected: return false
        default: return !paired
        }
    }

    var body: some View {
        @Bindable var app = app
        Section {
            ConnectionStatusRow()
            if let approval { approvalView(approval) }
            if showPairing && approval == nil { pairingWays }
            if let message {
                Text(message).font(Font.Brasscribe.callout).accessibilityIdentifier("pairingMessage")
            }
            if app.connection.record?.token != nil {
                Button(role: .destructive) { confirmForget = true } label: { Text("Forget this computer") }
                    .disabled(busy)
            }
            DisclosureGroup {
                Text("Without Brasscribe Bandroom, start the engine with “brasscribe serve --lan”.")
                    .font(Font.Brasscribe.callout)
                ConnectionDetails()
                if showPairing && approval == nil { linkField }
                if let problem = browser.problem {
                    Text(problem).font(Font.Brasscribe.caption).foregroundStyle(Color.Brasscribe.textMuted)
                }
                TextField(text: $app.companionURL) { Text("Address") }
                    .textContentType(.URL)
                    .autocorrectionDisabled()
            } label: { Text("Details for the band's tech person") }
        } header: { Text("Your computer") } footer: {
            if showPairing { Text("Do this once. This device stays paired, also when the computer restarts or gets a new address.") }
        }
        .onAppear { if showPairing { browser.start() } }
        .onDisappear { browser.stop() }
        .onChange(of: showPairing) { _, show in if show { browser.start() } else { browser.stop() } }
        .task(id: app.pendingLink) {
            // a link from outside the app (the camera, another app, a web page) pairs only when the player says so
            guard let link = app.pendingLink else { return }
            app.pendingLink = nil
            confirmLink = link
        }
        .alert(Text(confirmLink.map(confirmTitle) ?? ""),
               isPresented: Binding(get: { confirmLink != nil }, set: { if !$0 { confirmLink = nil } }),
               presenting: confirmLink) { link in
            Button("Pair") { Task { await pair(link) } }
            Button("Cancel", role: .cancel) {}
        } message: { link in
            Text(confirmMessage(link))
        }
        .confirmationDialog(Text("Forget this computer?"), isPresented: $confirmForget) {
            Button("Forget", role: .destructive) { Task { await forget() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Scores already on this device stay. To use the computer again, pair once more.")
        }
        #if os(iOS)
        .sheet(isPresented: $scanning) {
            QRScannerSheet { text in
                scanning = false
                if let link = PairingLink(string: text) { Task { await pair(link) } }
                else { message = String(localized: "That code isn't a Brasscribe pairing code.") }
            }
        }
        #endif
    }

    // MARK: ways to pair

    @ViewBuilder private var pairingWays: some View {
        Text("On your computer, click the Brasscribe mark in the menu bar (Mac) or the taskbar corner (Windows), and choose Pair a phone.")
            .font(Font.Brasscribe.body).fixedSize(horizontal: false, vertical: true)
        // 1. choose the computer here, then allow it there (no code)
        ForEach(browser.engines) { engine in
            Button { Task { await ask(engine) } } label: {
                Label(ConnectionCopy.named(computer: engine.computerName), systemImage: BrasscribeIcon.computer.systemName)
            }
            .disabled(busy)
            .accessibilityHint(Text("Asks the computer to allow this device."))
        }
        if browser.engines.isEmpty {
            Text("Looking for Brasscribe on your network…").foregroundStyle(Color.Brasscribe.textMuted)
        }
        // 2. scan the QR code (the camera app also opens its link here)
        #if os(iOS)
        if QRScannerSheet.available {
            Button { scanning = true } label: { Label("Scan the code", systemImage: "qrcode.viewfinder") }
                .disabled(busy)
                .accessibilityIdentifier("scanCode")
        }
        #endif
        // 3. the six digits
        HStack {
            TextField(text: $code) { Text("Six-digit code") }
                .textContentType(.oneTimeCode)
                #if os(iOS)
                .keyboardType(.numberPad)
                #endif
                .accessibilityIdentifier("pairingCode")
            Button("Pair") { Task { await pair(code: code.filter(\.isNumber)) } }
                .disabled(code.filter(\.isNumber).count != 6 || busy)
        }
    }

    /// The pairing link pasted by hand, for the tech person (behind the disclosure).
    private var linkField: some View {
        HStack {
            TextField(text: $linkText) { Text("Pairing link") }
                .autocorrectionDisabled()
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
                .accessibilityIdentifier("pairingLink")
            Button("Use link") {
                if let link = PairingLink(string: linkText) { Task { await pair(link) } }
                else { message = String(localized: "That isn't a Brasscribe pairing link. It starts with brasscribe://pair.") }
            }
            .disabled(linkText.isEmpty || busy)
        }
    }

    @ViewBuilder private func approvalView(_ a: Approval) -> some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            switch a.outcome {
            case .waiting:
                Text("On \(ConnectionCopy.named(computer: a.engineName)), choose Allow. Check that it shows the same number:")
                    .font(Font.Brasscribe.body).fixedSize(horizontal: false, vertical: true)
                MatchCodeView(code: a.matchCode)
                HStack(spacing: Space.s2) {
                    ProgressView().controlSize(.small)
                    Text("Waiting for your computer …").font(Font.Brasscribe.callout).foregroundStyle(Color.Brasscribe.textMuted)
                }
                Button("Cancel") { approval = nil }.buttonStyle(.plainText)
            case .expired, .denied:
                Text(a.outcome == .expired ? "The request ran out before it was allowed on the computer."
                                           : "The computer didn't allow this device.")
                    .font(Font.Brasscribe.body).fixedSize(horizontal: false, vertical: true)
                HStack(spacing: Space.s3) {
                    Button("Ask again") { Task { await ask(at: a.address, name: a.engineName) } }
                        .buttonStyle(SecondaryButtonStyle(minHeight: 44))
                        .accessibilityIdentifier("askAgain")
                    Button("Cancel") { approval = nil }.buttonStyle(.plainText)
                }
            }
        }
        .accessibilityElement(children: .contain)
    }

    // MARK: actions

    private func ask(_ engine: EngineBrowser.Engine) async {
        busy = true; defer { busy = false }
        message = nil
        guard let url = try? await browser.resolve(engine) else {
            message = String(localized: "\(ConnectionCopy.named(computer: engine.computerName)) didn't answer. Check that it's still open.")
            return
        }
        app.companionURL = url.absoluteString
        await ask(at: url, name: engine.computerName)
    }

    /// Ask the computer to allow this device, then wait for the answer (requests last two minutes).
    private func ask(at url: URL, name: String) async {
        message = nil
        let svc = CompanionService(baseURL: url)
        do {
            let req = try await svc.requestPairing(deviceName: AppModel.deviceName, platform: AppModel.platform)
            var a = Approval(engineName: name, address: url, requestID: req.requestID, matchCode: req.matchCode)
            approval = a
            AccessibilityNotifier.announce(String(localized: "Check that your computer shows \(req.matchCode.map(String.init).joined(separator: " ")), then choose Allow there."))
            while approval?.requestID == req.requestID {
                try? await Task.sleep(for: .seconds(2))
                guard approval?.requestID == req.requestID else { return }
                switch try await svc.pollPairing(req.requestID) {
                case .pending: continue
                case .approved(let result):
                    approval = nil
                    await app.connection.adopt(result, address: url, fallbackName: "Brasscribe on \(name)")
                    paired(name: app.connection.serverName)
                    return
                case .denied:
                    a.outcome = .denied; approval = a
                    AccessibilityNotifier.announce(String(localized: "The computer didn't allow this device."))
                    return
                case .expired:
                    a.outcome = .expired; approval = a
                    AccessibilityNotifier.announce(String(localized: "The request ran out before it was allowed on the computer."))
                    return
                }
            }
        } catch {
            approval = nil
            message = String(localized: "The computer can't be reached. Check that Brasscribe on the computer says Running, and that both are on the same network.")
        }
    }

    private func pair(code: String) async {
        busy = true; defer { busy = false }
        message = nil
        let url = URL(string: app.companionURL) ?? URL(string: "http://localhost:8765")!
        do {
            let r = try await CompanionService(baseURL: url).pair(code: code, deviceName: AppModel.deviceName, platform: AppModel.platform)
            await app.connection.adopt(r, address: url)
            self.code = ""
            paired(name: app.connection.serverName)
        } catch TranscriptionError.pairingRejected {
            message = String(localized: "That code didn't work. Check the six digits on the computer, or choose the computer above and allow it there.")
        } catch {
            message = String(localized: "The computer can't be reached. Check that Brasscribe on the computer says Running, and that both are on the same network.")
        }
    }

    private func pair(_ link: PairingLink) async {
        busy = true; defer { busy = false }
        message = nil
        do {
            if let url = try await app.connection.pair(link: link, deviceName: AppModel.deviceName, platform: AppModel.platform) {
                // no code in the link: ask the computer instead
                await ask(at: url, name: EngineRecord.computerName(fromServerName: link.serverName))
            } else {
                linkText = ""
                paired(name: app.connection.serverName)
            }
        } catch TranscriptionError.pairingRejected {
            message = String(localized: "That code has been used or has run out. Show a new one on the computer, or choose the computer above and allow it there.")
        } catch {
            message = String(localized: "The computer can't be reached. Check that Brasscribe on the computer says Running, and that both are on the same network.")
        }
    }

    private func confirmTitle(_ link: PairingLink) -> String {
        String(localized: "Pair with \(ConnectionCopy.name(link.serverName)) at \(link.displayHost)?")
    }

    /// Says when the link would take the place of the computer this device is paired with.
    private func confirmMessage(_ link: PairingLink) -> String {
        if let current = app.connection.record, current.token != nil, current.serverID != link.serverID {
            return String(localized: "This device is paired with \(ConnectionCopy.name(current.serverName)). If you pair with \(ConnectionCopy.name(link.serverName)), this device uses it instead.")
        }
        return String(localized: "Only pair with a computer you know. The recordings you send go to it.")
    }

    private func paired(name: String) {
        let text = String(localized: "Paired with \(ConnectionCopy.name(name)).")
        message = text
        AccessibilityNotifier.announce(text)
        Task { await app.refreshComputerScores() }
    }

    private func forget() async {
        busy = true; defer { busy = false }
        await app.connection.forget()
        message = nil
    }
}

#if os(iOS)
/// Scans the pairing QR code with the camera (VisionKit). Not offered where the camera can't scan
/// (the simulator, or no camera permission): the pairing link can be pasted instead.
struct QRScannerSheet: View {
    let found: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    @MainActor static var available: Bool { DataScannerViewController.isSupported && DataScannerViewController.isAvailable }

    var body: some View {
        NavigationStack {
            Scanner(found: found)
                .ignoresSafeArea()
                .navigationTitle(Text("Scan the code"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
        }
    }

    struct Scanner: UIViewControllerRepresentable {
        let found: (String) -> Void

        func makeUIViewController(context: Context) -> DataScannerViewController {
            let vc = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])], qualityLevel: .balanced,
                                               isHighlightingEnabled: true)
            vc.delegate = context.coordinator
            try? vc.startScanning()
            return vc
        }

        func updateUIViewController(_ vc: DataScannerViewController, context: Context) {}

        func makeCoordinator() -> Coordinator { Coordinator(found: found) }

        final class Coordinator: NSObject, DataScannerViewControllerDelegate {
            let found: (String) -> Void
            private var done = false
            init(found: @escaping (String) -> Void) { self.found = found }

            func dataScanner(_ scanner: DataScannerViewController, didAdd items: [RecognizedItem], allItems: [RecognizedItem]) {
                for case let .barcode(code) in items {
                    guard !done, let text = code.payloadStringValue, text.lowercased().hasPrefix("brasscribe://") else { continue }
                    done = true
                    scanner.stopScanning()
                    found(text)
                }
            }
        }
    }
}
#endif
