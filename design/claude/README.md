# Brasscribe design system for Claude

The design system is published as a Claude "Design System" artifact:
<https://claude.ai/artifact/HVMWuTurQEHoXnWARqic6G>

The page is regenerated from this folder (`design/`); nothing in it is edited by hand.
`build.py` turns the sources into the files the artifact keeps under `project/`:

- `tokens.json`: `tokens/tokens.json` in the artifact's list shape. Each colour mode is a theme (light first),
  and each role keeps its name (`color.light.bg` becomes `bg`).
- `README.md`, `components-on-each-platform.md`, `music-stand.md`: the brand book, taken from `README.md`,
  `system.md`, `brand/brand.md` and `music-stand.md`.
- `components/`: static previews and guidelines for the core components, and `bundle.css`, which is the
  component CSS from `mockups/mockup.css` pointed at the artifact's tokens.
- `fonts/` and `assets/`: Instrument Serif, the logos, the app icon masters, the icons, the mockup PNGs and
  the social preview, copied as they are. Mockups that show a computer name or a network address are left out.

Beside `project/` it writes `assets.json`, the map of asset files to upload (group, name, source, size,
media type). The artifact's index (`project/design-system.json`) is not generated: it holds the upload
ids and is updated when the artifact is published.

## Rebuild

```sh
uv run design/claude/build.py              # writes design/claude/out (ignored by git)
uv run design/claude/build.py --out DIR
```

The output depends only on the files under `design/`, so two runs give the same bytes.

## Keeping the artifact in sync

After a change to `design/` lands on `main`, ask Claude Code to republish the artifact. It rebuilds, then
compares the output with the published files and sends only the `project/` files that changed. Any new or
changed images go up first as uploads. The index goes last, re-read just before it is written so its other
keys are kept.
