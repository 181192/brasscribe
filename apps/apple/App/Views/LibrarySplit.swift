import SwiftUI

/// iPad and Mac: the library in a sidebar next to the screen. On the Mac the window keeps one
/// minimum (`WindowFit.minimumWindow`), and the sidebar steps aside below
/// `WindowFit.sidebarCollapseWidth` so the screen keeps its width; the sidebar button brings it
/// back. The music stand has the whole window.
struct LibrarySplit<Detail: View>: View {
    @Environment(AppModel.self) private var app
    @Binding var columns: NavigationSplitViewVisibility
    @ViewBuilder var detail: Detail

    var body: some View {
        NavigationSplitView(columnVisibility: $columns) {
            LibrarySidebar()
                .navigationSplitViewColumnWidth(min: 240, ideal: ScribeDesign.Size.sidebarWidth, max: 340)
        } detail: {
            detail
        }
        .navigationSplitViewStyle(.balanced)
        #if os(macOS)
        .frame(minWidth: WindowFit.minimumContent.width, minHeight: WindowFit.minimumContent.height)
        // only when the width crosses the line, so a sidebar the user opened or closed stays that way
        .onGeometryChange(for: Bool.self) { $0.size.width < WindowFit.sidebarCollapseWidth } action: { narrow in
            guard !app.standOpen else { return }
            columns = narrow ? .detailOnly : .all
        }
        .onChange(of: app.standOpen) { _, open in columns = open ? .detailOnly : .all }
        #endif
    }
}

#if os(macOS)
extension View {
    /// A Mac sheet's size: its content's, within `minWidth`…`maxWidth`, and no taller than the room
    /// between the sheet's top and the bottom of the visible frame (above the Dock), nor 90 % of the
    /// screen's height (the content scrolls inside past that).
    func sheetSize(minWidth: CGFloat, idealWidth: CGFloat? = nil, maxWidth: CGFloat, minHeight: CGFloat = 0) -> some View {
        modifier(SheetSizing(minWidth: minWidth, idealWidth: idealWidth, maxWidth: maxWidth, minHeight: minHeight))
    }
}

struct SheetSizing: ViewModifier {
    let minWidth: CGFloat
    let idealWidth: CGFloat?
    let maxWidth: CGFloat
    let minHeight: CGFloat
    /// 90 % of the screen's visible height until the sheet is on screen, then the room below its top
    @State private var cap = SheetSize.maxHeight

    func body(content: Content) -> some View {
        content
            .frame(minWidth: minWidth, idealWidth: idealWidth, maxWidth: maxWidth, minHeight: min(minHeight, cap), maxHeight: cap)
            .background(SheetWindowReader { cap = $0 })
    }
}

enum SheetSize {
    /// 90 % of the main screen's visible height.
    @MainActor static var maxHeight: CGFloat {
        ((NSScreen.main?.visibleFrame.height ?? 900) * WindowFit.sheetHeightShare).rounded(.down)
    }

    /// Room for a sheet whose top edge is at `top` (AppKit screen coordinates, y up): down to the
    /// visible frame's bottom, above the Dock, and at most 90 % of its height.
    static func maxHeight(top: CGFloat, visible v: CGRect) -> CGFloat {
        let share = (v.height * WindowFit.sheetHeightShare).rounded(.down)
        return max(0, min(share, (top - v.minY).rounded(.down)))
    }
}

/// Reports the room below the sheet's top edge on its screen, when the sheet's window appears and
/// when its window (or the window it hangs from) moves or changes size.
private struct SheetWindowReader: NSViewRepresentable {
    let report: (CGFloat) -> Void

    func makeNSView(context: Context) -> ReaderView { ReaderView(report: report) }
    func updateNSView(_ v: ReaderView, context: Context) { v.report = report }

    final class ReaderView: NSView {
        var report: (CGFloat) -> Void
        private var observers: [NSObjectProtocol] = []
        init(report: @escaping (CGFloat) -> Void) { self.report = report; super.init(frame: .zero) }
        required init?(coder: NSCoder) { fatalError() }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            observers.forEach(NotificationCenter.default.removeObserver)
            observers = []
            guard let w = window else { return }
            for target in [w, w.sheetParent].compactMap({ $0 }) {
                for name in [NSWindow.didMoveNotification, NSWindow.didResizeNotification, NSWindow.didChangeScreenNotification] {
                    observers.append(NotificationCenter.default.addObserver(forName: name, object: target, queue: .main) { [weak self] _ in
                        MainActor.assumeIsolated { self?.measure() }
                    })
                }
            }
            DispatchQueue.main.async { [weak self] in self?.measure() }
        }

        private func measure() {
            // only a sheet: an ordinary window (the layout tests' off-screen one) keeps the 90 % cap
            guard let w = window, w.sheetParent != nil, let screen = w.screen ?? w.sheetParent?.screen else { return }
            let room = SheetSize.maxHeight(top: w.frame.maxY, visible: screen.visibleFrame)
            if room > 100 { report(room) }
        }

    }
}
#endif
