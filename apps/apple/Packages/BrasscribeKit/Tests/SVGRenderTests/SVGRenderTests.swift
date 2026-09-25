import CoreGraphics
import Foundation
import ImageIO
import Testing
import UniformTypeIdentifiers
@testable import SVGRender

func render(_ doc: SVGDocument, scale: CGFloat = 1, highlight: [String: CGColor] = [:]) -> CGImage {
    let w = Int(doc.size.width * scale), h = Int(doc.size.height * scale)
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.setFillColor(CGColor(gray: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.translateBy(x: 0, y: CGFloat(h))
    ctx.scaleBy(x: scale, y: -scale)
    doc.draw(in: ctx, highlight: highlight)
    return ctx.makeImage()!
}

func darkFraction(_ img: CGImage, in rect: CGRect? = nil) -> Double {
    let ctx = CGContext(data: nil, width: img.width, height: img.height, bitsPerComponent: 8, bytesPerRow: img.width * 4,
                        space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.draw(img, in: CGRect(x: 0, y: 0, width: img.width, height: img.height))
    let p = ctx.data!.assumingMemoryBound(to: UInt8.self)
    let r = rect ?? CGRect(x: 0, y: 0, width: img.width, height: img.height)
    var dark = 0, total = 0
    for y in Int(r.minY)..<min(img.height, Int(r.maxY)) {
        for x in Int(r.minX)..<min(img.width, Int(r.maxX)) {
            // bitmap memory is top-down
            let i = (y * img.width + x) * 4
            if Int(p[i]) + Int(p[i + 1]) + Int(p[i + 2]) < 300 { dark += 1 }
            total += 1
        }
    }
    return total > 0 ? Double(dark) / Double(total) : 0
}

func writePNG(_ img: CGImage, _ path: String) {
    let d = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(d, img, nil)
    CGImageDestinationFinalize(d)
}

@Test func pathParserHandlesVerovioNumbers() {
    let p = PathParser.parse("M441 -245c-23 -4 -48 -6 -76 -6zM10 10h5v5H0V0l1.5.5z")
    #expect(!p.isEmpty)
    let b = PathParser.parse("M0 0 L10 0 L10 10 Z").boundingBoxOfPath
    #expect(b == CGRect(x: 0, y: 0, width: 10, height: 10))
    #expect(numbers("1.5.5-2e1,3") == [1.5, 0.5, -20, 3])
}

@Test func transformsComposeLeftToRight() {
    let t = parseTransform("translate(10, 20) scale(2, 2)")
    #expect(CGPoint(x: 1, y: 1).applying(t) == CGPoint(x: 12, y: 22))
}

@Test func simpleDocument() throws {
    let svg = """
    <svg width="100px" height="50px" xmlns:xlink="http://www.w3.org/1999/xlink">
      <defs><g id="dot"><path d="M0 0 L10 0 L10 10 L0 10 Z"/></g></defs>
      <svg class="definition-scale" viewBox="0 0 1000 500">
        <g id="m1" class="measure"><use xlink:href="#dot" transform="translate(100, 100) scale(10, 10)"/></g>
        <g id="m2" class="measure" fill="#FF0000"><rect x="500" y="100" width="100" height="100"/></g>
      </svg>
    </svg>
    """
    let doc = try SVGDocument(svg: svg)
    #expect(doc.size == CGSize(width: 100, height: 50))
    #expect(doc.ids(ofClass: "measure") == ["m1", "m2"])
    let f = try #require(doc.frames["m1"])
    #expect(abs(f.minX - 10) < 0.01 && abs(f.width - 10) < 0.01)
    let img = render(doc)
    #expect(darkFraction(img, in: CGRect(x: 10, y: 10, width: 10, height: 10)) > 0.9)
}

/// Page 1 of the Mikkel full score as Verovio 6.3 renders it.
@Test func verovioPage() throws {
    let url = try #require(Bundle.module.url(forResource: "Resources/verovio-page", withExtension: "svg"))
    let t0 = Date()
    let doc = try SVGDocument(data: Data(contentsOf: url))
    let parse = Date().timeIntervalSince(t0)
    #expect(doc.ids(ofClass: "measure").count == 3)
    #expect(doc.ids(ofClass: "staff").count == 54)
    #expect(doc.ids(ofClass: "note").count == 69)
    for id in doc.ids(ofClass: "measure") {
        let f = try #require(doc.frames[id])
        #expect(f.width > 50 && f.height > 500, "measure \(id) spans all staves: \(f)")
    }
    let t1 = Date()
    let img = render(doc, scale: 2)
    let draw = Date().timeIntervalSince(t1)
    let ink = darkFraction(img)
    #expect(ink > 0.01 && ink < 0.3)
    if let out = ProcessInfo.processInfo.environment["SVG_RENDER_OUT"] { writePNG(img, out) }
    print("svg-render parse \(Int(parse * 1000)) ms, draw@2x \(Int(draw * 1000)) ms, ops \(doc.ops.count), ink \(ink)")
}
