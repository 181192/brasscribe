# WCAG 2.2 AA checklist: Brasscribe Play and Studio

Every WCAG 2.2 Level A and AA success criterion, mapped to testable requirements for:

- **Play**, native apps: Apple (SwiftUI, macOS/iOS/iPadOS), Android (Jetpack Compose), Windows (WinUI 3).
- **Studio**, the browser UI served by the engine.

EN 301 549 clauses that go beyond WCAG for software come after the WCAG tables. Clause numbers are taken from **EN 301 549 V4.1.1 (2026-09)**. In clause 11 (non-web software), each WCAG criterion X.Y.Z is clause 11.X.Y.Z.

Platform keys in the tables: **A** Apple, **K** Android/Compose, **W** Windows/WinUI 3, **S** Studio (web).

## 1. Legal baseline (Norway)

| Source | What it says | Status |
|---|---|---|
| *Lov om likestilling og forbud mot diskriminering* (likestillings- og diskrimineringsloven, LOV-2017-06-16-51) §17 | Public and private undertakings *rettet mot allmennheten* must universally design their general functions (the physical environment). | Verified on Lovdata 2026-09-25 |
| Same act, §18 "Universell utforming av IKT" | Public and private undertakings must universally design the main ICT solutions aimed at or made available to users. Exemption for *uforholdsmessig stor byrde*, weighing effect, the undertaking's character, cost, size and resources. The duty is also met by meeting universal-design requirements in another act or regulation. The fifth paragraph lets the King issue regulations on scope and content. | Verified on Lovdata 2026-09-25 |
| *Forskrift om universell utforming av informasjons- og kommunikasjonsteknologiske (IKT)-løsninger* (FOR-2013-06-21-732) | Authority: ldl §§ 2, 18, 19a, 36, 36a, 41. Last amended by FOR-2023-01-17-87 (in force 2023-02-01). | Verified on Lovdata 2026-09-25 |
| Forskrift §4, private sector | WCAG 2.0 A and AA, except 1.2.3, 1.2.4 and 1.2.5. | Verified |
| Forskrift §4b, public sector | EN 301 549 V3.2.1 (2021-03), which references WCAG 2.1. | Verified |
| Forskrift §4e | Accessibility statement (*tilgjengelighetserklæring*): **public sector only**. | Verified |
| WCAG 2.2 | Not yet part of Norwegian regulation (uutilsynet, 2023-11-08). | See `docs/plan/research-app-stack.md` §5 |
| EN 301 549 V4.1.1 | Adopts WCAG 2.2. Not yet cited in the Official Journal, so V3.2.1 stays the legal reference. | See the research doc |

The project **targets WCAG 2.2 AA plus the applicable EN 301 549 V4.1.1 clauses**. That covers both legal floors (WCAG 2.0 for private, WCAG 2.1 via V3.2.1 for public) and lasts through the next revision of the regulation.

**Open legal questions**
1. **Scope.** Is a non-commercial, open project a *virksomhet* whose solution is *rettet mot allmennheten*? The regulations may not apply at all. We meet the target anyway.
2. **Private-sector native apps.** uutilsynet says apps must meet the same minimum as websites. The forskrift defines *mobilapplikasjon* in §3. Whether §4 (private sector) covers native desktop apps (macOS, Windows), as well as mobile apps and web, has not been checked in the text of §2.
3. **EAA.** The Norwegian transposition of the European Accessibility Act is delayed. Whether Play falls within its product or service scope was not assessed.
4. **4.1.1 Parsing.** It was removed in WCAG 2.2 and is *Void* in V4.1.1 (11.4.1.1). EN 301 549 V3.2.1, the current legal reference, still lists it. For Studio, which is HTML: keep markup valid (the axe-core `duplicate-id-*` rules). It costs nothing.

## 2. Project-wide rules

