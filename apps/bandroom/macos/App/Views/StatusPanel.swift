import BandroomKit
import SwiftUI

/// The popover content (design/server-app.md §7), also shown as the "Brasscribe on this Mac" window.
/// Top to bottom is the reading and focus order.
struct StatusPanel: View {
    @Environment(AppModel.self) private var app
    @AccessibilityFocusState private var voiceOverOnStatus: Bool
    @FocusState private var primaryFocused: Bool
    @State private var techOpen = false
    @State private var confirm: Confirmation?

    enum Confirmation: Equatable { case stop, restart, remove }
    /// "Also delete the downloads", on by default (§3.10).
    @State var deleteDownloads = true
    @State var downloadsGB: Double?

    @FocusState private var dialogFocus: Bool

    var body: some View {
        ZStack {
            Group {
                switch app.panelPage {
                case .status: status
                case .phones: PhonesView()
                }
            }
            // While a confirmation is up, nothing behind it takes focus or reads out.
            .disabled(confirm != nil)
            .accessibilityHidden(confirm != nil)
            if let confirm {
                confirmation(confirm)
                    .onAppear { dialogFocus = true }
            }
        }
        .animation(nil, value: app.panelPage)
    }

    private var state: DisplayState { app.displayState }

    private var status: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            if let expired = app.expiredRequest { ExpiredCard(name: expired) }
            if let request = app.monitor.requests.first {
                // A phone is waiting: allowing it is the one primary until it's answered.
                AllowCard(request: request)
            }
            lead
            primaryButton
            if app.showKeyUnreadableNote { KeyUnreadableCard() }
            if app.isRunning || app.monitor.status != nil { phonesRow }
            if app.isRunning { thisComputer }
            actions
            techDetails
        }
        .padding(14)
        .onAppear {
            primaryFocused = true
            voiceOverOnStatus = true
        }
    }

    // MARK: header

    private var header: some View {
        HStack(alignment: .top, spacing: 10) {
            Mark(size: 20).padding(.top, 2)
            VStack(alignment: .leading, spacing: 4) {
                Text("Brasscribe on \(app.hostName)")
                    .brFont(.heading)
                    .foregroundStyle(Color.Scribe.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                HStack(spacing: 6) {
                    StatusIcon(state: state)
                    Text(Strings.statusWord(state)).brFont(.body).foregroundStyle(Color.Scribe.text)
                }
                .accessibilityElement(children: .combine)
                .accessibilityFocused($voiceOverOnStatus)
            }
            Spacer(minLength: 4)
            MoreMenu {
                downloadsGB = app.downloadsGB()
                deleteDownloads = true
                confirm = .remove
            }
        }
    }

    // MARK: lead: what is happening now, or why not

    @ViewBuilder private var lead: some View {
        switch state {
        case .busy:
            if let job = app.monitor.job { NowCard(job: job) }
        case .running:
            Text("Ready. Phones and tablets can send recordings.").brFont(.body).foregroundStyle(Color.Scribe.textMuted)
        case .stopped:
            Text("Phones can't send recordings until you start it.").brFont(.body).foregroundStyle(Color.Scribe.textMuted)
        case .updating:
            VStack(alignment: .leading, spacing: 6) {
                Text("Updating Brasscribe…").brFont(.bodyStrong)
                BrassProgress(fraction: Double(app.updater.percent) / 100)
                Text("Back in about a minute. Phones reconnect by themselves.").brFont(.body).foregroundStyle(Color.Scribe.textMuted)
            }
        case .starting:
            EmptyView()
        case .settingUp(let n):
            VStack(alignment: .leading, spacing: 6) {
                Text("Setting up").brFont(.bodyStrong)
                BrassProgress(fraction: Double(n) / 100)
            }
        case .attention(let p):
            ProblemCard(title: Strings.problemTitle(p), why: Strings.problemWhy(p), symbol: "exclamationmark.triangle.fill",
                        tint: Color.Scribe.warning)
            if app.isBusy, let job = app.monitor.job { NowCard(job: job) }
        case .error:
            ProblemCard(title: Strings.failureTitle(app.failure), why: Strings.failureWhy(app.failure),
                        symbol: "xmark.circle.fill", tint: Color.Scribe.error)
        }
    }

    // MARK: the one primary

    @ViewBuilder private var primaryButton: some View {
        switch state {
        case .running, .busy:
            Button { app.openWindow("pair") } label: { Label("Pair a phone", systemImage: "iphone") }
                .buttonStyle(BRButtonStyle(kind: app.monitor.requests.isEmpty ? .primary : .secondary, fullWidth: true))
                .focused($primaryFocused)
        case .stopped:
            Button { app.start() } label: { Text("Start Brasscribe") }
                .buttonStyle(.brPrimary).focused($primaryFocused)
        case .settingUp:
            Button { app.openWindow("setup") } label: { Text("Finish setting up") }
                .buttonStyle(.brPrimary).focused($primaryFocused)
        case .error:
            Button { app.tryAgain() } label: { Text("Try again") }
                .buttonStyle(.brPrimary).focused($primaryFocused)
            Button { app.copyDiagnostics() } label: { Text("Copy details for the tech person") }
                .buttonStyle(.brPlain)
        case .attention(let p):
            Button { fix(p) } label: { Text(Strings.problemFix(p)) }
                .buttonStyle(.brPrimary).focused($primaryFocused)
            if p.pixiRefusal != nil {
                Button { app.copyDiagnostics() } label: { Text("Copy details for the tech person") }
                    .buttonStyle(.brPlain)
            }
        case .starting, .updating:
            EmptyView()
        }
    }

    private func fix(_ p: Problem) {
        switch p {
        case .lowDisk: app.openStorageSettings()
        case .missingDownload: app.openWindow("setup")
        case .noFreePort: app.tryAgain()
        case .updateFailed: app.retryUpdate()
        case .notResponding: app.restartNow()
        case .pixiTooOld, .updateRefused: app.openLatestRelease()
        }
    }

    // MARK: phones

    private var phonesRow: some View {
        Button {
            app.panelPage = .phones
        } label: {
            HStack(spacing: 10) {
                Image(systemName: "iphone").font(.system(size: 17)).frame(width: 24).foregroundStyle(Color.Scribe.text)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Phones and tablets").brFont(.bodyStrong).foregroundStyle(Color.Scribe.text)
                    Text(Strings.devicesSummary(connected: app.monitor.status?.onlineDevices ?? 0,
                                                paired: app.monitor.status?.pairedDevices ?? 0))
                        .brFont(.callout).foregroundStyle(Color.Scribe.textMuted)
                }
                Spacer()
                Image(systemName: "chevron.right").foregroundStyle(Color.Scribe.textMuted)
            }
            .frame(minHeight: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .card(padding: 6)
    }

    // MARK: this computer

    private var thisComputer: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionLabel(text: "This computer").padding(.bottom, 4)
            if let host = app.host {
                HealthRow(symbol: "cpu", label: "Work load", value: Strings.load(host.workLoad), meter: host.workLoad.rawValue)
                Divider()
                HealthRow(symbol: "memorychip", label: "Memory", value: Strings.memory(host.memory), meter: host.memory.rawValue)
                Divider()
                HealthRow(symbol: "internaldrive", label: "Free space", value: String(localized: "\(host.diskFreeGB) GB free"), meter: nil)
                Divider()
            }
            HealthRow(symbol: "checkmark.circle", label: "Ready to make scores",
                      value: app.models.isReady ? String(localized: "Ready") : Strings.missingDownloads(app.models.missing.count), meter: nil)
            Text(app.monitor.health?.device == "cpu" ? String(localized: "Processor only: slower")
                 : String(localized: "Uses the graphics chip"))
                .brFont(.caption).foregroundStyle(Color.Scribe.textMuted)
                .padding(.top, 2)
        }
        .card(padding: 12)
    }

    // MARK: actions

    /// Start, Restart and Stop follow the engine's phase, so a Needs-attention note never hides them. Not while
    /// setting up or updating: those start the engine themselves.
    private var showsEngineControls: Bool {
        switch state {
        case .settingUp, .updating: false
        default: true
        }
    }

    private var actions: some View {
        VStack(alignment: .leading, spacing: 8) {
            if showsEngineControls && app.phase.offersStop {
                HStack(spacing: 8) {
                    Button { requestRestart() } label: { Label("Restart", systemImage: "arrow.clockwise") }
                        .buttonStyle(.brOutline)
                    Button { requestStop() } label: { Label("Stop", systemImage: "power") }
                        .buttonStyle(.brOutline)
                }
            } else if showsEngineControls && app.phase.offersStart && state != .stopped {
                // When Stopped is what the panel shows, Start is already the primary button.
                Button { app.start() } label: { Text("Start Brasscribe") }
                    .buttonStyle(.brOutline)
            }
            if app.isRunning {
                Button { app.openStudio() } label: { Label("Open Studio", systemImage: "arrow.up.forward.square") }
                    .buttonStyle(BRButtonStyle(kind: .plain, height: 32))
            }
        }
    }

    private func requestStop() {
        if app.isBusy { confirm = .stop } else { app.stopNow() }
    }

    private func requestRestart() {
        if app.isBusy { confirm = .restart } else { app.restartNow() }
    }

    // MARK: tech person

    private var techDetails: some View {
        Disclosure(title: "Details for the band's tech person", isExpanded: $techOpen) {
            VStack(alignment: .leading, spacing: 10) {
                Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 10, verticalSpacing: 3) {
                    techRow("Address", app.addresses.joined(separator: "\n"))
                    techRow("Port", app.supervisor.port.map(String.init) ?? "–")
                    techRow("Version", "\(Bundle.main.shortVersion) (engine \(app.monitor.status?.version ?? "–"))")
                    techRow("Engine build", app.monitor.health?.build ?? "–")
                    techRow("Workspace", app.bundledStamp?.short ?? "–")
                    techRow("Runs on", Strings.runsOn(app.monitor.health?.device))
                    techRow("Server", app.monitor.status.map { String($0.serverId.prefix(8)) + "…" } ?? "–")
                    techRow("Data folder", app.paths.data.path.replacingOccurrences(of: NSHomeDirectory(), with: "~"))
                }
                .brFont(.mono)
                .foregroundStyle(Color.Scribe.text)
                .textSelection(.enabled)
                HStack(spacing: 8) {
                    Button { app.showLogs() } label: { Text("Show logs") }.buttonStyle(.brOutline)
                    Button { app.copyDiagnostics() } label: { Text("Copy diagnostics") }.buttonStyle(.brOutline)
                }
            }
        }
    }

    private func techRow(_ label: LocalizedStringKey, _ value: String) -> some View {
        GridRow {
            Text(label).foregroundStyle(Color.Scribe.textMuted).fixedSize()
            Text(value).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: confirmations (system rule 9)

    /// Remove Brasscribe from this Mac? (§3.10): what goes, what stays; Cancel has the focus.
    @ViewBuilder private var removeDialog: some View {
        Text("Remove Brasscribe from this Mac?").brFont(.bodyStrong).multilineTextAlignment(.center)
            .accessibilityAddTraits(.isHeader)
        Text("Phones can't make full-band scores here after this. Scores on your phones stay.")
            .brFont(.callout).foregroundStyle(Color.Scribe.textMuted).multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
        if let gb = downloadsGB {
            let size = gb.formatted(.number.precision(.fractionLength(gb < 10 ? 1 : 0)))
            Toggle(isOn: $deleteDownloads) { Text("Also delete the downloads (\(size) GB)").brFont(.callout) }
                .toggleStyle(.checkbox)
                .frame(maxWidth: .infinity, alignment: .leading)
            if !deleteDownloads {
                Text("The downloads stay in \(app.paths.models.path.replacingOccurrences(of: NSHomeDirectory(), with: "~")), so installing again doesn't fetch them again.")
                    .brFont(.callout).foregroundStyle(Color.Scribe.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        Button { confirm = nil; app.removeFromThisMac(deleteDownloads: downloadsGB != nil && deleteDownloads) } label: { Text("Remove") }
            .buttonStyle(.brPrimary)
        Button { confirm = nil } label: { Text("Cancel") }.buttonStyle(.brPlain).keyboardShortcut(.cancelAction)
            .focused($dialogFocus)
    }

    @ViewBuilder private func confirmation(_ c: Confirmation) -> some View {
        let title = app.monitor.job?.title ?? String(localized: "this score")
        ZStack {
            Color.Scribe.scrim.ignoresSafeArea().onTapGesture { confirm = nil }
            VStack(spacing: 12) {
                Mark(size: 36)
                switch c {
                case .stop:
                    Text("Stop while “\(title)” is being made?").brFont(.bodyStrong).multilineTextAlignment(.center)
                    Group {
                        if let device = app.monitor.job?.deviceName {
                            Text("\(device) keeps the recording and can send it again.")
                        } else {
                            Text("The phone keeps the recording and can send it again.")
                        }
                    }
                        .brFont(.callout).foregroundStyle(Color.Scribe.textMuted).multilineTextAlignment(.center)
                    Button { confirm = nil; app.stopNow() } label: { Text("Stop now") }.buttonStyle(.brPrimary)
                    Button { confirm = nil } label: { Text("Keep going").frame(maxWidth: .infinity) }
                        .buttonStyle(BRButtonStyle(kind: .secondary, fullWidth: true))
                        .keyboardShortcut(.cancelAction)
                        .focused($dialogFocus)
                case .restart:
                    Text("Restart when “\(title)” is done?").brFont(.bodyStrong).multilineTextAlignment(.center)
                    Button { confirm = nil; app.restartWhenDone = true } label: { Text("Restart when done") }.buttonStyle(.brPrimary)
                    Button { confirm = nil; app.restartNow() } label: { Text("Restart now").frame(maxWidth: .infinity) }
                        .buttonStyle(BRButtonStyle(kind: .secondary, fullWidth: true))
                    Button { confirm = nil } label: { Text("Cancel") }.buttonStyle(.brPlain).keyboardShortcut(.cancelAction)
                        .focused($dialogFocus)
                case .remove:
                    removeDialog
                }
            }
            .padding(16)
            .background(Color.Scribe.surfaceRaised, in: RoundedRectangle(cornerRadius: ScribeDesign.Radius.lg))
            .overlay(RoundedRectangle(cornerRadius: ScribeDesign.Radius.lg).strokeBorder(Color.Scribe.border))
            .padding(24)
            .accessibilityAddTraits(.isModal)
        }
    }
}

/// Status icon: shape first, status colour on the icon only (§6.1).
struct StatusIcon: View {
    let state: DisplayState
    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(tint)
            .accessibilityHidden(true)
    }

    private var symbol: String {
        switch state {
        case .running, .busy: "checkmark.circle"
        case .attention: "exclamationmark.triangle.fill"
        case .stopped: "stop.fill"
        case .starting: "ellipsis"
        case .updating: "arrow.clockwise"
        case .error: "xmark.circle.fill"
        case .settingUp: "arrow.down.circle"
        }
    }

    private var tint: Color {
        switch state {
        case .running, .busy: Color.Scribe.success
        case .attention: Color.Scribe.warning
        case .error: Color.Scribe.error
        default: Color.Scribe.text
        }
    }
}

struct NowCard: View {
    let job: JobSummary
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionLabel(text: "Now")
            Text(Strings.step(job.step)).brFont(.heading).foregroundStyle(Color.Scribe.text)
            if let title = job.title {
                Group {
                    if let device = job.deviceName {
                        Text("“\(title)” from \(device)")
                    } else {
                        Text("“\(title)”")
                    }
                }
                .brFont(.callout).foregroundStyle(Color.Scribe.textMuted)
            }
            BrassProgress(fraction: Double(job.percent) / 100).padding(.vertical, 4)
            HStack {
                Group {
                    if let m = job.minutesLeft {
                        Text("\(job.percent)% · about \(m) min left")
                    } else {
                        Text("\(job.percent)%")
                    }
                }
                .brFont(.callout).foregroundStyle(Color.Scribe.text)
                Spacer()
                if job.waiting > 0 {
                    Text("\(job.waiting) more waiting").brFont(.callout).foregroundStyle(Color.Scribe.textMuted)
                }
            }
        }
        .card(padding: 12)
        .accessibilityElement(children: .combine)
    }
}

struct ProblemCard: View {
    let title: String
    let why: String
    let symbol: String
    let tint: Color
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: symbol).foregroundStyle(tint).font(.system(size: 16)).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).brFont(.bodyStrong).foregroundStyle(Color.Scribe.text)
                Text(why).brFont(.callout).foregroundStyle(Color.Scribe.text).fixedSize(horizontal: false, vertical: true)
            }
        }
        .card(padding: 12)
        .accessibilityElement(children: .combine)
    }
}

