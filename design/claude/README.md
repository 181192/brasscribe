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
  the social preview, copied as they are. Only the mockup screens listed in `PUBLISHED_MOCKUPS` are copied; the
  build stops on a screen it doesn't know, so a new one is published only after it is added to a list.

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

After a change to `design/` lands on `main`, ask Claude Code to republish the artifact, or do it by hand:

1. Run `uv run design/claude/build.py`.
2. Upload new or changed images from `out/project/assets/` as assets to the artifact url.
3. Publish the `project/` files that changed (never the whole tree).
4. Last, read the current `project/design-system.json`, keep its keys, update the asset records and
   `lastChange`, and write it back.

Reading the artifact's content fails behind some corporate web filters (the host answers HTTP 307), and
publishing needs that read first. Run these steps from another network.