- Localisation: nb-NO and en from the first build, using platform localisation (String Catalogs, `strings.xml`, `.resw`, and ICU messages in Studio). The talking-score grammar is in [talking-score-spec.md](talking-score-spec.md).
- Colours come only from [design-tokens.json](design-tokens.json). CI runs `uv run qa/tools/contrast.py`.
- Notation is always drawn as an image (Verovio SVG or alphaTab canvas). The **talking score** is its accessible, reflowable equivalent, and any screen with notation offers it.
- Scripted screen-reader runs are in [../../qa/screen-reader-scripts/](../../qa/screen-reader-scripts/).

## 3. WCAG 2.2 A and AA (55 criteria)

### Perceivable

| SC | Lvl | Requirement for Brasscribe | Implementation | Test (tool) |
|---|---|---|---|---|
| 1.1.1 Non-text content | A | Every control has a name; the waveform, piano roll, spectrogram and score have a text alternative (a summary, plus the talking score for notation); decorative images are hidden. | A: `.accessibilityLabel`, `.accessibilityHidden(true)`, `.accessibilityChartDescriptor` for waveform and piano roll. K: `contentDescription`, `Modifier.semantics { hideFromAccessibility() }` or `clearAndSetSemantics {}` for decoration. W: `AutomationProperties.Name`, `AccessibilityView="Raw"`. S: `alt`, `aria-label`, `role="img"` + `aria-labelledby` on the SVG score, `aria-hidden` for decoration. | Audit every screen (Xcode Accessibility Inspector; Accessibility Scanner; Accessibility Insights FastPass; axe-core `image-alt`, `svg-img-alt`, `button-name`) |
| 1.2.1 Audio-only and video-only (prerecorded) | A | The imported recording is the user's own content, so no alternative is needed. Tutorial videos we ship get a transcript. The talking score is the text alternative for generated audio (playback). | Transcript files beside tutorials. | Manual: each shipped tutorial has a transcript |
| 1.2.2 Captions (prerecorded) | A | Shipped tutorial videos have captions. Imported video keeps its caption tracks; see EN 301 549 7.1. | A: AVPlayer legible media selection. K: Media3 text tracks. W: `MediaPlayerElement` with `TimedTextSource`. S: `<track kind="captions">`. | Manual: import an MP4 with a caption track; captions appear in picture-in-picture |
| 1.2.3 Audio description or media alternative | A | Tutorials: a full text transcript that includes visual actions. | as 1.2.1 | Manual |
| 1.2.4 Captions (live) | AA | Not applicable (no live media). Recording from the microphone is not live media for others. | – | N/A, recorded in the audit |
| 1.2.5 Audio description (prerecorded) | AA | Tutorials: describe on-screen actions in the narration, or ship a described version. | – | Manual |
| 1.3.1 Info and relationships | A | Headings per screen section; the part list is a list; the talking score has a part → bar → beat hierarchy exposed as structure, not only as text; form fields are tied to their labels. | A: `.accessibilityAddTraits(.isHeader)`, `.accessibilityElement(children: .contain)`, `accessibilityRotor` for parts and bars. K: `semantics { heading() }`, `collectionInfo`/`collectionItemInfo`, `isTraversalGroup`. W: `AutomationProperties.HeadingLevel`, `ListView`/`TreeView`, `ITableProvider` for the bar grid. S: `<h1>`–`<h3>`, `<ul>`, `<table>` with `<th scope>`, `<label for>`. | Inspect the tree (Accessibility Inspector hierarchy; `uiautomator dump`; Accessibility Insights Live Inspect; axe `heading-order`, `list`, `label`) |
| 1.3.2 Meaningful sequence | A | Reading order: transport → current position → score or talking score. The player bar is not read before the content on every swipe. | A: `.accessibilitySortPriority`. K: `semantics { traversalIndex }`. W: XAML order and `TabIndex`. S: DOM order equals visual order. | Swipe through each screen with the screen reader and compare to the script |
| 1.3.3 Sensory characteristics | A | No instruction relies on colour, shape or position alone ("tap the red notes" is not allowed; say "notes marked uncertain"). | Copy review | Manual review of all strings (en, nb) |
| 1.3.4 Orientation | AA | Play works in portrait and landscape on iOS, iPadOS and Android. | Do not lock orientation. | Rotate each screen (device) |
| 1.3.5 Identify input purpose | AA | Few personal-data fields exist. The pairing code uses `oneTimeCode`; a name or e-mail for export metadata uses name/email content types. | A: `.textContentType(.oneTimeCode)`. K: `semantics { contentType = ContentType.SmsOtpCode }` / autofill hints. W: `InputScope`. S: `autocomplete="one-time-code"`. | Inspect |
| 1.4.1 Use of colour | A | Uncertainty, the active part, the loop range, the cursor and errors are shown by shape, pattern or text **as well as** colour. See [visual-design-tokens.md](visual-design-tokens.md) §2. Engine output today uses red only (`#D0021B`, 230 solo notes in the Mikkel golden output): fails. | Notehead shape plus marker in all renderers. A: honour `accessibilityDifferentiateWithoutColor` by adding a text badge. | `qa/tools/musicxml_readability.py --check` (`colour_only_uncertain` = 0); greyscale screenshot review |
| 1.4.2 Audio control | A | Playback never starts on its own. A pause/stop control is reachable in one step and is the first control in the player bar. The metronome and count-in have their own volume. | – | Manual: open a score; nothing plays |
| 1.4.3 Contrast (minimum) | AA | Text ≥ 4.5:1, large text ≥ 3:1, in all three themes. | Tokens | `uv run qa/tools/contrast.py` (CI); spot checks with Accessibility Inspector Color Contrast Calculator, Accessibility Scanner, and Accessibility Insights Colour Contrast; axe `color-contrast` |
| 1.4.4 Resize text | AA | UI text scales to 200% (Dynamic Type up to AX5 on iOS; font scale 2.0 on Android; Windows text size 225%) without loss of function. The notation zooms separately up to 400%. | A: Dynamic Type fonts (`.font(.body)`), no fixed heights. K: `sp` units, no fixed heights. W: honour `UISettings.TextScaleFactor` (the default for XAML text). S: `rem`, browser zoom 200%. | Screenshots at max text size; nothing clipped or overlapping |
| 1.4.5 Images of text | AA | No text rendered as images. Titles, part names and bar numbers inside the notation image have a text equivalent (the talking score). | – | Review |
| 1.4.10 Reflow | AA | UI reflows at 320 CSS px width (or the platform equivalent: 1280 px at 400%). The **score** needs two-dimensional layout; the talking score and the single-part view are the reflowable alternative. | K/A: size classes; the score becomes a single-staff horizontal view. S: CSS grid, no fixed widths. | Studio: browser at 320 px, axe plus manual. Native: iPad Split View at its narrowest width; Android split screen; Windows at 500 px wide |
| 1.4.11 Non-text contrast | AA | Controls, focus rings, noteheads, staff lines, the cursor, loop edges and uncertainty marks ≥ 3:1 against adjacent colours. | Tokens | `contrast.py` (CI) plus manual checks of real screenshots |
| 1.4.12 Text spacing | AA | Studio: no loss when line-height is 1.5, paragraph spacing 2, letter spacing 0.12 and word spacing 0.16 em. Native: text containers grow; no fixed-height labels. | S: no fixed heights on text boxes. | Studio: text-spacing bookmarklet; Native: largest text size |
| 1.4.13 Content on hover or focus | AA | Note tooltips (pitch, confidence) and help popovers can be dismissed with Esc without moving focus, can be hovered, and stay until dismissed. | A: `.help()` on macOS. W: `ToolTipService`. S: tooltip pattern with Esc. | Manual |

