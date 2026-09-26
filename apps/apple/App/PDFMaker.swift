import CoreGraphics
import CoreText
import Foundation
import NotationKit
import ScoreKit

/// Printed parts and scores, engraved on this device with Verovio: A4 pages, the title and
/// part name on the first page, and the "?" legend in the footer of every page.
enum PDFMaker {
    static let page = CGSize(width: 595, height: 842)   // A4 in points

    enum Failure: Error { case engraving }

    /// - Parameters:
    ///   - parts: part ids to include (nil = the conductor's score)
    ///   - marks: keep the "?" marks and note colours, with the legend in the footer
    static func pdf(musicXML: String, parts: Set<String>?, title: String, subtitle: String?, marks: Bool) throws -> Data {
        let xml = PartNames.localized(marks ? musicXML : ScoreRenderer.removingUncertainty(musicXML))
        guard let r = ScoreRenderer(musicXML: xml, keepQuestionMarks: marks) else { throw Failure.engraving }
        let top: CGFloat = 36, header: CGFloat = 56, footer: CGFloat = 40
        let zoom: CGFloat = parts?.count == 1 ? 0.9 : 0.6
        guard r.apply(ScoreRenderer.Layout(width: page.width, zoom: zoom, parts: parts, pitch: .written,
                                           height: page.height - top - header - footer)) else { throw Failure.engraving }
        let pages = r.renderAllPages()
        let out = NSMutableData()
        var box = CGRect(origin: .zero, size: page)
        guard let consumer = CGDataConsumer(data: out as CFMutableData),
              let ctx = CGContext(consumer: consumer, mediaBox: &box, [kCGPDFContextTitle as String: title] as CFDictionary) else {
            throw Failure.engraving
        }
        let ink = CGColor(gray: 0, alpha: 1)
        for (i, p) in pages.enumerated() {
            ctx.beginPDFPage(nil)
            ctx.saveGState()
            ctx.translateBy(x: 0, y: page.height)
            ctx.scaleBy(x: 1, y: -1)
            var y = top
            if i == 0 {
                if let subtitle { text(subtitle.uppercased(), size: 9, bold: true, at: CGPoint(x: page.width / 2, y: y + 10), in: ctx) }
                text(title, size: 22, bold: false, serif: true, at: CGPoint(x: page.width / 2, y: y + 36), in: ctx)
                y += header
            } else {
                y += 12
            }
            ctx.saveGState()
            let scale = min(1, page.width / max(1, p.svg.size.width))
            ctx.translateBy(x: (page.width - p.svg.size.width * scale) / 2, y: y)
            ctx.scaleBy(x: scale, y: scale)
            p.svg.draw(in: ctx, ink: ink, keepDocumentColors: marks)
            ctx.restoreGState()
            let foot = marks ? String(localized: "? = Brasscribe wasn't sure. Boxed ? = very unsure. · Page \(i + 1) of \(pages.count)")
                             : String(localized: "Written down by Brasscribe · Page \(i + 1) of \(pages.count)")
            text(foot, size: 8, bold: false, at: CGPoint(x: page.width / 2, y: page.height - footer / 2), in: ctx)
            ctx.restoreGState()
            ctx.endPDFPage()
        }
        ctx.closePDF()
        return out as Data
    }

    /// Centred text in a y-down context.
    private static func text(_ s: String, size: CGFloat, bold: Bool, serif: Bool = false, at p: CGPoint, in ctx: CGContext) {
        let name = serif ? "InstrumentSerif-Regular" : (bold ? "Helvetica-Bold" : "Helvetica")
        let font = CTFontCreateWithName(name as CFString, size, nil)
        let attrs = [kCTFontAttributeName as NSAttributedString.Key: font,
                     kCTForegroundColorAttributeName as NSAttributedString.Key: CGColor(gray: 0.1, alpha: 1)] as [NSAttributedString.Key: Any]
        let line = CTLineCreateWithAttributedString(NSAttributedString(string: s, attributes: attrs))
        let w = CTLineGetTypographicBounds(line, nil, nil, nil)
        ctx.saveGState()
        ctx.textMatrix = CGAffineTransform(scaleX: 1, y: -1)
        ctx.textPosition = CGPoint(x: p.x - w / 2, y: p.y)
        CTLineDraw(line, ctx)
        ctx.restoreGState()
    }
}
