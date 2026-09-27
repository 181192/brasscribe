import SwiftUI
import TranscriptionKit

/// Words for the connection to the computer, the same on every Play app.
enum ConnectionCopy {
    enum Device { case phone, iPad, mac }

    static var device: Device {
        #if os(macOS)
        .mac
        #else
        UIDevice.current.userInterfaceIdiom == .pad ? .iPad : .phone
        #endif
    }

    /// "Brasscribe on Studio Mac" / "Brasscribe på Studio Mac": built from the computer's name, so the
    /// English server name never ends up inside a Norwegian sentence.
    static func name(_ serverName: String) -> String { named(computer: EngineRecord.computerName(fromServerName: serverName)) }

    static func named(computer: String) -> String {
        computer.isEmpty ? String(localized: "Brasscribe on your computer") : String(localized: "Brasscribe on \(computer)")
    }

    static func status(_ s: ConnectionState) -> String {
        switch s {
        case .connected(let n): String(localized: "Connected to \(name(n))")
        case .reconnecting(let n): String(localized: "Looking for \(name(n)) …")
        case .offline:
            switch device {
            case .phone: String(localized: "Not connected. You can still make scores on this phone.")
            case .iPad: String(localized: "Not connected. You can still make scores on this iPad.")
            case .mac: String(localized: "Not connected. You can still make scores on this Mac.")
            }
        case .needsPairing:
            switch device {
            case .phone: String(localized: "The computer no longer recognises this phone.")
            case .iPad: String(localized: "The computer no longer recognises this iPad.")
            case .mac: String(localized: "The computer no longer recognises this Mac.")
            }
        }
    }

    static var pairAgain: String {
        switch device {
        case .phone: String(localized: "Pair this phone again")
        case .iPad: String(localized: "Pair this iPad again")
        case .mac: String(localized: "Pair this Mac again")
        }
    }

    static func systemImage(_ s: ConnectionState) -> String {
        switch s {
        case .connected: BrasscribeIcon.running.systemName
        case .reconnecting: BrasscribeIcon.network.systemName
        case .offline: "wifi.slash"
        case .needsPairing: BrasscribeIcon.accessKey.systemName
        }
    }
}

/// The compact connection row: an icon and words (never colour alone), plus the one way forward when
/// there is one ("Connect", "Pair this phone again"). On Home and in Settings.
struct ConnectionStatusRow: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        let state = app.connection.state
        ViewThatFits(in: .horizontal) {
            HStack(spacing: Space.s3) { status(state); Spacer(minLength: Space.s2); action(state) }
            VStack(alignment: .leading, spacing: Space.s2) { status(state); action(state) }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("connectionStatus")
    }

    private func status(_ state: ConnectionState) -> some View {
        Label {
            Text(ConnectionCopy.status(state)).fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: ConnectionCopy.systemImage(state)).accessibilityHidden(true)
        }
        .font(Font.Brasscribe.callout)
        .foregroundStyle(Color.Brasscribe.text)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(ConnectionCopy.status(state)))
        .accessibilityIdentifier("connectionStatusText")
    }

    @ViewBuilder private func action(_ state: ConnectionState) -> some View {
        switch state {
        case .offline:
            Button("Connect") {
                if app.connection.canConnect { app.connection.connect() } else { app.showSettings = true }
            }
            .buttonStyle(SecondaryButtonStyle(outline: true, minHeight: 44))
            .accessibilityIdentifier("connectionConnect")
        case .needsPairing:
            Button(ConnectionCopy.pairAgain) { app.showSettings = true }
                .buttonStyle(SecondaryButtonStyle(outline: true, minHeight: 44))
                .accessibilityIdentifier("connectionPairAgain")
        case .connected, .reconnecting:
            EmptyView()
        }
    }
}

/// Addresses, the server id and when it last answered, behind "Details for the band's tech person".
struct ConnectionDetails: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        let r = app.connection.record
        let url = r?.baseURL
        VStack(alignment: .leading, spacing: Space.s1) {
            detail("Address", url?.host() ?? "–")
            detail("Port", url?.port.map(String.init) ?? "–")
            detail("Server id", r.map { $0.serverID.isEmpty ? "–" : $0.serverID } ?? "–")
            detail("This device's id", r?.deviceID ?? "–")
            detail("Last answered", app.connection.lastSeen.map { $0.formatted(date: .abbreviated, time: .standard) } ?? "–")
        }
        .font(Font.Brasscribe.caption)
        .foregroundStyle(Color.Brasscribe.textMuted)
        .textSelection(.enabled)
    }

    private func detail(_ label: LocalizedStringKey, _ value: String) -> some View {
        LabeledContent { Text(verbatim: value).monospaced() } label: { Text(label) }
    }
}

/// The four-digit number the computer also shows, large, read digit by digit.
struct MatchCodeView: View {
    let code: String
    var body: some View {
        Text(verbatim: code)
            .font(.system(size: 44, weight: .semibold, design: .rounded).monospacedDigit())
            .tracking(8)
            .foregroundStyle(Color.Brasscribe.text)
            .frame(maxWidth: .infinity)
            .padding(.vertical, Space.s3)
            .accessibilityLabel(Text(code.map(String.init).joined(separator: " ")))
            .accessibilityIdentifier("matchCode")
    }
}

extension View {
    /// Announces connection changes politely: only when the kind of state changes, never per heartbeat,
    /// and not for the first check after launch.
    func announcesConnectionChanges(_ monitor: ConnectionMonitor) -> some View {
        onChange(of: monitor.state.kind) { _, _ in
            guard monitor.checks > 1, !monitor.staged else { return }
            AccessibilityNotifier.announce(ConnectionCopy.status(monitor.state), polite: true)
        }
    }
}