### Operable

| SC | Lvl | Requirement for Brasscribe | Implementation | Test (tool) |
|---|---|---|---|---|
| 2.1.1 Keyboard | A | Everything works from the keyboard on macOS, Windows, iPad with keyboard, Android with keyboard, and Studio. That covers import, record, transcribe, cancel, review, next/previous uncertain note, part mute/solo, loop set by bar numbers, speed, play-along, talking-score navigation and export. See the keyboard script. | A: `.focusable()`, `.keyboardShortcut`, `.onKeyPress`, Full Keyboard Access (iOS). K: `Modifier.focusable()`, `onKeyEvent`, `FocusRequester`. W: native tab order, `KeyboardAccelerator`, `AccessKey`. S: native elements, `tabindex="0"` only on the custom score widget, roving tabindex inside it. | `qa/screen-reader-scripts/keyboard-desktop.md` (Mac, Windows, Studio); iPad with Full Keyboard Access |
| 2.1.2 No keyboard trap | A | The score canvas captures arrow keys but Tab/Shift+Tab (and Esc) always leave it. Modal dialogs trap focus until they close, which is allowed. | – | Keyboard script, step K-12 |
| 2.1.4 Character key shortcuts | A | Single-key shortcuts (Space, L, [, ], digits) work **only while the score or player has focus**, and can be turned off or remapped in Settings. Global shortcuts use a modifier. | Scope handlers to the focused view; add a Settings → Keyboard page. | Keyboard script K-20; with the screen reader on, single keys do not fight VoiceOver/NVDA quick-nav |
| 2.2.1 Timing adjustable | A | No time limits. The LAN pairing code does not expire while the pairing screen is open; if it expires, one action renews it with no data lost. A transcription job never times out on the user. | – | Leave the pairing screen open for 30 min |
| 2.2.2 Pause, stop, hide | A | The auto-scrolling score during playback stops when playback stops. A "follow playback" toggle turns off auto-scroll. Progress animations stop under reduced motion; the progress text stays. | A: `accessibilityReduceMotion`. K: `ANIMATOR_DURATION_SCALE` 0. W: `UISettings.AnimationsEnabled`. S: `prefers-reduced-motion`. | Manual with reduced motion on |
| 2.3.1 Three flashes or below | A | A visual metronome flash per beat is 3.4 Hz at 136 bpm × 150% speed, which is over the limit. So the visual beat indicator is a **non-flashing** moving dot or beat counter; no full-screen or large-area flashing. | – | Code review; slowest-to-fastest playback at 150% |
| 2.4.1 Bypass blocks | A | Studio: a "skip to main" link and landmarks. Native: *Void* for non-web software in EN 301 549 (11.2.4.1); still provide headings and rotors. | S: `<main>`, `<nav>`, skip link. | axe `bypass`, `region` |
| 2.4.2 Page titled | A | Each window/screen has a title ("Mikkel: Solo Cornet part"). EN 301 549 11.2.4.2 "Non-web software titled". | A: `.navigationTitle`. K: `semantics { paneTitle }` on screens. W: `Window.Title`, `AppWindow.Title`. S: `<title>` updated on route change. | Inspect |
| 2.4.3 Focus order | A | Focus order follows reading order. After a dialog closes, focus returns to the control that opened it. After a transcription completes, focus moves to the result heading, and the move is announced. | A: `@AccessibilityFocusState`. K: `FocusRequester`. W: `FocusManager.TryFocusAsync`. S: `dialog.showModal()` returns focus. | Scripts |
| 2.4.4 Link purpose (in context) | A | Links say where they go ("Open in MuseScore", not "Open"). | – | axe `link-name`; review |
| 2.4.5 Multiple ways | AA | Studio: pipeline runs reachable by list and by search. Native: *Void* for software (11.2.4.5). | – | Manual |
| 2.4.6 Headings and labels | AA | Headings and labels describe the content: "Part: Solo Cornet", "Speed 75 percent". | – | Review |
| 2.4.7 Focus visible | AA | A visible focus ring on every focusable element, including the current note or bar in the score (at least 2 px, token `focus`, ≥ 3:1). | A: default focus ring; custom `.focusEffect` on the score. K: `Modifier.border` on focus / `indication`. W: `UseSystemFocusVisuals="True"`, `FocusVisualKind="HighVisibility"`. S: `:focus-visible` outline. | Keyboard script; screenshots |
| 2.4.11 Focus not obscured (minimum) | AA | The sticky player bar and toasts never fully cover the focused note, bar or control. Scroll the focused element into the visible area above the player bar. | A: `.safeAreaInset(edge: .bottom)` for the player bar. K: `bringIntoViewRequester`. W: `StartBringIntoView`. S: `scroll-padding-bottom` = player bar height. | Keyboard script K-9 (tab through score with player bar shown) |
| 2.5.1 Pointer gestures | A | Pinch-zoom has +/- buttons; two-finger scrub has a slider; swipe between parts has a part picker. | – | Manual |
| 2.5.2 Pointer cancellation | A | Actions fire on up-event. The record button is tap-to-toggle, not press-and-hold. | Default buttons | Manual: press record, drag off, release; nothing happens |
| 2.5.3 Label in name | A | The visible label is contained in the accessible name ("Play", not "Start playback" on a button labelled "Play"). This matters for Voice Control and Voice Access. | – | Voice Control on macOS/iOS: "Click Play"; Voice Access on Android; Windows Voice Access |
| 2.5.4 Motion actuation | A | No shake or tilt actions. | – | N/A |
| 2.5.7 Dragging movements | AA | The loop range, the waveform selection and the speed slider have non-drag alternatives: bar-number fields ("Loop from bar [12] to bar [16]"), step buttons, and keyboard. | Steppers or text fields. A: `.accessibilityAdjustableAction`. K: `semantics { setProgress }`. W: `Slider` with `SmallChange`. S: `<input type=number>`. | Manual: set a loop without dragging |
| 2.5.8 Target size (minimum) | AA | Targets ≥ 24×24 CSS px (we use 44 pt on Apple, 48 dp on Android, and 32×32 epx minimum on Windows). Part chips and transport buttons on phone. Note selection in the score via keyboard or talking score is the equivalent for small noteheads. | K: `Modifier.minimumInteractiveComponentSize()`. A: `.frame(minWidth: 44, minHeight: 44)` / `.contentShape`. | Accessibility Scanner (touch target); Accessibility Inspector audit (hit region); axe `target-size` |

