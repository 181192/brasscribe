import SwiftUI

/// A band above or below the score that takes its own height up to `share` of the screen's height,
/// and scrolls inside that when it needs more (large text, a phone on its side), so the music keeps
/// the rest.
struct HeightShare: ViewModifier {
    let share: CGFloat
    let height: CGFloat
    @State private var natural: CGFloat = 0

    func body(content: Content) -> some View {
        if height > 0 {
            ScrollView(.vertical) {
                content.onGeometryChange(for: CGFloat.self) { $0.size.height } action: { natural = $0 }
            }
            .scrollBounceBehavior(.basedOnSize)
            .frame(height: natural > 0 ? min(natural, height * share) : nil)
        } else {
            content
        }
    }
}

extension View {
    func heightShare(_ share: CGFloat, of height: CGFloat) -> some View { modifier(HeightShare(share: share, height: height)) }
}
