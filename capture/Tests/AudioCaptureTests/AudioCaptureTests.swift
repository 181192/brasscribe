import AudioCapture
import Foundation
import Testing

@Test func defaultOutputDeviceHasUID() throws {
    let uid = try ProcessTapRecorder.defaultOutputDeviceUID()
    #expect(!uid.isEmpty)
}

@Test func audioAppListIsDeduplicated() {
    let apps = ProcessTapRecorder.audioApps()
    #expect(Set(apps.map(\.bundleID)).count == apps.count)
}

@Test func stopWithoutStartThrows() {
    let r = ProcessTapRecorder(source: .system, outputURL: FileManager.default.temporaryDirectory.appending(path: "x.wav"))
    #expect(throws: CaptureError.self) { try r.stop() }
}