### Understandable

| SC | Lvl | Requirement for Brasscribe | Implementation | Test (tool) |
|---|---|---|---|---|
| 3.1.1 Language of page | A | The app language is set (nb or en), so the screen reader picks the right voice. | A: localisation, `CFBundleDevelopmentRegion`. K: `values-nb`. W: `ApplicationLanguages.PrimaryLanguageOverride`. S: `<html lang>`. | Switch the system language; the voice follows |
| 3.1.2 Language of parts | AA | English titles inside Norwegian UI (song titles) are marked where known. Note names follow the UI language (the talking-score spec). Native: *Void* (11.3.1.2), but set `accessibilityLanguage` on known-language strings anyway. | A: `AttributedString` with the `accessibilitySpeechLanguage` attribute. K: `LocaleSpan`. W: `Language` property. S: `lang` attribute. | Manual |
| 3.2.1 On focus | A | Focusing a note does not start playback or change the view. | – | Scripts |
| 3.2.2 On input | A | Choosing a lineup or difficulty does not re-transcribe until the user presses "Apply". | – | Scripts |
| 3.2.3 Consistent navigation | AA | Studio: the same nav on every page. Native: *Void* (11.3.2.3); keep the tab bar/sidebar order the same anyway. | – | Review |
| 3.2.4 Consistent identification | AA | The same icon and name for the same function everywhere ("Loop" is always "Loop"). | String catalogue review | Review |
| 3.2.6 Consistent help | A | Help (link to the docs and the shortcut list) is in the same place on each screen. Native: *Void* (11.3.2.6). | – | Review |
| 3.3.1 Error identification | A | Failed import, unsupported file, DRM-protected source, companion not reachable, and transcription failure are each described in text and announced. | Live region / notification | Scripts step "error" |
| 3.3.2 Labels or instructions | A | Every field has a label: bar numbers, speed, pairing code, key. | – | axe `label`; inspect |
| 3.3.3 Error suggestion | AA | Suggest a fix: "Bar 140 doesn't exist. This score has 128 bars." / "Start the engine on your computer, then try again." | – | Scripts |
| 3.3.4 Error prevention (legal, financial, data) | AA | Not directly applicable. Still: overwriting an export or discarding a review asks for confirmation or can be undone. | – | Manual |
| 3.3.7 Redundant entry | A | Lineup, difficulty and key choices are remembered per song and pre-filled on re-run. | – | Manual |
| 3.3.8 Accessible authentication (minimum) | AA | LAN pairing does not require transcribing a code from one screen to another from memory: offer a QR code, and allow paste and autofill (`oneTimeCode`). No cognitive puzzles. | – | Manual: pair using only paste; pair with QR |

