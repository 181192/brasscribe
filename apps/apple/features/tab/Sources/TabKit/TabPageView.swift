import SwiftUI
import WebKit

/// The tab page in a SwiftUI screen, as high as its engraving: put it in a scroll view. The page itself is hidden
/// from VoiceOver; give the screen's own elements (the bars, the marks, the tab as text) over or beside it.
public struct TabPageView: View {
    private let page: TabPage

    public init(page: TabPage) {
        self.page = page
    }

    public var body: some View {
        Host(page: page)
            .frame(height: max(page.engraving?.height ?? 0, 1))
            .accessibilityHidden(true)
    }

    #if os(macOS)
    private struct Host: NSViewRepresentable {
        let page: TabPage
        func makeNSView(context: Context) -> WKWebView { page.webView }
        func updateNSView(_ view: WKWebView, context: Context) {}
    }
    #else
    private struct Host: UIViewRepresentable {
        let page: TabPage
        func makeUIView(context: Context) -> WKWebView { page.webView }
        func updateUIView(_ view: WKWebView, context: Context) {}
    }
    #endif
}
