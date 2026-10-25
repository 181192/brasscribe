import SwiftUI
import TranscriptionKit

/// The app's one stack: Home, then where a recording goes (What is this?, writing down the notes, Check the song) and
/// the tab. Settings, the first run and the recorders are sheets over it.
struct RootView: View {
    @Environment(FretscribeModel.self) private var model

    var body: some View {
        @Bindable var model = model
        NavigationStack(path: $model.path) {
            HomeView()
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .whatIsThis(let src): WhatIsThisView(source: src)
                    case .transcribing(let id): TranscribingView(jobID: id)
                    case .check(let song): CheckTheSongView(song: song)
                    case .tab(let song): TabScreen(song: song)
                    case .problem(let p): ProblemView(problem: p)
                    }
                }
        }
        .tint(Color.Scribe.primary)
        .sheet(isPresented: $model.showSettings) { SettingsView() }
        .sheet(isPresented: $model.showRecorder) { MicRecordView() }
        #if os(macOS)
        .sheet(isPresented: $model.showCapture) { CaptureView() }
        #endif
        .sheet(isPresented: Binding(get: { !model.firstRunDone }, set: { if !$0 { model.firstRunDone = true } })) { FirstRunView() }
        .modifier(ConnectionLifecycle(staged: nil))
    }
}