### Robust

| SC | Lvl | Requirement for Brasscribe | Implementation | Test (tool) |
|---|---|---|---|---|
| 4.1.2 Name, role, value | A | Custom controls (score canvas, part mixer, loop range, transport, speed) expose role, name, state and value, and changes to them. The score exposes the current note as its value ("bar 12, beat 1: E-flat 5, quarter note, uncertain"). | A: `.accessibilityElement`, `.accessibilityValue`, `.accessibilityAdjustableAction` (increment = next note), `.accessibilityActions`, custom rotors "Parts", "Bars", "Uncertain notes". K: `semantics { role; stateDescription; customActions }`, `toggleableState` for mute/solo. W: custom `AutomationPeer` (`OnCreateAutomationPeer`) implementing `IRangeValueProvider` (speed), `IToggleProvider` (mute/solo), `IValueProvider` (current note text), `ISelectionProvider` (parts); `IGridProvider` for bars × parts if the grid view exists. S: native controls first; ARIA `role="slider"` + `aria-valuetext`, `aria-pressed` for mute/solo. | Accessibility Inspector; Accessibility Insights (Live Inspect, patterns); Compose `SemanticsMatcher` tests; axe |
| 4.1.3 Status messages | AA | Transcription progress ("Transcribing, 40 percent, about 2 minutes left"), completion, errors, "Loop set, bars 12 to 16" and speed changes are announced without moving focus. Progress is throttled (at most one announcement every 10 s, or at each 10% step). | A: `AccessibilityNotification.Announcement(...).post()`; `.accessibilityAddTraits(.updatesFrequently)` on the position. K: `semantics { liveRegion = LiveRegionMode.Polite }`, `progressBarRangeInfo`. W: `AutomationPeer.RaiseNotificationEvent(AutomationNotificationKind.ActionCompleted, ...)`, `AutomationProperties.LiveSetting="Polite"`. S: `role="status"` / `aria-live="polite"`, `<progress>`. | Scripts step "transcribe" |

