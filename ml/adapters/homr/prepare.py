"""Pages made ready for homr: prepare.py <output folder> <page>...  (runs in the adapter's environment)

Every page is written to the output folder as page-NNN.<suffix>, in the order given. A picture is copied as it
is; a PDF's pages are rendered here, not by homr, so that their number and their size are bounded: at 300 dpi,
or less for a page so large that it would be more than MAX_PIXELS at 300 dpi. Nothing is decoded before its
size is known: a picture's is read from its header.

Exit 3 with one line, "scribe-refusal: <code>", for pages the engine refuses whatever they hold:
too_many_pages (more than MAX_PAGES once the PDFs are opened) and page_too_large (a picture over MAX_PIXELS).
"""

import shutil
import sys
from pathlib import Path

MAX_PAGES = 40  # as the engine's pages.MAX_PAGES
MAX_PIXELS = 50_000_000  # as the engine's pages.MAX_PIXELS
PDF_DPI = 300


def refuse(code: str) -> None:
    print(f"scribe-refusal: {code}", file=sys.stderr)
    sys.exit(3)


def main(out: Path, pages: list[Path]) -> None:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    written = 0

    def next_page(suffix: str) -> Path:
        nonlocal written
        written += 1
        if written > MAX_PAGES:
            refuse("too_many_pages")
        return out / f"page-{written:03d}{suffix}"

    for page in pages:
        if page.suffix.lower() != ".pdf":
            with Image.open(page) as im:  # the header only: nothing is decoded
                if im.width * im.height > MAX_PIXELS:
                    refuse("page_too_large")
            shutil.copyfile(page, next_page(page.suffix.lower()))
            continue
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(page))
        try:
            if written + len(pdf) > MAX_PAGES:
                refuse("too_many_pages")
            for i in range(len(pdf)):
                sheet = pdf[i]
                width, height = sheet.get_size()  # points
                scale = PDF_DPI / 72
                if width * height * scale * scale > MAX_PIXELS:
                    scale = (MAX_PIXELS / (width * height)) ** 0.5
                sheet.render(scale=scale).to_pil().convert("RGB").save(next_page(".png"))
        finally:
            pdf.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]])