struct HealthRow: View {
    let symbol: String
    let label: LocalizedStringKey
    let value: String
    let meter: Int?
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: symbol).frame(width: 20).foregroundStyle(Color.Scribe.textMuted).accessibilityHidden(true)
            Text(label).brFont(.body).foregroundStyle(Color.Scribe.text)
            Spacer()
            Text(value).brFont(.bodyStrong).foregroundStyle(Color.Scribe.text)
            if let meter { Meter(level: meter) }
        }
        .frame(minHeight: 44)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(label))
        .accessibilityValue(Text(value))
    }
}

/// "Allow Kari's iPhone?" with the match number (§3.4 way 1).
struct AllowCard: View {
    @Environment(AppModel.self) private var app
    let request: PairRequestInfo
    /// In the Pair window's sheet, the sheet is the card.
    var inSheet = false

    var body: some View {
        VStack(spacing: 8) {
            Mark(size: 28)
            Text("Allow \(request.name)?").brFont(.bodyStrong).multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
            Group {
                Text("It can send recordings to this computer and get scores back. You can remove it any time.")
                    .brFont(.callout).foregroundStyle(Color.Scribe.textMuted).multilineTextAlignment(.center)
                Text("The phone shows the number:").brFont(.callout)
                Text(request.matchCode)
                    .brFont(.matchCode)
                    .accessibilityLabel(Text(request.matchCode.map(String.init).joined(separator: " ")))
                Button { decide(true) } label: { Text("Allow") }.buttonStyle(.brPrimary)
                Button { decide(false) } label: { Text("Don't allow").frame(maxWidth: .infinity) }
                    .buttonStyle(BRButtonStyle(kind: .secondary, fullWidth: true))
            }
        }
        .foregroundStyle(Color.Scribe.text)
        .modifier(CardIf(on: !inSheet))
    }

