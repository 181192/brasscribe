# Scribe, the family

Scribe is the family Brasscribe and Fretscribe belong to. It is not a product: it has no app, no
icon in a store and no token file. It appears where the products appear together: the bar at the
top of every page of the site, the family's home page and the Bandroom page.

**The idea: the desk and the pen**, where anything played becomes something written. The family is
the desk and the pen; each product is a sheet of its own paper laid on it (an engraved band part, a
ruled notebook page). The pen line runs through every page as the place where sound becomes writing.

## The mark

A pen writing a line: a stroke that ends in a filled dot (`mark.svg`). It is the playhead of every
product's page, the line that separates what has been heard from what has been written, turned on
its side. It is drawn in the colour of the text around it (`currentColor`) and is never coloured in
a product's brand colour. `favicon.svg` is the mark in paper on ink.

### The pen line

The family's one motif, made from the mark: a 2 px line ending in an 8 px dot, always horizontal or
vertical, always ink. It may be drawn through a product's sheet (as the playhead of its strip) but is
never coloured. It appears in the bar's mark (with its line run out to the edge on the family's own
pages: the pen is down), the favicon, under the last words of the home's headline and under the
family's section headings, as the arrows of its diagrams, as the bullets of its lists, and along the
top of a product's sheet when it is pointed at. Its sizes are `--family-pen-width` and
`--family-pen-dot` (`dist/web/line.css`).

## The name

"Scribe", set in the platform's own face at weight 600 to 650, beside the mark. The family has no
display face of its own: its headings are the platform's face at 650 with -0.02 em tracking
(`--family-display-weight`, `--family-display-tracking`), and never a product's. The products' faces
(Instrument Serif, Atkinson Hyperlegible Next) belong to the products; on a family page they appear
only inside a product's sheet.

Each level has one name: **Scribe** (the line), **Brasscribe** and **Fretscribe** (the apps; the site
does not add "Play"), and the places an app runs: "Brasscribe for iPhone", "Fretscribe for Mac",
**Bandroom** (the helper every app shares; "Scribe Bandroom" where a full name is needed) and
"Brasscribe Studio".

## Voice

The publisher's foreword: short, plain, about the apps and never about itself. "Play it. Scribe writes
it down." "One helper on your computer does the listening for every app." Not "a family of AI-powered
transcription products", not "two apps that try to write down what was played".

## The palette

No accent colour of its own: ink is the family's only colour. Every neutral role is the midpoint of
the brands' values in each mode, moved one step back so a product's own surface is the lightest thing
on a family page (in light mode one step further: desk linen under paper), and with no accent: where
a brand has its brand colour, the family has its text colour. In the bar each product has a 10 px
chip in its brand colour on a dark ground; the chip is the only brand colour in the bar.

The doubt mark ("?") in the site's own figures has one colour for every product,
`--family-doubt`: Fretscribe's `uncertain` (amber), which reads on both brands' papers. A picture of
a product's own score or tab keeps that product's own colours.

`design/tooling/family.py` makes `dist/web/scribe.css` (the tokens, as `--scribe-…`), `line.css`
(what the family puts on every page: the bar's colours, the chips, the pen line, the display face's
weight and tracking, the doubt colour), `variants/<place>.svg` (the glyphs of the places an app runs,
from `design/tooling/icons.json`) and `fonts.css` (empty), and its first lines state the rules. Run
it again when a brand's tokens change; CI checks that it was.

## Where a product begins

On a family page, a product's part is marked `data-brand="<product>"` and wears that product's
tokens. The family never mixes two brands' colours in one element.
