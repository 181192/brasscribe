import SwiftUI

/// What the app ships of others' work, each with its licence and notice, and every licence's text. Reached from
/// About. The text is the app's own file from licences/dist (written by scripts/licences.py), among its resources.
struct ThirdPartyLicencesView: View {
    /// The file's name among the resources, without ".txt".
    let resource: String

    var body: some View {
        ScrollView {
            // A long text: only the paragraphs on screen are laid out.
            LazyVStack(alignment: .leading, spacing: Space.s3) {
                ForEach(Array(Self.parts(of: text).enumerated()), id: \.offset) { _, part in
                    switch part {
                    case .rule: Divider()
                    case .heading(let words):
                        Text(verbatim: words).font(Font.Scribe.body.weight(.semibold)).accessibilityAddTraits(.isHeader)
                    case .paragraph(let words):
                        Text(verbatim: words).font(Font.Scribe.callout).textSelection(.enabled)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .foregroundStyle(Color.Scribe.text)
            .padding(Space.s5)
            .readingColumn()
        }
        .pageBackground()
        .navigationTitle(Text("Third-party licences"))
    }

    private var text: String {
        Bundle.main.url(forResource: resource, withExtension: "txt").flatMap { try? String(contentsOf: $0, encoding: .utf8) } ?? ""
    }

    enum Part: Equatable {
        case rule
        case heading(String)
        case paragraph(String)
    }

    /// The file as it is shown: its first line is the screen's title and is left out, a line of "=" is a divider,
    /// and the first line after one is that part's heading.
    static func parts(of text: String) -> [Part] {
        var parts: [Part] = []
        var afterRule = false
        let paragraphs = text.components(separatedBy: "\n\n").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        for paragraph in paragraphs.dropFirst() where !paragraph.isEmpty {
            if paragraph.allSatisfy({ $0 == "=" }) {
                parts.append(.rule)
                afterRule = true
            } else if afterRule {
                let lines = paragraph.split(separator: "\n", omittingEmptySubsequences: false)
                parts.append(.heading(String(lines[0])))
                if lines.count > 1 { parts.append(.paragraph(lines.dropFirst().joined(separator: "\n"))) }
                afterRule = false
            } else {
                parts.append(paragraph == "Contents" ? .heading(paragraph) : .paragraph(paragraph))
            }
        }
        return parts
    }
}
