# Changelog

Every release of Brasscribe, newest first. Generated from the commit history by git-cliff (`cliff.toml`).

## 0.7.1 (2026-10-04)

### Fixes

- **Android:** The score still plays and redraws after Read aloud ([#275](https://github.com/181192/brasscribe/pull/275))

## 0.7.0 (2026-10-04)

### New features

- **Android:** Fretscribe's Home no longer offers Open a tab ([#233](https://github.com/181192/brasscribe/pull/233))
- **Android:** A solo opens straight on your part after Check the notes ([#244](https://github.com/181192/brasscribe/pull/244))
- **Android:** While a repeat is set on the music stand, the page pedals play, pause and go back to its start ([#240](https://github.com/181192/brasscribe/pull/240))
- **Android:** Print and share a PDF without the computer: the phone lays out your part, every part and the score ([#251](https://github.com/181192/brasscribe/pull/251))

### Fixes

- **Android:** Read the pairing QR code on the phone, without Google's scanner ([#236](https://github.com/181192/brasscribe/pull/236))
- **Android:** Show a score opened while another score is on screen ([#259](https://github.com/181192/brasscribe/pull/259))
- **Bandroom for Windows:** Show the status icon in Dark's colours ([#230](https://github.com/181192/brasscribe/pull/230))
- **Bandroom for Windows:** Tab reaches Remove on every paired phone ([#253](https://github.com/181192/brasscribe/pull/253))
- **Windows:** Home and every screen turn dark at once when you choose Dark in Settings ([#252](https://github.com/181192/brasscribe/pull/252))
- **Windows:** Screen readers say "Try again" on the error screen ([#257](https://github.com/181192/brasscribe/pull/257))

<details><summary>Under the hood (4 changes: docs, tests, CI, build, refactoring)</summary>


- **Design:** The glossary says «Demp» for mute in Norwegian, as the apps do ([#235](https://github.com/181192/brasscribe/pull/235))
- **Engine:** Keep Beat This! small0 for solo scores made on the computer ([#231](https://github.com/181192/brasscribe/pull/231))
- **Engine:** A ukulele chord heard on three strings is completed to four when a doubling fits ([#232](https://github.com/181192/brasscribe/pull/232))
- **Eval:** The Slakh guitar song set is slakh-guitar again ([#241](https://github.com/181192/brasscribe/pull/241))

</details>

## 0.6.0 (2026-10-04)

### New features

- **Android:** Fretscribe's practice keeps each song's speed, repeat and place after the app is closed ([#196](https://github.com/181192/brasscribe/pull/196))
- **Android:** Fretscribe's practice player labels the speed, and holding − or + keeps stepping ([#194](https://github.com/181192/brasscribe/pull/194))
- **Android:** Fretscribe's "Check them" goes to the first ?, and a ?'s note offers Play this bar slowly and Next ? ([#195](https://github.com/181192/brasscribe/pull/195))
- **Android:** Print with Every part is one print job, not a dialog for each player ([#217](https://github.com/181192/brasscribe/pull/217))
- **Android:** Repeat opens on the bar you are at, and holding the music stand's speed keeps stepping ([#211](https://github.com/181192/brasscribe/pull/211))
- **Android:** A score opens where you left it in practice, also after the app was closed ([#213](https://github.com/181192/brasscribe/pull/213))
- **Android:** A tap on a "?" on the score opens Check the notes at that note, and Check them goes on where you left off ([#215](https://github.com/181192/brasscribe/pull/215))

### Fixes

- **Android:** Back on Record asks before it throws the take away ([#191](https://github.com/181192/brasscribe/pull/191))
- **Android:** Back while a recording is written down asks before it stops the job ([#190](https://github.com/181192/brasscribe/pull/190))
- **Android:** Fretscribe's pairing screen and Settings show only what a player can use ([#188](https://github.com/181192/brasscribe/pull/188))
- **Android:** Fretscribe's Help says what the keys and pedals do on the tab ([#189](https://github.com/181192/brasscribe/pull/189))
- **Android:** Brasscribe's Help, pairing and Check the notes say what is true, in plain words ([#203](https://github.com/181192/brasscribe/pull/203))
- **Android:** With nothing paired, the problem screens offer to connect the computer ([#205](https://github.com/181192/brasscribe/pull/205))
- **Android:** Back from Check the notes goes to the score, not to What is this? ([#207](https://github.com/181192/brasscribe/pull/207))
- **Android:** The music stand and a phone on its side start with the music, not the engraved title ([#209](https://github.com/181192/brasscribe/pull/209))
- **Studio:** On a narrow screen the score page fits, focus never hides under the open menu, and headings no longer break mid-word ([#193](https://github.com/181192/brasscribe/pull/193))
- **Studio:** The narrow navigation menu closes on Escape and whenever focus moves outside it ([#199](https://github.com/181192/brasscribe/pull/199))

<details><summary>Under the hood (3 changes: docs, tests, CI, build, refactoring)</summary>


- **Android:** The screens are tested on the JVM, with screenshots and accessibility checks, in CI ([#133](https://github.com/181192/brasscribe/pull/133))
- **Studio:** A screen catalogue of every view on the built bundle, checked in CI with screenshots against the merge base ([#180](https://github.com/181192/brasscribe/pull/180))
- **Windows:** Run the Windows apps' checks on pull requests that reach them ([#176](https://github.com/181192/brasscribe/pull/176))

</details>

## 0.5.0 (2026-10-03)

### New features

- **Android:** A recording waits in Your scores until its score is made ([#143](https://github.com/181192/brasscribe/pull/143))

### Fixes

- **Accessibility:** The talking score names plain eighths in 6/8, 9/8 and 12/8 as eighths, not triplets ([#139](https://github.com/181192/brasscribe/pull/139))
- **Accessibility:** Whole-bar rests in compound time carry the compound flag ([#155](https://github.com/181192/brasscribe/pull/155))
- **Android:** Music stand in the score's ⋯ sheet is no longer cut off at large text ([#129](https://github.com/181192/brasscribe/pull/129))
- **Android:** The keyboard reaches a screen's choices before the button under them ([#140](https://github.com/181192/brasscribe/pull/140))
- **Android:** A band draft opens on the score, not in Check the notes ([#132](https://github.com/181192/brasscribe/pull/132))
- **Android:** The transcribing screen says to keep Brasscribe open, and no longer shows a time left that stands still ([#135](https://github.com/181192/brasscribe/pull/135))
- **Android:** Sending a recording works the first time, and again when the computer has let go of it ([#147](https://github.com/181192/brasscribe/pull/147))
- **Android:** A recording is not sent twice after a timeout, and No notes found offers the microphone after a file ([#164](https://github.com/181192/brasscribe/pull/164))
- **Android:** Keep ONNX Runtime from reporting to Microsoft ([#169](https://github.com/181192/brasscribe/pull/169))
- **Bandroom:** Say why the engine can't start when pixi refuses the workspace ([#128](https://github.com/181192/brasscribe/pull/128))
- **Bandroom:** After an update that can't finish, say so while the previous version keeps running ([#138](https://github.com/181192/brasscribe/pull/138))
- **Core:** Name the C calling convention on every .NET import ([#123](https://github.com/181192/brasscribe/pull/123))
- **Core:** The Windows command line download runs without the Visual C++ runtime ([#130](https://github.com/181192/brasscribe/pull/130))
- **Core:** A tab's slide or bend starts from the note before it on the same string ([#134](https://github.com/181192/brasscribe/pull/134))
- **Engine:** Make the band score's PDF once MuseScore is installed or updated ([#127](https://github.com/181192/brasscribe/pull/127))
- **Engine:** Open chords and 6/8 bars no longer misread when a note is left out or the beat swings ([#124](https://github.com/181192/brasscribe/pull/124))
- **Engine:** A renamed score's PDF, MIDI and braille carry the new title ([#131](https://github.com/181192/brasscribe/pull/131))
- **Engine:** A melody played high over a ringing chord keeps its notes in the tab ([#137](https://github.com/181192/brasscribe/pull/137))
- **Engine:** A short note in a tab gets the straight length nearest to how it was played ([#141](https://github.com/181192/brasscribe/pull/141))
- **Engine:** Leave out the overtones a ukulele melody pulled up the neck ([#149](https://github.com/181192/brasscribe/pull/149))
- **Engine:** Keep a bass line that really sits high in its octave ([#145](https://github.com/181192/brasscribe/pull/145))
- **Fretscribe:** Next bar says when you are in the last bar, and a fetched recording is no longer lost ([#146](https://github.com/181192/brasscribe/pull/146))
- **Fretscribe:** Pairing, Help, About and problem screens say Fretscribe, not Brasscribe ([#148](https://github.com/181192/brasscribe/pull/148))
- **Scripts:** Tag a release whose commit is on main's own line ([#122](https://github.com/181192/brasscribe/pull/122))
- **Windows:** Name the C calling convention on the core bridge imports ([#153](https://github.com/181192/brasscribe/pull/153))
- **Windows:** Play for Windows runs without the Visual C++ runtime installed ([#160](https://github.com/181192/brasscribe/pull/160))

<details><summary>Under the hood (8 changes: docs, tests, CI, build, refactoring)</summary>


- **Android:** Stop the JVM tests aborting at exit when ONNX Runtime uploads telemetry ([#126](https://github.com/181192/brasscribe/pull/126))
- **CI:** Stricter Windows import check, and vector changes run the tests that read them ([#167](https://github.com/181192/brasscribe/pull/167))
- **Core:** Compare the talking score of a score in compound time ([#158](https://github.com/181192/brasscribe/pull/158))
- **Engine:** Say what the 6/8 rule costs and which takes its numbers come from ([#151](https://github.com/181192/brasscribe/pull/151))
- **Eval:** Measure Beat This! small0 against final0 for solo scores ([#144](https://github.com/181192/brasscribe/pull/144))
- **Studio:** Regenerate the engine API types and check the copies stay in step ([#125](https://github.com/181192/brasscribe/pull/125))
- **Talking-score:** Android and Windows read the conformance vectors from docs/ ([#157](https://github.com/181192/brasscribe/pull/157))
- **Windows:** Bring the engine client's API snapshot up to date and keep it in step ([#136](https://github.com/181192/brasscribe/pull/136))

</details>

## 0.4.0 (2026-10-02)

### New features

- **Android:** Build Fretscribe as a second app from the same code ([#82](https://github.com/181192/brasscribe/pull/82))
- **Android:** Give Fretscribe its own colours, title font and icon ([#87](https://github.com/181192/brasscribe/pull/87))
- **Bandroom:** Show the band writer's terms before downloading it ([#47](https://github.com/181192/brasscribe/pull/47))
- **Bandroom:** Bass tabs work with Bandroom for Mac and Windows ([#85](https://github.com/181192/brasscribe/pull/85))
- **Core:** Choose a string and fret for every note on fretted instruments ([#50](https://github.com/181192/brasscribe/pull/50))
- **Core:** Suggest tunings, honour playing techniques and prefer chord shapes on fretted instruments ([#62](https://github.com/181192/brasscribe/pull/62))
- **Core:** Write fretted tablature as MusicXML ([#64](https://github.com/181192/brasscribe/pull/64))
- **Core:** Name the source note on every note of the tab MusicXML ([#81](https://github.com/181192/brasscribe/pull/81))
- **Core:** Tab fingering for fretted instruments through the bindings ([#84](https://github.com/181192/brasscribe/pull/84))
- **Design:** Generate the Claude design system from design/ ([#48](https://github.com/181192/brasscribe/pull/48))
- **Engine:** Correct the recording's tuning before writing the notes ([#59](https://github.com/181192/brasscribe/pull/59))
- **Engine:** Write a bass line as tablature ([#65](https://github.com/181192/brasscribe/pull/65))
- **Engine:** Give a bass tab as MusicXML, PDF and MIDI ([#73](https://github.com/181192/brasscribe/pull/73))
- **Engine:** A cleaner bass tab that marks the notes to check ([#80](https://github.com/181192/brasscribe/pull/80))
- **Engine:** Bass tabs work in the Docker image ([#83](https://github.com/181192/brasscribe/pull/83))
- **Engine:** Write guitar as tablature, and one tab profile for every fretted instrument ([#106](https://github.com/181192/brasscribe/pull/106))
- **Engine:** Ukulele and mandolin tabs, from a song or the instrument alone ([#108](https://github.com/181192/brasscribe/pull/108))
- **Fretscribe:** Choose your instrument, tuning and what you read ([#91](https://github.com/181192/brasscribe/pull/91))
- **Fretscribe:** Send a recording to your computer and check the song ([#93](https://github.com/181192/brasscribe/pull/93))
- **Fretscribe:** Guitar, ukulele and mandolin, beside bass ([#113](https://github.com/181192/brasscribe/pull/113))
- **Fretscribe:** A tab as plain text and as playing instructions in words ([#114](https://github.com/181192/brasscribe/pull/114))
- **Fretscribe:** Read the tab, with the notes to check marked ([#104](https://github.com/181192/brasscribe/pull/104))
- **Fretscribe:** Practise with the recording under the tab, slowed down and bar by bar ([#117](https://github.com/181192/brasscribe/pull/117))
- Make a band draft on the phone when no computer is paired ([#60](https://github.com/181192/brasscribe/pull/60))

### Fixes

- **Engine:** Give MuScriptor the original audio again ([#46](https://github.com/181192/brasscribe/pull/46))
- **Bandroom for Mac:** Bundle a pixi the engine accepts ([#102](https://github.com/181192/brasscribe/pull/102))
- **Core:** Build the core artifacts from every workspace member ([#63](https://github.com/181192/brasscribe/pull/63))
- **Core:** Keep bass tab low on the neck when a line has stray high notes ([#78](https://github.com/181192/brasscribe/pull/78))
- **Engine:** Tabs of a lone instrument are written in 4/4, and open guitar chords can stay in open position ([#111](https://github.com/181192/brasscribe/pull/111))
- **Windows:** Keep the repeat band readable in dark themes ([#58](https://github.com/181192/brasscribe/pull/58))

<details><summary>Under the hood (13 changes: docs, tests, CI, build, refactoring)</summary>


- **Android:** Teach the engine client to read bass tabs ([#89](https://github.com/181192/brasscribe/pull/89))
- **Appearance:** Split the hidden palette into light and dark ([#32](https://github.com/181192/brasscribe/pull/32))
- **Core:** Keep instrument knowledge out of the shared modules ([#43](https://github.com/181192/brasscribe/pull/43))
- **Engine:** Let the bass tab option tests run without a built core ([#79](https://github.com/181192/brasscribe/pull/79))
- **Eval:** Gate Basic Pitch on the retuned recording ([#61](https://github.com/181192/brasscribe/pull/61))
- **QA:** Read the token file's own extension in the contrast check ([#42](https://github.com/181192/brasscribe/pull/42))
- **Scripts:** Find the squash-merged release commit when tagging ([#56](https://github.com/181192/brasscribe/pull/56))
- Bump actions/checkout from 4 to 7 ([#52](https://github.com/181192/brasscribe/pull/52))
- Bump github/codeql-action from 3 to 4 ([#53](https://github.com/181192/brasscribe/pull/53))
- Bump actions/configure-pages from 5 to 6 ([#55](https://github.com/181192/brasscribe/pull/55))
- Bump gradle/actions/dependency-submission from 4.4.3 to 6.3.0 ([#54](https://github.com/181192/brasscribe/pull/54))
- Bump android-actions/setup-android from 3.2.2 to 4.0.4 ([#51](https://github.com/181192/brasscribe/pull/51))
- Use documentation addresses in tests and the guide ([#57](https://github.com/181192/brasscribe/pull/57))

</details>

## 0.3.2 (2026-09-30)

### New features

- **Design:** A link-preview image for the repository ([#31](https://github.com/181192/brasscribe/pull/31))

### Fixes

- **Engine:** Patch vulnerable Python dependencies ([#17](https://github.com/181192/brasscribe/pull/17))
- **Engine:** Run Basic Pitch on macOS 27 ([#34](https://github.com/181192/brasscribe/pull/34))
- **Android:** Recording, playback, pairing and storage fixes ([#25](https://github.com/181192/brasscribe/pull/25))
- **iPhone, iPad and Mac:** Refuse broken scores, and keep playback, recording and pairing safe ([#27](https://github.com/181192/brasscribe/pull/27))
- **Bandroom for Mac:** Engine supervision, pairing, install and removal fixes ([#22](https://github.com/181192/brasscribe/pull/22))
- **Bandroom for Windows:** Keep working when Brasscribe answers with an error, and say what didn't work ([#21](https://github.com/181192/brasscribe/pull/21))
- **Core:** Stop the bindings, conformance and core-artifact checks passing on failures ([#19](https://github.com/181192/brasscribe/pull/19))
- **Core:** Refuse input that cannot be arranged instead of hanging or crashing ([#28](https://github.com/181192/brasscribe/pull/28))
- **Engine:** Stricter checks on job inputs, request origins and ids ([#26](https://github.com/181192/brasscribe/pull/26))
- **Engine:** Cancelling stops a running model, renames work on Windows, paired devices see no computer paths ([#30](https://github.com/181192/brasscribe/pull/30))
- **Engine:** Make stopping a model reliable ([#41](https://github.com/181192/brasscribe/pull/41))
- **Release:** Refuse a version that doesn't go up, push main and the tag atomically, and check the identity without naming any domain
- **Release:** Compare versions without GNU sort
- **Release:** Release through a pull request, generate the notes before changing anything, and check the identity and versions strictly
- **Release:** Tag what main released under any merge method, and refuse unknown arguments
- **Release:** Link each pull request once in the notes, and don't name bots as authors ([#44](https://github.com/181192/brasscribe/pull/44))
- **Site:** Link the release files CI makes, add Bandroom for Windows, and publish checksums
- **Studio:** Fix stale results, lost focus, stuck playback and silent failures ([#20](https://github.com/181192/brasscribe/pull/20))
- **Windows:** Give Play and Bandroom for Windows the release version
- **Windows:** Stay open through errors, follow audio devices and keep your files safe ([#24](https://github.com/181192/brasscribe/pull/24))
- **Windows:** Build Play for Windows again with the last ONNX Runtime that has DirectML ([#49](https://github.com/181192/brasscribe/pull/49))
- Music rules, benchmark gates, adapter downloads and conversion parity ([#23](https://github.com/181192/brasscribe/pull/23))

<details><summary>Under the hood (41 changes: docs, tests, CI, build, refactoring)</summary>


- **Core:** State the Rust version the core really needs ([#18](https://github.com/181192/brasscribe/pull/18))
- **Deps:** Bump zip from 2.4.2 to 8.6.0 in /core ([#3](https://github.com/181192/brasscribe/pull/3))
- **Deps:** Bump the minor-and-patch group across 2 directories with 3 updates ([#6](https://github.com/181192/brasscribe/pull/6))
- **Deps:** Bump com.google.android.apps.common.testing.accessibility.framework:accessibility-test-framework from 2.1 to 4.1.1 in /apps/android ([#7](https://github.com/181192/brasscribe/pull/7))
- **Release:** Release notes and changelog from the commits, and a script that cuts a release
- **Release:** Notes for exactly the tag's range, one run per tag, and public-safe changelog wording
- **Release:** List the Windows version files in the manual release steps, and say why the identity check uses the author
- **Security:** CodeQL for the code and workflows, dependency review on pull requests, and Dependabot
- **Security:** Analyse Kotlin from the Android debug build
- **Security:** Install the pinned Android NDK and CMake for the Kotlin analysis
- **Security:** On pull requests, analyse only the languages whose files changed
- **Security:** Scan the native audio code and inline scripts, add the Gradle dependency graph, a required-safe CodeQL result, and keep the signed APK a day
- **Windows:** Give the UI-thread stop test room for a slow CI runner
- Contributor guide, issue and pull request templates, security policy, and agent guidance
- Say how far the Windows apps are tested, and list the Windows downloads in the README
- Pin third-party actions to commit SHAs
- Say exactly when the security scans run, and fold unlisted commit types into the changelog
- Let the release read pull requests for its notes, and widen the security path filters to manifests and the generated Compose theme
- List Play for Windows as a preview download, and sort the changelog by app
- Dependabot for the core Android project, and release notes for pre-release tags
- Windows in the guide's install and computer sections, the core tool for every OS, and accurate contributor and agent guidance
- The CodeQL result needs a successful change detection, and the core Android graph uses the app's Gradle version
- Allow the AI co-author trailer, which is the disclosure the template asks for ([#1](https://github.com/181192/brasscribe/pull/1))
- Check a branch once, through its pull request, and run only the jobs whose parts changed
- Run on every pull request so the CI result is always reported ([#16](https://github.com/181192/brasscribe/pull/16))
- Bump the minor-and-patch group with 3 updates ([#8](https://github.com/181192/brasscribe/pull/8))
- Bump xunit.runner.visualstudio from 3.1.5 to 4.0.0 ([#9](https://github.com/181192/brasscribe/pull/9))
- Bump xunit.runner.visualstudio from 3.1.5 to 4.0.0 ([#14](https://github.com/181192/brasscribe/pull/14))
- Bump prefix-dev/setup-pixi from 0.8.1 to 0.10.2 in the minor-and-patch group ([#10](https://github.com/181192/brasscribe/pull/10))
- Bump actions/dependency-review-action from 4 to 5 ([#11](https://github.com/181192/brasscribe/pull/11))
- Bump actions/cache from 4 to 6 ([#12](https://github.com/181192/brasscribe/pull/12))
- Bump actions/upload-pages-artifact from 3 to 5 ([#13](https://github.com/181192/brasscribe/pull/13))
- Bump actions/setup-java from 4 to 6 ([#15](https://github.com/181192/brasscribe/pull/15))
- Only report dependency alerts for code that ships, and fewer, grouped update PRs ([#35](https://github.com/181192/brasscribe/pull/35))
- Pull request titles become the release notes ([#29](https://github.com/181192/brasscribe/pull/29))
- Promote the reference golden after the melody-exclusion change ([#33](https://github.com/181192/brasscribe/pull/33))
- Bump actions/upload-artifact from 4 to 7 ([#40](https://github.com/181192/brasscribe/pull/40))
- Bump actions/deploy-pages from 4 to 5 ([#38](https://github.com/181192/brasscribe/pull/38))
- Bump actions/setup-node from 4 to 7 ([#36](https://github.com/181192/brasscribe/pull/36))
- Bump dorny/paths-filter from 3.0.4 to 4.0.3 ([#37](https://github.com/181192/brasscribe/pull/37))
- Bump actions/setup-dotnet from 4 to 6 ([#39](https://github.com/181192/brasscribe/pull/39))

</details>

## 0.3.1 (2026-09-30)

<details><summary>Under the hood (8 changes: docs, tests, CI, build, refactoring)</summary>


- **iPhone, iPad and Mac:** Build only the Verovio slices a build needs; the release builds macOS alone
- **iPhone, iPad and Mac:** Keep the full Verovio build time in the make help
- **QA:** Expect the pink themes in the design tokens
- **Release:** Sign the Android APKs with the release key and allow starting a release by hand
- **Release:** Ship Bandroom for Mac and Windows, and re-sign the Mac apps ad hoc
- **Release:** Pass the secrets on to the Android build so the signing job gets the key
- Link to the latest release instead of naming a version
- Prepare the repository for public release

</details>

## 0.3.0 (2026-09-30)

### New features

- **Android:** Hidden Pink appearance, unlocked from About
- **Android:** Play Listen to this bar with the band SoundFont
- **iPhone, iPad and Mac:** Hidden Pink appearance, unlocked from About
- **iPhone, iPad and Mac:** Mac score window screenshots from the macOS VM, in English and Norwegian
- **iPhone, iPad and Mac:** Play trills with their written auxiliary, staccato at half value
- **Apps:** Pass the SwiftF0 confidence with the solo contour
- **Arranger:** Write the pop kit for a pop or rock take
- **Core:** Collision-aware quantization for the solo line
- **Core:** Pitch-change onsets from the SwiftF0 contour for the solo line
- **Design:** Add the hidden Pink palette to the tokens
- **Notation:** Write sustained two-note alternations as trills
- **Playback:** A percussion part's midi-program picks the pop kit on every player
- **Band sounds:** Fetch the trumpet vibrato sustains and concert percussion from VSCO 2 CE
- **Band sounds:** Solo cornet, trumpet, band kit, desk variants and steady loops
- **Band sounds:** Pin the sounds-2026.09.29 band pack
- **Band sounds:** Even velocity steps, pedal-note samples and slower pedal releases
- **Studio:** Hidden Pink appearance, unlocked from the lockup
- **Windows:** Music stand page model, layer rules and keys in Core
- **Windows:** Music stand in Play
- **Windows:** Appearance setting (Match system, Light, Dark)
- **Windows:** Ask what the player plays, and follow their part
- **Windows:** Trumpet in What do you play, tune from the core
- **Windows:** Refuse a solo take for the percussion seat, and say why
- **Windows:** Show empty parts as empty, not arranged
- **Windows:** Hidden Pink appearance, unlocked from About
- **Windows:** Boost a quiet recording to the band's level
- The trumpet part plays its own trumpet preset
- Hear a candidate pitch in Change note before saving

### Fixes

- **Android:** Make the bottom sheet's drag handle a 48 dp target
- **Android:** Keep a changed note's original pitch with the score
- **iPhone, iPad and Mac:** Credit the band sound sources in About
- **iPhone, iPad and Mac:** Keep a changed note's original pitch with the score
- **iPhone, iPad and Mac:** Readable selected note in the review list on iPad and Mac
- **iPhone, iPad and Mac:** Review actions follow the note at the accessibility text sizes
- **iPhone, iPad and Mac:** Level the band kit drum by drum and fit the band gain on arrangements
- **Bandroom for Mac:** Read the Hugging Face key off the main thread
- **Bandroom for Mac:** Close setup after re-entering the key when nothing is missing
- **Bandroom for Mac:** Say so when the Keychain prompt for the key goes unanswered
- **Core:** Direction offsets and review bracket numbers as the reference writes them
- **Core:** Compare pitches as music21 does when consolidating tuplets
- **Core:** Name split notes by their own plateau, dense grids only on evidence, faithful only
- **Core:** A short semitone into or off a held note is its bend, not a note
- **Engine:** Braille for measures longer than a braille line
- **Engine:** The rendered MP3 plays at the band's loudness under the apps' ceiling
- **MusicXML:** Number every tie the writers write
- **Engine:** Estimate a beat grid for takes with under two tracked beats
- **Play:** Pair alphaTab's ties and trills from the MusicXML
- **Playback:** A drier hall on Apple and level parity with the new band sounds
- **Playback:** Levels for the even velocity curve, and Apple seat trims
- **Playback:** Refit the arrangement level and band estimate on the golden without held notes
- **Quantization:** Read tuplets from runs of beats, robust to timing jitter
- **Quantization:** Tuplet runs need three beats; keep trills through app re-encodes
- **Band sounds:** Band kit bass drum level, the full-band phrase and pack tooling
- **Band sounds:** The band kit bass drum plays level with the MS Basic kick on every player
- **Band sounds:** Start the Bass Trombone's pp C3 where it speaks, pack sounds-2026.10.01
- **Studio:** The viewer's themed screenshots show Old Hundredth
- **Windows:** Music stand shows the music, takes taps on both pages
- **Windows:** Name the Play button by what it does
- **Windows:** Say the seat notice once and build the part menu as it opens
- **Windows:** Mockup tile words, one article in the notices, bass-clef key wording
- **Windows:** «Notert (F-nøkkel)» for the bass-clef toolbar label
- **Windows:** Pedals turn stand pages without showing the controls
- **Windows:** Tab or Space keep the stand's controls up until the next touch
- **Windows:** Keep a changed note's original pitch with the score
- Keep the fast-notes data out of data/eval, document the contour parameters

<details><summary>Under the hood (47 changes: docs, tests, CI, build, refactoring)</summary>


- **Android:** Pin the band estimate to the promoted fast-notes golden
- **Android:** Pass the first run's seat question in PlayFlowA11yTest
- **Android:** Confirm the immersive-mode prompt on pool emulators
- **Android:** Memory tests leave the library as they found it and skip on a locked screen
- **iPhone, iPad and Mac:** Screenshots.sh takes SIM_DEVICE for a dedicated simulator
- **iPhone, iPad and Mac:** Retake the iPhone and iPad site screenshots in English and Norwegian
- **iPhone, iPad and Mac:** Keep the earlier iPad review screenshots
- **iPhone, iPad and Mac:** Pin the golden recording target to the promoted fast-notes golden
- **Conformance:** The pop-kit arrangement has its own golden
- **Core:** Regenerate bindings for the trills options
- **Design:** Describe the hidden Pink appearance
- **Design:** Appearance setting spec (Match system, Light, Dark)
- **Design:** Name the contrast setting per platform
- **Developer tools:** The release process, bandroom-mac in the tiers, the VM's full-suite rule
- **Eval:** Measure where fast notes and two-note alternations are lost
- **Eval:** Fast-notes traps, real vibrato, separated and URMP sets, readability
- **Eval:** Freeze the new controls and separated clips into the fast-notes suite
- **Fast notes:** Follow-up results; gate trills in the fast-notes suite
- **Fast notes:** Note the on-device reference change from tuplet runs
- **Research:** Fast-notes results, gates and the bars for the owner to check
- **Research:** Status lines checked against main
- **Research:** The trumpet and fast-notes critiques, with the range and contour tests
- **Site:** Download 0.2.0, What do you play?, sound credits, correct pairing
- **Site:** Refresh the screenshots, with a Norwegian Mac shot, and the alt text follows
- **Site:** Transparent corners on the Mac window shots
- **Site:** Retake the iPad review and large-text shots
- **Band sounds:** Sources and licences of the band sounds, with the MS Basic notice
- **Band sounds:** Pin sounds-2026.09.30 and document the pack
- **Windows:** Read the fast-notes golden sibling through one constant
- **Windows:** Manual checklist for the Windows parity run
- Cover Bandroom for macOS in the check tiers
- Offline render harnesses for the Apple and alphaSynth band paths
- Freeze the fast-notes clips as a CI bench suite
- Check against the fast-notes golden and on-device reference siblings
- Promote the fast-notes golden and on-device reference
- READMEs and design docs checked against the code
- Refusal codes, device installs in the release, reviewer wording
- Mac install uses Open Anyway, since right-click › Open no longer bypasses Gatekeeper
- Music stand for Windows Play
- Appearance setting for Windows Play
- My instrument for Windows Play
- License the project under MIT OR Apache-2.0
- Rewrite the root README for a public audience, add engine and Bandroom Mac READMEs
- Rerun readability baseline, difficulty table and conformance totals on the current golden
- Tidy the music package metadata
- Point the on-device reference at its sibling for the tuplet-run change
- Merge the pop kit style signal into the sound follow-ups

</details>

## 0.2.0 (2026-09-29)

### New features

- **Android:** Shared output stage on alphaTab and sfizz, level-matched recording
- **Android:** One overflow entry on the score, the top bar's ⋯
- **Android:** Ask what the player plays and make it their part
- **Android:** Who played, who plays the tune and where each part came from
- **Android:** Add an emulator pool for parallel device tests
- **Android:** Trumpet in What do you play
- **iPhone, iPad and Mac:** Level-match the original recording to the band
- **iPhone, iPad and Mac:** Play score dynamics at alphaTab's velocities
- **iPhone, iPad and Mac:** Ask what the player plays, and use it as their part
- **iPhone, iPad and Mac:** Offer the tune only to seats the core says can carry it; screenshots
- **iPhone, iPad and Mac:** Trumpet in What do you play
- **Core:** Tune flag on each seat
- **Core:** Source footer on arranged parts
- **Core:** Write a faithful soloist's lead in the octave played
- **Core:** Trumpet in B♭ and a trumpet seat that takes the lead part
- **Design:** Light high-contrast palette
- **Engine:** Cache-Control on Studio files and band sounds
- **Engine:** Record GPU queue wait apart from stage run time
- **Engine:** Optional bounded stage parallelism
- **Engine:** Report the running build in /v1/health
- **Engine:** Give each refused job option a code the apps can word
- **Core:** Part_name_nb over UniFFI, the C ABI and .NET
- **Playback:** Play the recording at the band's loudness for the score
- **Band sounds:** One playback loudness target and shared output-stage vectors
- **Studio:** Keep Light or Dark under more contrast
- **Windows:** Shared output stage and level-matched recording

### Fixes

- **Engine:** Decode m4a/mp4/mov with ffmpeg for swift-f0, basic-pitch and separator
- **Android:** The score shows on first open, not only after the music stand
- **Android:** A phone on its side keeps the score in view
- **Android:** The job event stream outlasts a quiet stage
- **Android:** Bottom sheets open fully and keep clear of the navigation bar
- **Android:** A full disk ends a recording instead of crashing it
- **Android:** The score keeps 55 % of the height upright
- **Android:** No control is cut off above the score on a phone
- **Android:** Title Case for every instrument tile in English
- **Android:** Offer the tune only to seats the core says can carry it
- **Android:** Show empty parts as empty, not arranged
- **Android:** Don't offer the full band for whole-band recordings
- **Android:** Refuse a solo take for the percussion seat, and say why
- **Android:** Say «Demp stemmen min» for mute my part
- **Android:** Reach How should the score be? from any score
- **Android:** Say engine and core failures in plain en and nb
- **Android:** Don't blame the file when a computer's score can't be fetched
- **Android:** Stay on the note after Change note → Save
- **iPhone, iPad and Mac:** Keep the part view's header with the music, and align the tile words
- **iPhone, iPad and Mac:** The score keeps 55 % of an iPhone's height
- **iPhone, iPad and Mac:** Zooming a Mac window keeps it clear of the Dock
- **iPhone, iPad and Mac:** Keep the part's name on the phone at the largest text sizes
- **iPhone, iPad and Mac:** One window minimum on the Mac, content-sized sheets, actions under the content
- **iPhone, iPad and Mac:** Mark the in-process audio units sandbox-safe so a score opens on the Mac
- **iPhone, iPad and Mac:** Show empty parts as empty, not arranged
- **iPhone, iPad and Mac:** Don't offer the full band for whole-band recordings
- **iPhone, iPad and Mac:** Refuse a solo take for the percussion seat, and say why
- **iPhone, iPad and Mac:** Say «Demp stemmen min» for mute my part
- **iPhone, iPad and Mac:** Reach How should the score be? from any score
- **iPhone, iPad and Mac:** Keep each score's seat when the instrument changes in Settings
- **iPhone, iPad and Mac:** Say engine and core failures in plain en and nb
- **iPhone, iPad and Mac:** Give an unopened score the seat it was made for
- **iPhone, iPad and Mac:** Stay on the note after Change note → Save
- **iPhone, iPad and Mac:** Reachable controls over the score, one window minimum, sheets above the Dock
- **Apps:** Read a seat's default clef where the notes say how a part is written
- **Apps:** Send a trumpet job to an older engine as solo-cornet
- **Bandroom:** Plain Norwegian for the tools and separator lines
- **Bandroom:** Make the workspace swap's commit point the journal delete
- **Bandroom for Mac:** Update the installed engine workspace after an app update
- **Bandroom for Windows:** Replace the engine workspace atomically after an app update
- **Core:** Write a seat's mapped part in its own default clef
- **Core:** Refuse a solo take for the percussion seat
- **Core:** Label parts left without notes as empty, with no footer
- **Core:** Keep a soloist phrase's contour when it goes past the solo range
- **Core:** Split a soloist phrase past the range inside the solo range
- **Engine:** Event streams wait in their own threads
- **Engine:** GPU mutex that a crashed holder cannot leave locked
- **Engine:** Processes sharing the file-hash index no longer collide
- **Engine:** Give child processes /dev/null as stdin
- **Engine:** Check a band take's tune against the small band it is made for
- **Engine:** Put the refusal code first in a 422 body
- **Notation:** Publish the engraving as one snapshot the cursor reads safely
- **Play:** Recording fade cannot be restarted, app player checked for the stage
- **Studio:** Score viewer no longer overflows the stack on open
- **Studio:** Piano roll and beat summary without argument spreading
- **Studio:** Compare e2e runs on its own fixture pair of runs
- **Studio:** Explain a stage's GPU wait in the stage panel, not a hover title
- **Studio:** Name the empty part source
- **Studio:** Show the band a run is actually made for
- **Studio:** Announce a Trumpet part as a trumpet, not by its transposition
- **Windows:** Keep a marked note with the uncertain tune when linking the golden
- **Windows:** Offer the full band only where it is made
- **Windows:** Say «Demp stemmen min» for mute my part
- **Windows:** Say engine and core failures in plain en and nb
- **Windows:** Stay on the note after Change note → Save
- Rerun the Python conformance side when its sources changed

### Performance

- **Android:** Parse the composition once per score for humanization
- **Android:** Load the band SoundFont when it is needed and let it go with the score
- **Android:** Parse the score off the main thread
- **Android:** Recordings stream to disk, with a stated length limit
- **iPhone, iPad and Mac:** Open a score without blocking the main thread
- **Bandroom:** Verify model checksums off the main actor
- **Bandroom:** Check setup off the UI thread and remember when it is complete
- **Core:** Separation check without copies of the stems
- **Engine:** List jobs from cached manifest summaries
- **Core:** Move the stems into the band arrangement instead of cloning them
- **Core:** Borrow the caller's stems and contour in the band arrangement
- **Studio:** One synthesizer and SoundFont per page
- **Studio:** Keep the band SoundFont across visits
- **Windows:** Read the band SoundFont in the background, not before the first frame
- **Windows:** Stop a recording without blocking the UI thread
- **Windows:** Read the dev brass SoundFonts one at a time, in the background
- **Windows:** Read cached layer stems off the UI thread
- Build the UI tests on the host and split them over two VMs

<details><summary>Under the hood (45 changes: docs, tests, CI, build, refactoring)</summary>


- **Android:** Landscape screenshots with the controls group in the ⋯ sheet
- **Android:** What do you play? on the emulator, with screenshots
- **iPhone, iPad and Mac:** Audit macOS window and sheet sizing with an off-screen layout harness
- **iPhone, iPad and Mac:** Add install-mac target for a launchable ad-hoc Release
- **iPhone, iPad and Mac:** Check the sidebar relayout and the 900 x 600 minimum in the VM
- **iPhone, iPad and Mac:** Change note → Save stays on the note on iPhone
- **iPhone, iPad and Mac:** Read the stand's position as the Mac reports it, skip tooltips in the audit
- **iPhone, iPad and Mac:** Read the change-note card's words as label or value on macOS
- **Apps:** Pin the empty source, the default reading and «Demp» wording
- **Checks:** Compare only the Rust side of the reference cases in the fast tier
- **Checks:** Test against the current core and the branch's own files
- **Core:** Build from a fixed copy of the sources
- **Mac VM:** Keep the VM Dock's height fixed, document the UI test findings
- **Performance:** Probes for the performance audit
- **Research:** Trumpet as a soloist and a seat, with instrument facts from the core
- **Research:** Trumpet plan scoped to the soloist range and a trumpet seat
- **Research:** Trumpet plan with the soloist rule as built and the owner defaults
- **Research:** Trumpet plan with the step 2 and 3 review answers
- **Research:** Performance audit across engine, core, Studio and apps
- **Research:** Start-up per app, network and FFI payloads in the performance audit
- **Research:** Engine job list, GPU wait and stage parallelism results
- **Research:** Studio SoundFont before and after in the performance audit
- **Research:** App-side performance fixes and the Android memory measurement
- **Research:** User flow review from recording to my part
- **Site:** Link How it works from every page's menu
- **Band sounds:** Playback loudness target, per-app stages and measured levels
- **Studio:** Rebuild the static bundle
- **Tests:** Report golden tests as skipped when their data is missing
- **Windows:** Golden note count after the cornet-limit golden update
- **Windows:** Mark the three multi-second golden tests Category=Slow
- **Windows:** A Trumpet part plays the Solo Cornet's sound without a mapping
- Add worktree setup and a shared core artifact cache
- Add fast and affected-only tiers for the engine and the core
- Add check tiers per area and repeatable Apple unit-test targets
- Mark the slow Swift and JVM tests and enable the Gradle configuration cache
- Point each README at the test tiers
- Describe the verification tiers, worktree setup and measurements
- Run the macOS UI tests in a headless Tart VM
- Set the VM display mode, reach xcodegen over SSH, copy Xcode without a share
- Place the macOS VM UI tests in tier 3 of the verify guide
- Queue macOS VM runs on one lock and keep the full suite for releases
- Cover a changed note staying open, and remember it across launches
- Stop a VM test run when the host build fails
- Save the soloist golden next to the current one
- Promote the soloist golden

</details>

## 0.1.0 (2026-09-28)

### New features

- **Android:** Gradle project and Composition model with talking-score announcer
- **Android:** Engine companion client with golden fixture engine
- **Android:** On-device SwiftF0 pitch detection with ONNX Runtime
- **Android:** Brasscribe Play app with capture, transcription, review and score
- **Android:** Realistic tier loads installed SFZ instruments per part
- **Android:** Free-time announcements, live-engine checks, export tests
- **Android:** Basic Pitch on ONNX Runtime with upstream note decoding and parity tests
- **Android:** On-device Beat This! small with the log-mel frontend and minimal postprocessor
- **Android:** Rust core behind CoreBridge; braille, talking score and job options in the engine client
- **Android:** Offline solo with Basic Pitch confirmation and Beat This beats, arranged by the Rust core
- **Android:** Band SoundFont with one channel per part, humanized realistic tier, reference-exact offline solo
- **Android:** Live full-band engine run, braille export and per-part talking score checks
- **Android:** Assemble the reduced ONNX Runtime AAR, debug channel counts, keep the last on-device arrangement
- **Android:** Full screen for the music stand
- **Android:** Open a MusicXML file as a score
- **Android:** Restyle Play onto the Brasscribe design system
- **Android:** Second usability review: share or print scope, triage, "?" at spec size, both keys
- **Android:** Interim review UI, selection column and caret, nb compound breaks, radio column
- **Android:** Review by the engine's groups, readable score titles on Home
- **Android:** Stoppable listen-to-bar, connection status, pair once
- **Android:** Band sounds by default, one resolver for every part, no chopped notes
- **Android:** Say when the band sounds are missing, and fade out on stop and pause
- **Android:** **Breaking:** Remove the built-in reference demo
- **Android:** Offer the brass quartet as a third output
- **Android:** Music stand with pages, a hiding control layer and rotation that keeps playing
- **Android:** Appearance setting (Match system, Light, Dark)
- **Android:** Pedals turn pages without the controls; drop open-on-turn
- **iPhone, iPad and Mac:** Link the design system tokens, display face, mark and app icon
- **iPhone, iPad and Mac:** Norwegian for every new string, screenshot scenes for the review states
- **iPhone, iPad and Mac:** Review the engine's note groups, one item per group, with the group's bars on the staff
- **iPhone, iPad and Mac:** Readable score titles and rows, an iPhone review with Listen and Change note in view
- **iPhone, iPad and Mac:** Change note and Keep write to the Composition; Change note arranges the score again through the Rust core
- **iPhone, iPad and Mac:** Keychain credentials, pairing link and connection state machine
- **iPhone, iPad and Mac:** Stoppable Listen to this bar, connection status row and pair once
- **iPhone, iPad and Mac:** Say above the player when the band sounds are missing
- **iPhone, iPad and Mac:** **Breaking:** Remove the built-in reference demo
- **iPhone, iPad and Mac:** Offer the brass quartet as a third output
- **iPhone, iPad and Mac:** Bundle the phone band SoundFont on iOS
- **iPhone, iPad and Mac:** Band output stage with make-up gain and a soft limiter
- **iPhone, iPad and Mac:** The music stand on iPhone, iPad and Mac
- **iPhone, iPad and Mac:** Appearance setting, stand screenshots and stand polish
- **Bandroom:** MacOS menu-bar app that supervises the engine
- **Bandroom:** Bokmål copy deck, one primary per state, device in the Now line
- **Bandroom:** Brasscribe Bandroom for Windows, tray app with engine supervision
- **Bandroom:** Show the wrong-code lockout in Pair a phone on Windows
- **Bandroom:** Bundle the band SoundFont and serve it to Studio
- **Bandroom for Mac:** Add Remove Brasscribe from this Mac to the More menu
- **Bandroom for Mac:** Appearance setting (Match system, Light, Dark)
- **Bandroom for Windows:** Download the models, name what's missing, name shown to phones
- **Bandroom for Windows:** Appearance setting (Match system, Light, Dark)
- **Core:** Regenerate Swift, Kotlin and C bindings; platform tests for humanization and the talking score
- **Core:** Rust port of the symbolic pipeline with a conformance runner
- **Core:** UniFFI and C bindings with Swift, Android and .NET packages
- **Core:** Port beat cleanup, key plans, dynamics, rehearsal marks, energy gate and part splitting
- **Core:** Port humanization and the talking score
- **Core:** Difficulty modes, lineups, transposition and band MIDI mapping
- **Core:** Meter and bar phase for single-instrument beat tracks
- **Core:** Calibrated solo-note confidence and grouped review marks
- **Design:** Design tokens in DTCG format with contrast checks for every role
- **Design:** Brasscribe mark, wordmark, lockups and app icons for every platform
- **Design:** Generate Swift, Compose, WinUI and CSS themes from the tokens
- **Design:** Play and Studio mockups rendered from the generated tokens
- **Design:** Apply the usability review to the spec, tokens and mockups
- **Design:** Bandroom mockups, state icons and panel components
- **Windows:** Band arrangement with stems, humanization and talking score; vector tests
- **Engine:** Pair each device once with its own long-lived credential
- **Engine:** Name the engine after the computer's user-visible name
- **Engine:** Device presence, /v1/status, computer name and local-trust switch
- **Engine:** Name the paired device that started each job
- **Engine:** Report the wrong-code lockout in the pairing state
- **Core:** Stems-aware band arrangement, humanization and talking score
- **Core:** Arrangement options (lineup, difficulty, key, transposition) over UniFFI and the C ABI
- **Core:** Contour voicing confidence over UniFFI, the C ABI and .NET; regenerate bindings
- **Site:** Bilingual promotion page and user guide for GitHub Pages
- **Site:** Show real app screenshots in device and window frames
- **Site:** Use the restyled iPhone, iPad and macOS screenshots
- **Site:** Mac, iPad and iPhone group in the hero, slim iPhone frames below
- **Band sounds:** Fetch VSCO 2 CE, Iowa MIS, MS Basic and OpenAIR IRs with pinned checksums
- **Band sounds:** Brass-band instrument builder (SFZ + SF2), seating plan and offline room renderer
- **Band sounds:** Blind A/B generator and scorer, engine parity check, recording plan
- **Band sounds:** Specified deterministic humanization, VSCO sources for euphonium and B-flat bass, calibrated reverb level, room-matched baseline control
- **Band sounds:** Single band SoundFont with a preset per part, GM programs plus banks, MS Basic drum kit on bank 128
- **Band sounds:** One part-to-preset resolver for every lineup, plus test phrases and sound checks
- **Band sounds:** Equal-loudness presets, natural releases and real samples across each part's range
- **Band sounds:** Coverage and phrase checks that fail on GM fallback, range holes and chops
- **Band sounds:** Bundle the pinned band sound pack in every build
- **Studio:** Browser workbench with live stage graph, inspector, compare, benchmarks and score viewer
- **Studio:** Live-run e2e, parity latency, reflow and trend fixes
- **Studio:** Open .mxl, dark and high-contrast axe, re-run and compare e2e
- **Studio:** Norwegian and English UI, talking score, notation compare, run cleanup
- **Studio:** Restyle onto the Brasscribe design system
- **Studio:** Score side panel, blended score tints, screenshots in every theme
- **Studio:** Readable type scale, simpler views, 44 px targets
- **Studio:** Play the band sounds with one channel and preset per part
- **Studio:** Appearance setting (Match system, Light, Dark)
- **Windows:** Play core with Composition model and companion engine client
- **Windows:** Talking-score announcer in English and bokmål
- **Windows:** Talking score from MusicXML, score navigator and core bridge
- **Windows:** AlphaTab playback, rendering and uncertainty styling
- **Windows:** SwiftF0 on ONNX Runtime, capture contracts and exports
- **Windows:** View models for import, transcription, score, player and export
- **Windows:** WASAPI capture with per-app process loopback, Media Foundation decode
- **Windows:** Score view with UI Automation peer for Narrator and NVDA
- **Windows:** Score geometry for overlays and native core bridge on the shipped C ABI
- **Windows:** WinUI 3 app shell, screens, dialogs and bokmål/English resources
- **Windows:** Band SoundFont with one channel per part and balance
- **Windows:** Braille export and lineup, difficulty and key through the engine
- **Windows:** Switch between the score and the original, synced video with picture-in-picture
- **Windows:** Run on the native Rust core by default
- **Windows:** Restyle Brasscribe Play onto the design system
- **Windows:** Review triage, Change note and the key for your instrument
- **Windows:** Review by group, score titles and the selected note
- **Windows:** Stoppable Listen to this bar, connection status and pair once
- **Windows:** Every part resolves to its band preset, with a release tail, stop fade and headroom
- **Windows:** Say above the player when the band sounds are missing
- **Windows:** Offer a brass quartet as the third output option
- Add capture CLI, model adapters, and ChoraleBricks eval harness
- Add beat, separation and tagging adapters; record first benchmark
- Add Slakh trumpet-lead song benchmark, pipeline B, notation-tolerance metrics
- Add note-level consensus engine; fix Slakh bass octave in reference
- Add beat-grid quantizer and notation-level rhythm benchmark
- Add MusicXML export and draft lead-sheet tool; Mega-53 adapter env
- Add URMP brass benchmark and metrical-level selection
- Add brass-band instrument model with range validation; record melody extraction results
- Ps13 pitch spelling with key estimation, gap filling, confidence-flagged melody line
- Canonical score model, minimal deterministic arranger, transposing band export with round-trip test
- Harmony reduction and end-to-end song arrangement; first reference brass-band draft
- Write instrument-sound ids, MuseScore round-trip gate, safer tick origin and key in composition
- Layered solo-with-band arrangement for full brass band with percussion
- SwiftF0 adapter and three-way solo vote; SwiftF0-spine rule for solo lines
- Reproducible song pipeline with Mega-53 adapter; align docs with solo-vote findings
- ScoreKit for the Apple app: Composition, MusicXML parser, talking score, MIDI
- TranscriptionKit with companion engine client and fixture service
- PlaybackKit with sectioned samplers, seating, speed, loop, metronome, count-in
- Native SVG renderer for Verovio output with element frames and highlights
- NotationKit wraps the Verovio framework with part filtering, concert pitch and timemap cursor
- Brasscribe Play SwiftUI app for macOS, iOS and iPadOS
- Tempo changes, dynamics, rehearsal marks and free-time regions from the re-saved golden score
- Norwegian (bokmål) and English string catalogs; engrave once the view width is known
- Configurable data/adapter paths, render-free arrange runs and a solo arranger
- Engine service with job DAG, artifact cache, manifests and CLI
- Benchmark suites with a baseline gate, and Studio inspection endpoints
- Free-time regions, performed duration and articulations in Composition
- Written durations and staccato from performed lengths and SwiftF0 contours
- Free-time detection and proportional ad lib. notation
- Adapters run in their uv project or the pixi environment; SwiftF0 contour entry
- Contour stage, duration/free-time/readability suites and Linux CI
- Beat-showing rhythm spelling, plain written spellings, shape-encoded uncertainty
- Individual parts, energy gate for layer notes, part-writing durations
- Beat-track cleanup for missed and inserted beats; bar phase from downbeat labels
- Key changes and modes per passage
- Separation-failure check for the solo stem
- Dynamics per layer from loudness
- Gated beat cleanup, rehearsal marks, part rendering style
- Cross-platform adapter runner
- CI gates chorale suites on pinned annotations and committed model outputs
- Difficulty modes, minimal lineup, transposition, soprano doubling, figuration
- DELETE /v1/runs/{id} removes a finished run and keeps the cache
- Braille music (BRF) and talking-score exports, arrangement options on jobs
- Arrange on device with the Rust core; companion braille, talking-score and arrangement options
- Realistic brass-band tier per part with seating and mix gain; contrast fixes from the iPad audit
- Band SoundFont MIDI setup in MusicXML; transposed bass lines split where too wide
- SwiftF0 Core ML and static ONNX conversion with parity report
- Basic Pitch parity for Core ML, TFLite and ONNX exports vs TensorFlow
- Beat This! ONNX and Core ML conversion with beat parity report
- HT-Demucs ONNX and Core ML core with separator parity report
- BS-RoFormer core export (ONNX fp32/fp16, Core ML fp16) with SW parity report
- Mega-53 ONNX fp32 and Core ML fp16 parity report
- MuScriptor ONNX prefill and decode-with-past graphs with token parity
- OnDeviceKit runs SwiftF0, Basic Pitch and Beat This! with Core ML
- Offline solo transcription on iPhone and iPad
- Send lineup and key to the engine, show the key picker, route solos to the device
- Play the band SoundFont, one preset per part with channel_gain_db
- Convolution reverb with the OpenAIR central-hall IR, calibrated to +4.5 dB wet-to-direct
- Picture in picture for the synced video on iOS, iPadOS and macOS
- Solo profile uses the layered arranger, as the Play apps do on device
- Flexible-length Beat This small0 Core ML build
- SwiftF0 mixed-precision build with an fp16 Neural Engine trunk
- MuScriptor static KV cache for Core ML and the CoreML EP
- Meter and bar phase for single-instrument beat tracks
- Discover the engine on the LAN over Bonjour/mDNS
- Rename scores and correct note pitch/duration on all three apps
- Recent scores, score options and evidence-based note review on all apps
- Lightweight conformance summary and a background conformance run
- Calibrated solo-note confidence and grouped review marks
- Arrange for a brass quartet in the Python reference
- Benchmark the quartet against the ChoraleBricks voices
- Port the quartet arrangement to the Rust core
- Re-arrange a composition for any lineup through the FFI
- Offer the quartet lineup in the engine and Studio
- Seats, the seat-to-part table and part sources
- Benchmark the solo path per brass instrument and seat voices
- Write a solo take for the player's seat
- Measure the "?" rate on low brass and test a register recalibration
- Port the seat's solo take to Rust, and put the tune on the seat's part
- Seat, reads and lead over the FFI, the engine API and Studio

### Fixes

- **Android:** Lint-clean Compose state, per-API foreground service type, faster resampler
- **Android:** 16 KB page-size alignment for the 64-bit native libraries
- **Android:** Score follows the theme so it reads in dark mode
- **Android:** Say why offline transcription is unavailable for the sample
- **Android:** Reach LAN engines over Wi-Fi when mobile data is the default network
- **Android:** Part chip counts follow the review groups; retake screenshots
- **Android:** Lead line says where to start when most places are very unsure; drop "(draft)" from Home titles; cut the bar snippet below the staff so alphaTab's credit stays in About; only the engine's grouped parts have places to check
- **Android:** Cut the review snippet above alphaTab's credit line; test Home's count against the golden; retake the review screenshots
- **Android:** Status row layout, tablet wording, reconnect on emulators
- **Android:** Fade out on Stop, quiet retry after giving up, README
- **Android:** Space toggles Listen, nb stem-separation step, screenshots
- **Android:** Status row in Apple's form, nb tech-details label
- **Android:** Put docked actions on a band with a hairline
- **Android:** Point the tech details at Brasscribe Bandroom
- **Android:** Stand pages start with the title, Turn the music joins the layer
- **Android:** Two-page spread on a tablet on its side, no alphaTab credit, no title after page 1
- **Android:** One full-width stand page on tablets, bars never squeezed, no half title or credit
- **Android:** Stream uploads and take a video's sound out on the phone
- **Android:** An upload without a file stays empty; SoundFont check per score
- **iPhone, iPad and Mac:** Open a window and route shortcuts so macOS UI tests pass
- **iPhone, iPad and Mac:** Crash when picking a single part in the score
- **iPhone, iPad and Mac:** Card shadows off the text, a wrapping Check them line, opaque phone player
- **iPhone, iPad and Mac:** IPad keeps the score clear of the sidebar, stacks the score toolbar at the largest text sizes
- **iPhone, iPad and Mac:** Window keeps its size beside wrapping notices, Mac export sheet without a title bar, screenshot script
- **iPhone, iPad and Mac:** "Hear the recording" chip on iPhone, the Hear control only where it fits, Dynamic Type for the "?" legend mark
- **iPhone, iPad and Mac:** Review places only in the parts the arranger marked, so Home and Review both count 83; lead line says where to start when most places are very unsure
- **iPhone, iPad and Mac:** Beat This small0 download sizes
- **iPhone, iPad and Mac:** No pairing prompt for Brasscribe on the same Mac; refresh iPad and Mac screenshots
- **iPhone, iPad and Mac:** Band sounds by default, one resolved preset per part, no streaming dropouts
- **iPhone, iPad and Mac:** Find the repository by sounds/band.py, and check unisons by relative level
- **iPhone, iPad and Mac:** Load samples into memory only where the SDK has the switch
- **iPhone, iPad and Mac:** Dock Show the score on an opaque band
- **iPhone, iPad and Mac:** Stand fits every part, large text and pedals
- **iPhone, iPad and Mac:** Mac windows stay on their screen; output stage checked on the phone SoundFont
- **Apps:** Sync Android and Windows engine contracts with the current spec
- **Apps:** Model the seat, reads and lead job fields in the engine clients
- **Bandroom:** One address per line in tech details, reuse ports in TIME_WAIT
- **Bandroom:** Short bokmål name for separating the instruments
- **Bandroom:** Project file loads, stage names match Play, Stop names the phone
- **Bandroom:** Flyout fits its content, problem title in the status, list in a card
- **Bandroom:** Tray icon on a hidden tool window, Enter only opens the flyout
- **Bandroom:** Bundle every pyproject.toml; recopy the workspace when the app's sources change
- **Bandroom for Mac:** Download the models, name what is missing, find a hidden menu-bar mark
- **Bandroom for Mac:** Name the settings pickers once, by their section
- **Build:** Change trigger branch to main
- **Core:** Reproduce NumPy's argsort order in pitch spelling
- **Design:** 20% cursor tint as specified, DTCG colour objects for shadows, counts
- **Engine:** Keep the rotating token valid until its replacement is used
- **Engine:** Transcode beat_this/muscriptor input to wav via ffmpeg
- **Site:** Float guide phone shots beside the text and keep nb percentages together
- **Site:** Qualify record-what's-playing by platform and match copy to the shots
- **Site:** Correct the research article after fact-check
- **Band sounds:** Gate-ratio articulation, even-sized sm24 for TinySoundFont, section balance, per-part transposition
- **Band sounds:** Level sustain samples on what short notes hear
- **Band sounds:** Level the drum kit against the levelled brass presets
- **Studio:** Plain fetch-error states, Run conformance, review polish
- **Studio:** Parity names failing formats and says where each model is ready
- **Studio:** Read the brass-band profile's lineups as a plain list in nb
- **Studio:** Use the layered-preset gains with the phone band SoundFont
- **Windows:** Thread-safe synth, brass SoundFont routing, back after a failed run
- **Windows:** Clean MIDI export, bounded engine connect, shorter durations
- **Windows:** Title-bar clicks, glyph sizes, single-key review keys, re-arranged scores
- **Windows:** Lead line says where to start when most places are very unsure; Home's count matches Review
- **Windows:** English recording titles use invariant month names
- **Windows:** Function bindings on Visibility return Visibility
- **Windows:** Log unhandled exceptions and show them when the smoke test sees the app exit
- **Windows:** Add the Back-key accelerator in code so the main window loads
- **Windows:** Keep no frame back stack instead of clearing it after each navigation
- **Windows:** Create the selection canvas before the score surface adds it
- **Windows:** Score screen passes the Axe.Windows rules
- **Windows:** Connection status row as a bordered row like the other Play apps
- **Windows:** Leave out a null review list when writing a Composition
- Unescape ampersands in adapter scripts
- Tolerate MuseScore CLI shutdown crash when output was written
- Launch on iOS, open phones on the player's part, engrave pages progressively
- 44 pt hit targets and unclipped position text from the iOS accessibility audit
- Keep free-region notes and their fermata inside the region; contour in the song pipeline
- Deterministic MusicXML part ids so unchanged arrangements hit the cache
- GPU mutex for heavy adapters in live suites; stricter stage and reference file routes
- Band reading ranges and continuous bass octaves
- Batch MuseScore conversions into one launch and serialise instances
- Basic Pitch uses its ONNX model outside macOS
- Engine arrange stage matches the v2 layered song output
- No fragment values where a triplet and a 16th grid meet in one beat
- Keep MuseScore's playable ranges for range checks; place notes by reading range
- Arrange the small band on device instead of sending lineup/key the engine rejects; emit SSE events on their data line
- Stable ids for per-drum percussion instruments
- Include the id canonicaliser in the arrange stage cache key
- Arrow keys move by bar even when the score's scroll view has focus
- BRF lines never exceed 40 cells
- Infer the solo meter on the final beat grid, never merge notes, keep bars on weak evidence
- Treat the re-arrange transposition as the total from the recording
- Compare waveforms in the midi-bank test, and resolve part names in the offline renderer
- Keep the Solo Cornet inside its playable range
- Credit the arrangement to Brasscribe and drop the repeated subtitle

### Performance

- **Windows:** Lay out and draw notation off the UI thread, page by page

<details><summary>Under the hood (145 changes: docs, tests, CI, build, refactoring)</summary>


- **Accessibility:** WCAG 2.2 AA and EN 301 549 checklist for Play and Studio
- **Accessibility:** Talking-score announcement spec with conformance vectors
- **Accessibility:** Uncertainty palette, shape encoding, contrast, motion and zoom rules
- **Accessibility:** Record that the boxed ? survives MuseScore re-export
- **Android:** Instrumented accessibility flow and verify-command wiring
- **Android:** README, per-ABI release APKs and emulator screenshots
- **Android:** Pass the converted-model and data paths to pitch tests
- **Android:** Offline solo on the JVM against the engine's solo profile
- **Android:** Notation overlay for the uncertainty marks and the ad-lib tint
- **Android:** Share or print scope
- **Android:** Review triage and the bar on a staff
- **Android:** Keys, large text, status snackbar, nb part names, settings and help
- **Android:** Tests for my part and conductor's score
- **Android:** Lint and fixture test for part files
- **Android:** The core keeps the review groups; drop the JSON workaround
- **Android:** Let syncOpenApi run in the same build as the tests
- **Android:** Retake the Choose output screenshots with the quartet
- **Android:** A video larger than the heap imports and uploads; SoundFont bytes released
- **Android:** Page keys leave the hide timer alone; WAV, too-large and non-AAC coverage
- **iPhone, iPad and Mac:** Screenshots of every key screen, light and dark, on iPhone, iPad and Mac
- **iPhone, iPad and Mac:** Screenshots for the third review: populated Home, the new review, Norwegian main screens
- **iPhone, iPad and Mac:** Screenshots of Review listening/stopped and Home with the connection row
- **iPhone, iPad and Mac:** Retake the output and library screenshots with the quartet
- **iPhone, iPad and Mac:** Add Norwegian iPhone and iPad shots and large-text review from Old Hundredth
- **iPhone, iPad and Mac:** Give the reason iOS bundles the phone SoundFont correctly
- **iPhone, iPad and Mac:** Keep macOS UI tests inside the app window and out of make test
- **iPhone, iPad and Mac:** MacOS UI tests in their own scheme
- **Bandroom:** Windows build, how it runs and MSIX packaging
- **Bandroom:** Check that the engine's whole process tree ends with Bandroom
- **Bandroom:** What CI checks, and that the MSIX build is not yet exercised
- **Bandroom:** Bundle the phone band SoundFont for Studio playback
- **Bandroom:** Model downloads, hidden menu-bar mark and the name shown to phones
- **Bandroom for Mac:** Ship pinned MSST code for Mega-53, bokmål for the new strings
- **Bandroom for Windows:** Use Old Hundredth as the sample job title
- **CI:** Add build/test workflows and semver-tag release pipeline
- **CI:** Run Apple tests on the newest iPhone Pro simulator with Xcode 26.6 selected
- **Conformance:** Meter reference cases use the module numpy; regenerate bindings
- **Core:** Unit fixtures from the Python reference for spelling, quantize, argsort and durations
- **Core:** Free-time and duration fixtures, composition read-back checks, options in the C ABI
- **Core:** Composition dynamics and sections
- **Core:** Regenerate duration fixtures from the current reference
- **Design:** Design system, brand and voice guide, per-app implementation checklist
- **Design:** Brasscribe Bandroom spec for running the engine in the background
- **Design:** Complete the Bandroom copy deck and mark unverified platform facts
- **Design:** Bandroom passes the computer name through BRASSCRIBE_COMPUTER_NAME
- **Design:** Bandroom's engine assumptions include the admin token and /v1/status
- **Design:** Mockups for the instrument question, settings row and part source labels
- **Design:** Mark the current note in the review mockup with a tint column and caret
- **Design:** Music stand spec, mockups and platform plan
- **Design:** Apply the music stand review
- **Design:** Appearance setting spec (Match system, Light, Dark)
- **Design:** Name the contrast setting per platform
- **Research:** Pairing once per device, and reaching the engine from outside
- **Research:** Name changes by what they do; rotation grace, tailnet and Windows migration notes
- **QA:** MusicXML readability heuristics with CI gate
- **QA:** Report accidental density and mixed sharp/flat bars
- **QA:** Colour tokens with WCAG contrast and CVD check
- **QA:** Screen-reader and keyboard acceptance scripts for Play and Studio
- **QA:** Readability review of the reference golden output
- **QA:** Tighten horn range wording
- **QA:** Make the talking-score grammar produce every vector; add readability baseline
- **QA:** Count a "?" words direction at a note's onset as uncertainty shape encoding
- **Research:** Overlapping instruments and in-between tones
- **Site:** Explain the transcription pipeline and design choices
- **Site:** Refresh screenshots with Norwegian iPhone shots and the 83-place review; alt text follows
- **Site:** Regenerate the Apple screenshots and site shots from Old Hundredth
- **Site:** Call the small band «Lite band» in the nb pages
- **Site:** Show the Norwegian computer name in the nb guide
- **Site:** Add a research article on how Brasscribe works
- **Site:** Add the Norwegian research article and home-page teasers
- **Site:** Correct the review threshold and the spelling dataset on the home pages
- **Band sounds:** Pass the Composition in the A/B render command
- **Band sounds:** Band SoundFont alphaTab checks follow the banked golden score; drums measured where they enter
- **Studio:** Refresh screenshots from the e2e run
- **Studio:** Regenerate API types from the engine's openapi.json
- **Studio:** No MuseScore launches in the default e2e run
- **Studio:** Refresh screenshots from the e2e run
- **Studio:** Regenerate API types for evidence and run-edit endpoints
- **Windows:** Type-check the WinUI app's C# off Windows
- **Windows:** Build, test and Axe.Windows scan of Brasscribe Play on windows-latest
- **Windows:** Design system theme, overlay primitives, review and library view models
- **Windows:** Fluent shell, the design screens and copy
- **Windows:** Score titles, very unsure first, keep the rest of the bar
- **Windows:** Print the app's crash log when a step fails
- **Windows:** Show Old Hundredth in the preview scenes and screenshots
- Add model research reports and architecture summary
- Verify eval dataset and checkpoints, add recognition/embedding picks
- Record architecture decision from benchmark evidence
- Record reference performance setup from live video
- Add build plan for the Studio workbench and Play musician apps
- Revise app plan for native per-platform apps and non-commercial licensing; add external comparison
- Confirm app names and Linux coverage via Studio
- Turn capture into a Swift package with a reusable process-tap recorder
- App unit tests, UI test that plays a bar of reference, and accessibility audit
- WKWebView side of the notation spike, hosted in the macOS app
- Pixi workspace for the engine and every model adapter
- Free-time benchmark and composition diff
- Correct amendment history of the universal design regulation
- Linux-aarch64 platform, conda-forge torchaudio/torchvision and a Linux Docker image
- Re-save reference golden output after free-time, duration and readability changes
- DeleteRun path-traversal check accepts router rejection
- Check the re-saved golden rewrites byte-identical; keep the legacy-format check on the previous golden
- Lower URMP uncomfortable-note baseline to the measured 1.0
- Arrangement options in composition.json and the difficulty modes; round trip uses recorded options
- Run package tests on the iOS simulator; fixture artifact checks follow the golden files
- Notation spike results, app README and screenshots
- Companion client against a running engine; skip the engine's audio render
- Video import extracts audio and keeps the picture
- IPad screenshot with the synced video inset
- Merge master
- Conversion README with method, results and blockers; fix >2 GB ONNX export
- Record free-time, duration, bar-line, difficulty, readability, conformance and sound results
- Sound, room, offline solo and video notes in the Apple README
- Revert "Merge solo meter inference and bar-phase tracking"
- Reapply "Merge solo meter inference and bar-phase tracking"
- Document how to build and run every component
- Ignore SwiftPM's local Xcode state in core/swift
- Usability review of the design mockups for non-technical players
- Restyle in progress
- Restyle screens onto the design system
- Second usability review on restyled Android and Studio screens
- Fix failing workflows and split checks from release builds
- Review triage, bar on a staff, change note, key labels, nb part names
- Studio error states
- Studio usability and accessibility review
- Correct the registry path finding in the Studio review
- Third usability review on Android
- Third usability review, Apple section
- Re-save reference golden output with calibrated confidence
- Third usability review, Studio section and remaining P1s
- Review layout for the third usability review
- Final usability pass, all P1s closed
- Plan a brass quartet (kvartett) output option
- Add quartet share labels, accessible disabled card and sound-branch conflict to kvartett plan
- Let lineups carry their lead, bass and second-bass roles
- Band sound coverage, chop diagnosis, balance and remaining gaps
- Release builds fetch the pinned band sounds and fail without them
- Plan for asking what the player plays and writing for it
- Measurement scripts, URMP cross-check and review fixes for the instrument plan
- List the quartet lineup and arrange_musicxml_with in the READMEs
- Add the Old Hundredth screenshot fixture, arranged by the core
- Use Old Hundredth as the example title and drop the demo from design, QA and site
- Re-save the reference golden output with the cornet's playable top
- Run only fast Linux checks on push; platform builds on release or by hand
- A release tag runs the checks once, inside the release

</details>