    private func decide(_ approve: Bool) {
        Task { await app.decide(request, approve: approve) }
    }
}

private struct CardIf: ViewModifier {
    let on: Bool
    func body(content: Content) -> some View {
        if on { content.card(padding: 14) } else { content.padding(16) }
    }
}

/// "This request has expired. Choose this computer on the phone again." [OK]
/// The Keychain didn't hand over the saved key (Deny after an update), or its prompt went unanswered. Brasscribe runs without it; this says so
/// without taking the primary or the status, and offers the two ways back.
struct KeyUnreadableCard: View {
    @Environment(AppModel.self) private var app
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "key").font(.system(size: 16)).foregroundStyle(Color.Scribe.textMuted)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Brasscribe couldn't read your Hugging Face key").brFont(.bodyStrong)
                    Group {
                        if app.keyPromptUnanswered {
                            Text("Your Mac is still waiting for an answer to its Keychain prompt, so Brasscribe runs without the key for now. Full-band scores may need it.")
                        } else {
                            Text("Your Keychain didn't allow it, so Brasscribe runs without the key for now. Full-band scores may need it.")
                        }
                    }
                    .brFont(.callout).fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .combine)
            HStack(spacing: 8) {
                Button { app.readSavedKey() } label: { Text("Try again") }.buttonStyle(.brOutline)
                    .disabled(app.savedKey.state == .reading)
                Button { app.enterKeyAgain() } label: { Text("Enter the key again") }.buttonStyle(.brOutline)
            }
        }
        .foregroundStyle(Color.Scribe.text)
        .card(padding: 12)
    }
}

