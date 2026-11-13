# Scribe, the family

Scribe is the family Brasscribe and Fretscribe belong to. It is not a product: it has no app, no
icon in a store and no token file. It appears where the products appear together: the bar at the
top of every page of the site, and the family's home page.

## The mark

A pen writing a line: a stroke that ends in a filled dot (`mark.svg`). It is the playhead of every
product's page, the line that separates what has been heard from what has been written, turned on
its side. It is drawn in the colour of the text around it (`currentColor`) and is never coloured in
a product's brand colour. `favicon.svg` is the mark in paper on ink.

## The name

"Scribe", set in the platform's own face at weight 600 to 650, beside the mark. The family has no
display face: the products' faces (Instrument Serif, Atkinson Hyperlegible Next) belong to the
products, and on the family's home page each product's name and headline are set in its own.

## The palette

No colour of its own. Every neutral role is the midpoint of the brands' values in each mode, moved
one step back so a product's own surface is the lightest thing on a family page, and with no
accent: where a brand has its brand colour, the family has its text colour.
`design/tooling/family.py` makes `dist/web/scribe.css` (the tokens, as `--scribe-…`), `bar.css`
(the bar's three colours, the same in light and dark) and `fonts.css` (empty), and its first lines
state the rules. Run it again when a brand's tokens change; CI checks that it was.

## Where a product begins

On a family page, a product's part is marked `data-brand="<product>"` and wears that product's
tokens. The family never mixes two brands' colours in one element.
