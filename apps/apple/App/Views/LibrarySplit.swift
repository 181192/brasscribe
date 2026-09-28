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
                .navigationSplitViewColumnWidth(min: 240, ideal: BrasscribeDesign.Size.sidebarWidth, max: 340)
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
    /// A Mac sheet's size: its content's, within `minWidth`…`maxWidth` and at most 90 % of the
    /// screen's height (the content scrolls inside past that).
    func sheetSize(minWidth: CGFloat, idealWidth: CGFloat? = nil, maxWidth: CGFloat, minHeight: CGFloat = 0) -> some View {
        frame(minWidth: minWidth, idealWidth: idealWidth, maxWidth: maxWidth, minHeight: minHeight, maxHeight: SheetSize.maxHeight)
    }
}

enum SheetSize {
    /// 90 % of the main screen's visible height.
    @MainActor static var maxHeight: CGFloat {
        ((NSScreen.main?.visibleFrame.height ?? 900) * WindowFit.sheetHeightShare).rounded(.down)
    }
}
#endif
