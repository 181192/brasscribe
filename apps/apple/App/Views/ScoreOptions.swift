import SwiftUI

/// The options every score row offers (Home and the sidebar): the design system's "more" icon.
struct ScoreOptionsMenu: View {
    @Environment(AppModel.self) private var app
    let entry: ScoreEntry

    var body: some View {
        Menu {
            ScoreOptionItems(entry: entry)
        } label: {
            Image(systemName: BrasscribeIcon.more.systemName)
                .foregroundStyle(Color.Brasscribe.textMuted)
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Rectangle())
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .fixedSize()
        .accessibilityLabel(Text("Options for \(entry.title)"))
        .help(Text("Options for \(entry.title)"))
        .accessibilityIdentifier("options-\(entry.title)")
    }
}

/// The same items as a context menu, so right-click and long-press match the visible button.
struct ScoreOptionItems: View {
    @Environment(AppModel.self) private var app
    let entry: ScoreEntry

    var body: some View {
        Button { app.openOnStand = entry.id; app.open(entry) } label: {
            Label("Open on the music stand", systemImage: "arrow.up.left.and.arrow.down.right")
        }
        Button { app.renameTarget = entry } label: { Label("Edit title", systemImage: "pencil") }
        Button { app.open(entry, review: true) } label: { Label("Check the notes", systemImage: BrasscribeIcon.nextUncertain.systemName) }
        Divider()
        Button(role: .destructive) { app.deleteTarget = entry } label: { Label("Delete", systemImage: BrasscribeIcon.delete.systemName) }
    }
}

/// One rename dialog and one delete confirmation for every place that lists scores.
struct ScoreOptionDialogs: ViewModifier {
    @Environment(AppModel.self) private var app
    @State private var titleDraft = ""

    func body(content: Content) -> some View {
        @Bindable var app = app
        content
            .alert("Edit title", isPresented: Binding(get: { app.renameTarget != nil }, set: { if !$0 { app.renameTarget = nil } })) {
                TextField("Title", text: $titleDraft)
                Button("Cancel", role: .cancel) { app.renameTarget = nil }
                Button("Save") {
                    if let target = app.renameTarget { app.rename(target, to: titleDraft) }
                    app.renameTarget = nil
                }
                .disabled(titleDraft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .onChange(of: app.renameTarget) { _, target in titleDraft = target?.title ?? "" }
            .confirmationDialog(Text("Delete \(app.deleteTarget?.title ?? "")?"),
                                isPresented: Binding(get: { app.deleteTarget != nil }, set: { if !$0 { app.deleteTarget = nil } }),
                                titleVisibility: .visible) {
                Button("Delete", role: .destructive) {
                    if let target = app.deleteTarget { app.delete(target) }
                    app.deleteTarget = nil
                }
                Button("Cancel", role: .cancel) { app.deleteTarget = nil }
            } message: {
                Text(app.deleteTarget?.piece == nil ? "The score is removed from your computer." : "The score is removed from this device.")
            }
    }
}

extension View {
    func scoreOptionDialogs() -> some View { modifier(ScoreOptionDialogs()) }

    /// Focus lands on this score row after leaving a music stand opened from it.
    func scoreRowFocus(_ id: String) -> some View { modifier(ScoreRowFocus(id: id)) }
}

struct ScoreRowFocus: ViewModifier {
    @Environment(AppModel.self) private var app
    let id: String
    @AccessibilityFocusState private var a11y: Bool
    @FocusState private var keys: Bool

    func body(content: Content) -> some View {
        content
            .accessibilityFocused($a11y)
            .focused($keys)
            .onAppear(perform: take)
            .onChange(of: app.focusScoreRow) { _, _ in take() }
    }

    private func take() {
        guard app.focusScoreRow == id else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            guard app.focusScoreRow == id else { return }
            app.focusScoreRow = nil
            a11y = true
            keys = true
        }
    }
}