## 4. EN 301 549 V4.1.1 clauses beyond WCAG

| Clause | Requirement for Brasscribe | Test |
|---|---|---|
| 4.2.1 Usage without vision | The whole flow, from import to BRF export, works with a screen reader. The talking score and braille give access to notation. | All screen-reader scripts |
| 4.2.2 Usage with limited vision | Zoom to 400% for notation; follow the platform text size, magnifier and high contrast. | visual-design-tokens.md §4–5 |
| 4.2.3 Usage without perception of colour | Shape encoding for uncertainty, loop and cursor. | `contrast.py` CVD table; greyscale review |
| 4.2.4 Usage without hearing | Metronome, count-in and play-along cues have visual equivalents (beat counter "1 2 3 4", count-in numerals). "Listen to this bar" has a visual counterpart (piano roll overlay of original versus score). Audio-only feedback (intonation, later) must also have a text or visual form. | Manual with sound muted |
| 4.2.5 Usage with limited hearing | Separate volume for metronome, original and score; mono playback option; no information carried only by stereo position (seating placement). | Manual |
| 4.2.7 Usage with limited manipulation or strength | Everything works with Switch Control, Switch Access and Voice Control; no timing-critical input. Play-along uses the microphone, and is never required to finish a task. | Switch Control run of the core flow |
| 4.2.8 Usage with limited reach | Not applicable (no hardware). | – |
| 4.2.9 Minimize photosensitive seizure triggers | As 2.3.1: no flashing beat indicator. | – |
| 4.2.10 Usage with limited cognition, language or learning | Plain language in both languages; one decision per step ("What is this?"); undo; no jargon in default views (Studio may use technical terms). | Copy review |
| 4.2.11 Privacy | Recordings stay on the device or the user's own computer (no cloud). Screen-reader output doesn't expose the pairing code on a lock screen. | Review |
| 5.2 Activation of accessibility features | Accessibility features (high-contrast theme, talking score) can be activated without sight; they follow the system settings by default. | Scripts |
| 5.4 Preservation of accessibility information during conversion | Exports keep what the target format supports: MusicXML keeps part names, `<words>ad lib.</words>`, dynamics and the uncertainty flag; the talking-score text export keeps headings; BRF keeps the part and bar structure; PDF see clause 10. | Round-trip check: export → reopen → compare |
| 5.9 Simultaneous user actions | No two-finger-plus-key combinations required. | Review |
| 5.10 Authoring tools (5.10.1–5.10.5) | **Open question.** Play generates documents (MusicXML, PDF, BRF). If it counts as an authoring tool, the output must be able to conform to clause 10 (PDF tagging), and accessibility information must survive transformations. | Decide with the owner |
| 7.1.1–7.1.5 Subtitle processing | Imported video with subtitle tracks: show them in the video view and picture-in-picture, keep them in sync, keep them on re-export (7.1.3). | Import a subtitled MP4 |
| 7.3 User control of audiovisual accessibility features | The subtitle toggle is at the same level as play/pause. | Manual |
| 10 Non-web documents | The PDF export (MuseScore/Verovio) is very likely **untagged**. **Open question:** tagged PDF is not realistic for engraved notation; declare the talking-score text, MusicXML and BRF exports as the accessible alternatives and document it (clause 12). | Check a PDF with PAC or Acrobat |
| 11.5.2.x Accessibility services (object information, values, label relationships, parent-child, text, list and execution of actions, focus tracking, change notification) | Custom score and mixer controls use platform accessibility APIs, not self-voicing. Custom actions are listed and executable (11.5.2.11–12): "Play this bar", "Loop this bar", "Mark as checked", "Next uncertain note". Focus changes and value changes raise events (11.5.2.13, 11.5.2.15–17). | Accessibility Insights (events); Accessibility Inspector (actions); TalkBack actions menu |
| 11.6.1 User control of accessibility features / 11.6.2 No disruption | Don't override the system screen reader, zoom, text size or keyboard navigation; don't hijack VO/NVDA key combinations. | Scripts |
| 11.7 User preferences | Follow the system text size, contrast, reduced motion, colour filters and dark mode. At least one mode follows system settings exactly. | visual-design-tokens.md §3–4 |
| 12.1 / 12.3 Documentation of accessibility features | A user-facing page listing accessibility features, the keyboard shortcuts, and known limitations (e.g. untagged PDF), in nb and en, reachable from Help. | Review |

