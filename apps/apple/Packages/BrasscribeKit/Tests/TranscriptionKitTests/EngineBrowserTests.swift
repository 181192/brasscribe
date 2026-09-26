import Foundation
import Network
import Testing
@testable import TranscriptionKit

@Test func engineURLFromResolvedEndpoint() {
    #expect(EngineBrowser.url(host: .ipv4(IPv4Address("192.168.10.95")!), port: 8765)?.absoluteString == "http://192.168.10.95:8765")
    #expect(EngineBrowser.url(host: .name("studio.local", nil), port: 8765)?.absoluteString == "http://studio.local:8765")
    #expect(EngineBrowser.url(host: .ipv6(IPv6Address("fe80::1%lo0")!), port: 8765)?.absoluteString == "http://[fe80::1]:8765")
}
