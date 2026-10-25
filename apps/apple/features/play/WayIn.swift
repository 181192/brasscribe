import SwiftUI

/// A list row that leads somewhere: icon well, title, subtitle, chevron. At least 60 pt tall.
struct WayInRow: View {
    let icon: String
    let title: String
    var subtitle: String?
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: Space.s4) {
                IconWell(systemName: icon)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text)
                    if let subtitle { Text(subtitle).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted) }
                }
                Spacer(minLength: Space.s2)
                Image(systemName: PlayIcon.open.systemName).foregroundStyle(Color.Scribe.textMuted).accessibilityHidden(true)
            }
            .padding(.horizontal, Space.s4)
            .padding(.vertical, Space.s3)
            .frame(minHeight: 60)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// The desktop version of a way in: a card with an icon well, title and subtitle.
struct WayInCard: View {
    let icon: String
    let title: String
    let subtitle: String
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: Space.s3) {
                IconWell(systemName: icon)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Font.Scribe.headline).foregroundStyle(Color.Scribe.text)
                    Text(subtitle).font(Font.Scribe.callout).foregroundStyle(Color.Scribe.textMuted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .card()
            .contentShape(RoundedRectangle(cornerRadius: Radius.lg))
        }
        .buttonStyle(.plain)
    }
}