struct ExpiredCard: View {
    @Environment(AppModel.self) private var app
    let name: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Allow \(name)?").brFont(.bodyStrong)
            Text("This request has expired. Choose this computer on the phone again.").brFont(.callout)
            Button { app.expiredRequest = nil } label: { Text("OK") }.buttonStyle(.brOutline)
        }
        .foregroundStyle(Color.Scribe.text)
        .card(padding: 12)
    }
}

struct MoreMenu: View {
    @Environment(AppModel.self) private var app
    @Environment(\.openSettings) private var openSettings
    /// Asks before removing: the confirmation lives in the panel.
    var onRemove: () -> Void

    var body: some View {
        Menu {
            Button("Open Studio") { app.openStudio() }.disabled(!app.isRunning)
            Button("Settings…") { NSApp.activate(); openSettings() }
            Toggle("Start when I log in", isOn: Binding(get: { app.loginItemEnabled }, set: { app.setLoginItem($0) }))
            Button("About Brasscribe Bandroom") {
                NSApp.activate()
                NSApp.orderFrontStandardAboutPanel(nil)
            }
            Divider()
            Button("Remove Brasscribe from this Mac…") { onRemove() }
            Button("Quit Brasscribe Bandroom") { NSApp.terminate(nil) }
        } label: {
            Image(systemName: "ellipsis").font(.system(size: 15, weight: .bold)).frame(width: 28, height: 28)
                .contentShape(Rectangle())
        }
        // A button-style menu takes its label's 28 × 28 pt (WCAG 2.5.8); a borderless one shrank to its symbol (about 25 × 14).
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .accessibilityLabel(Text("More"))
        .help(Text("More"))
    }
}
