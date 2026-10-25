import SwiftUI
import WebKit

/// The tab page in a SwiftUI screen, as high as its engraving: put it in a scroll view. The web view is hidden from
/// VoiceOver, which reaches [bars] in its place: one element for each bar, in the product's words
/// (`TabBarReading.text`). A screen can add its own elements (the marks) over it.
public struct TabPageView: View {
    private let page: TabPage
    private let bars: [String]

    public init(page: TabPage, bars: [String] = []) {
        self.page = page
        self.bars = bars
    }

    public var body: some View {
        Host(page: page)
            .frame(height: max(page.engraving?.height ?? 0, 1))
            .accessibilityHidden(true)
            .overlay {
                if !bars.isEmpty {
                    Color.clear
                        .accessibilityElement(children: .contain)
                        .accessibilityChildren {
                            VStack { ForEach(Array(bars.enumerated()), id: \.offset) { Text($0.element) } }
                        }
                }
            }
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