## 5. Test tools per platform

| Platform | Automated | Manual |
|---|---|---|
| Apple | Xcode Accessibility Inspector audit; `XCUIApplication().performAccessibilityAudit()` (Xcode 15+) in UI tests. **Not available on this machine** (Command Line Tools only, no Xcode), so it runs on a Mac with Xcode or in CI. | VoiceOver (macOS, iOS), Voice Control, Switch Control, Full Keyboard Access |
| Android | Accessibility Test Framework via `AccessibilityChecks.enable()` (Espresso) and Compose tests; Android Accessibility Scanner on a device | TalkBack, Switch Access, Voice Access |
| Windows | Axe.Windows (NuGet) in UI tests; Accessibility Insights for Windows FastPass | Narrator, NVDA, high-contrast themes |
| Studio | `@axe-core/playwright` in CI (rules for WCAG 2.2 AA: tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`) | NVDA + Firefox or Chrome, VoiceOver + Safari |
| Output | `uv run qa/tools/musicxml_readability.py --check <file>`, `uv run qa/tools/contrast.py` | Readability review by a player |

## Open questions

1. Is the notation view a two-dimensional exception under 1.4.10? We treat it as one, with the talking score and single-part view as the reflowable alternatives.
2. Does 5.10 (authoring tools) apply to Play's exports? See clause 10 above.
3. Is BRF from `music21.braille` readable by braille-music users? This needs a review by a braille-music reader. The local MuseScore BRF export aborted in the agent shell (see the research doc).
4. The legal scope questions in §1.
