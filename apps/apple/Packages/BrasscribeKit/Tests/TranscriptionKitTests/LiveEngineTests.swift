import Foundation
import Testing
import ScoreKit
@testable import TranscriptionKit

/// Against a running engine (`brasscribe serve`), when BRASSCRIBE_ENGINE_URL is set.
/// Uses a finished job already on the engine, so no model runs.
@Suite(.serialized, .enabled(if: ProcessInfo.processInfo.environment["BRASSCRIBE_ENGINE_URL"] != nil))
struct LiveEngineTests {
    let svc = CompanionService(baseURL: URL(string: ProcessInfo.processInfo.environment["BRASSCRIBE_ENGINE_URL"] ?? "http://127.0.0.1:8765")!)

    @Test func healthProfilesAndPairing() async throws {
        let h = try await svc.health()
        #expect(h.status == "ok")
        let names = Set(try await svc.profiles().map(\.name))
        #expect(names.isSuperset(of: Set(SourceProfile.allCases.map(\.rawValue))))
        await #expect(throws: TranscriptionError.pairingRejected) { try await svc.pair(code: "000000", deviceName: "test", platform: "macos") }
    }

    /// Full upload → progress → result, when BRASSCRIBE_ENGINE_UPLOAD names an audio file
    /// (use one the engine has cached, or hold the GPU lock).
    @Test(.enabled(if: ProcessInfo.processInfo.environment["BRASSCRIBE_ENGINE_UPLOAD"] != nil))
    func uploadAndTranscribe() async throws {
        let audio = URL(fileURLWithPath: ProcessInfo.processInfo.environment["BRASSCRIBE_ENGINE_UPLOAD"]!)
        let t0 = Date()
        var progress: [TranscriptionProgress] = []
        var result: TranscriptionResult?
        for try await ev in svc.transcribe(.init(audioURL: audio, profile: .orchestraWithSoloist, title: "Mikkel")) {
            switch ev {
            case .progress(let p): progress.append(p)
            case .finished(let r): result = r
            }
        }
        let r = try #require(result)
        #expect(try MusicXMLParser.parse(r.musicXML).parts.count == 18)
        #expect(r.composition != nil)
        #expect(progress.map(\.fraction) == progress.map(\.fraction).sorted())
        print("LIVE upload \(Int(Date().timeIntervalSince(t0))) s, \(progress.count) progress events, steps \(Set(progress.map(\.stage.rawValue)).sorted()), artifacts \(r.available.map(\.rawValue).sorted())")
    }

    @Test func finishedJobStreamsAndServesArtifacts() async throws {
        var r = URLRequest(url: svc.baseURL.appending(path: "v1/jobs"))
        r.httpMethod = "GET"
        let jobs = try JSONDecoder().decode([CompanionService.Job].self, from: try await svc.send(r))
        let job = try #require(jobs.first { $0.status == "succeeded" }, "needs one finished job on the engine")
        var events: [CompanionService.Event] = []
        for try await ev in svc.events(jobID: job.id, after: -1) { events.append(ev) }
        #expect(events.last?.type == "job")
        #expect(events.last?.status == "succeeded")
        #expect(events.contains { $0.type == "stage" && $0.fraction != nil })
        let xml = try await svc.artifact(.musicXML, jobID: job.id)
        let score = try MusicXMLParser.parse(xml)
        #expect(score.parts.count > 0)
        let comp = try Composition.decode(try await svc.artifact(.composition, jobID: job.id))
        #expect(!comp.voices.isEmpty)
        let brf = try await svc.artifact(.brailleBRF, jobID: job.id)
        #expect(brf.count > 100)
        let talk = String(decoding: try await svc.artifact(.talkingScore, jobID: job.id), as: UTF8.self)
        #expect(!talk.isEmpty && !talk.hasPrefix("<"), "text format")
        print("LIVE job \(job.id): \(events.count) events, \(score.parts.count) parts, BRF \(brf.count) bytes, talking score \(talk.count) chars")
    }
}
