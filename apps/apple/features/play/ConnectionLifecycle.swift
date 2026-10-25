import Network
import SwiftUI
import TranscriptionKit

/// Keeps the heartbeat to the computer running while the app is in front, and checks at once when the
/// network changes.
struct ConnectionLifecycle: ViewModifier {
    /// A connection state shown instead of the real one (screenshots, the screen catalogue's launches); nil for the real one.
    var staged: ConnectionState?
    @Environment(\.playHost) private var host
    private var app: any PlayHost { host! }
    @Environment(\.scenePhase) private var phase
    @State private var path = NetworkPathWatcher()

    func body(content: Content) -> some View {
        content
            .announcesConnectionChanges(app.connection)
            .onChange(of: phase, initial: true) { _, p in
                if let staged {
                    guard !app.connection.staged else { return }
                    let record = staged == .offline ? nil
                        : EngineRecord(serverID: "7f3a9c2e", serverName: ConnectionLifecycle.stagedServerName, deviceID: "d-41b2", token: "staged",
                                       lastAddress: "http://192.0.2.20:8765", lastOK: Date().addingTimeInterval(-12))
                    app.connection.stage(staged, record: record)
                    return
                }
                switch p {
                case .active: app.connection.resume()
                case .background: app.connection.suspend()
                default: break
                }
            }
            .onChange(of: path.generation) { _, _ in app.connection.poke() }
            // the computer's scores follow the connection: fetched when it is there, gone when it is not
            .onChange(of: app.connection.state) { _, _ in Task { await app.connectionChanged() } }
            .task { path.start() }
    }

    /// The computer a staged connection shows: as the engine names itself.
    static let stagedServerName = "Brasscribe on Studio Mac"
}

/// Counts network path changes (Wi-Fi joined, lost, switched).
@MainActor @Observable
final class NetworkPathWatcher {
    private(set) var generation = 0
    @ObservationIgnored private var monitor: NWPathMonitor?
    @ObservationIgnored private var updates = 0

    func start() {
        guard monitor == nil else { return }
        let m = NWPathMonitor()
        m.pathUpdateHandler = { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                // the first update only reports the current path
                self.updates += 1
                if self.updates > 1 { self.generation += 1 }
            }
        }
        m.start(queue: .main)
        monitor = m
    }
}
