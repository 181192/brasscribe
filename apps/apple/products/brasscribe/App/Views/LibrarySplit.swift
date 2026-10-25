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
