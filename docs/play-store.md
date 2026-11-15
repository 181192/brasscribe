# Google Play: the Console answers, drafted

A draft of every answer the Play Console asks for, for **Brasscribe** (`app.kalli.brasscribe`) and **Fretscribe**
(`app.kalli.fretscribe`), for the owner to read before anything is submitted. Both apps go to the **internal
testing** track only (docs/shared/dev/release.md, Google Play). Every point marked **SJEKK** is a doubt to settle
first. Nothing here has been entered in the Console.

The answers come from the code and docs as they are when this was written. Where they rest on code, the file is
named, so a change there means the answer must be checked again. The ids `app.kalli.*` hold once the release that
moves the apps to them is out; the bundles of earlier releases are `no.kalli.*` and cannot go to Play.

## Store listing

Play's limits: app name at most 30 characters, short description at most 80, full description at most 4,000.
No emoji, no words in capitals for effect, and no claims about rank, price or awards. The counts below were
measured with `python3 -c 'print(len("…"))'`. Languages: English (United States) `en-US` is the default, and
Norwegian is `no-NO`, Play's code for Norwegian. The release notes use the same codes (`play-notes.py`).

### Brasscribe

| Field | en-US | no-NO |
|---|---|---|
| App name | Brasscribe (10) | Brasscribe (10) |
| Short description | Record your band, and get a part for every player to read and practise. (71) | Ta opp bandet, og få en stemme til hver musiker å lese og øve på. (65) |

Full description, en-US (1,441 characters):

> Record a rehearsal or open a recording, and Brasscribe writes down a part for every player in the band.
>
> A part for every player. Full brass band, a small band or a quartet. Each part in its range, written for B flat or E flat as the player reads it.
>
> A ? where it is not sure. A note Brasscribe was not sure of gets a ?. You hear that bar, keep the note or fix it, a semitone or an octave at a time, and go on to the next.
>
> Sheet music from a picture. Take a photo of a printed page, or open a picture or a PDF, and it becomes a score you can play from.
>
> The band to practise with. The score plays back with band sounds. Mute your own part, slow it down, repeat the hard bars, with a count-in and a metronome.
>
> Your part on the stand. Your own part fills the screen, with page turns from a pedal. Print it, or share the score as PDF, MusicXML or MIDI.
>
> Readable and audible. Large text, dark mode, a talking score that reads the music aloud, and braille music for those who use it.
>
> A solo is written on the phone. For a whole band, and for printed music, Brasscribe sends the recording or the pages to Bandroom, a free app for your own Mac or Windows PC on the same network. Your music goes only to your own computer: none of it is sent to us or to anyone else. When it is set up, Bandroom downloads its listening models from the internet; no music goes with that.
>
> Brasscribe is a free, non-commercial project, with no ads and no account.

Full description, no-NO (1,477 characters):

> Ta opp en øvelse eller åpne et opptak, så skriver Brasscribe ned en stemme til hver musiker i bandet.
>
> En stemme til hver musiker. Fullt brassband, et lite band eller en kvartett. Hver stemme i sitt register, skrevet i B eller Ess slik musikeren leser den.
>
> Et ? der den er usikker. En tone Brasscribe var usikker på, får et ?. Du hører den takten, beholder tonen eller retter den, et halvtonetrinn eller en oktav om gangen, og går videre til neste.
>
> Noter fra et bilde. Ta et bilde av et trykt notear, eller åpne et bilde eller en PDF, så blir det et partitur du kan spille fra.
>
> Et band å øve med. Partituret spilles av med bandlyder. Demp din egen stemme, sett ned tempoet, gjenta de vanskelige taktene, med inntelling og metronom.
>
> Din stemme på notestativet. Din egen stemme fyller skjermen, og du blar med en pedal. Skriv den ut, eller del partituret som PDF, MusicXML eller MIDI.
>
> Lett å lese og høre. Stor tekst, mørk modus, et partitur som leser musikken høyt, og punktskrift for dem som bruker det.
>
> En solo skrives på telefonen. For et helt band, og for trykte noter, sender Brasscribe opptaket eller sidene til Bandroom, en gratis app til din egen Mac eller Windows-PC på samme nettverk. Musikken din går bare til din egen datamaskin: ingenting av den sendes til oss eller noen andre. Når Bandroom settes opp, laster den ned lyttemodellene sine fra internett; ingen musikk følger med.
>
> Brasscribe er et gratis, ikke-kommersielt prosjekt, uten reklame og uten konto.

### Fretscribe

| Field | en-US | no-NO |
|---|---|---|
| App name | Fretscribe (10) | Fretscribe (10) |
| Short description | Play a riff or open a recording, and get tab for your instrument and tuning. (76) | Spill et riff eller åpne et opptak, og få tab for instrumentet og stemmingen. (77) |

Full description, en-US (1,320 characters):

> Play a riff or open a recording, and Fretscribe writes it down as tab for your instrument and your tuning.
>
> Tab for your instrument. Guitar, bass, ukulele or mandolin, with the strings you have, the tuning you play in and a capo.
>
> A look at what it heard, and a way to put it right. It shows the tuning, the key and the tempo it heard, and if one of them is off, you put it right and the tab is written again.
>
> A ? where it is not sure. Choose a note with a ? and it plays that bar slowly, so you can hear for yourself. Fix a note by choosing another string and fret, or mark it as a ghost note.
>
> Hear the tab. Play the recording, the tab's own notes, or both, with a count-in and a metronome.
>
> Practise. Repeat the hard bars, slower if you like, and let the speed trainer bring them up to tempo a little faster each time through.
>
> Open or record. Open a recording you have, play into the microphone, or record what another app on the phone is playing.
>
> Fretscribe writes the tab on Bandroom, a free app for your own Mac or Windows PC on the same network. Your music goes only to your own computer: none of it is sent to us or to anyone else. When it is set up, Bandroom downloads its listening models from the internet; no music goes with that.
>
> Fretscribe is a free, non-commercial project, with no ads and no account.

Full description, no-NO (1,293 characters):

> Spill et riff eller åpne et opptak, så skriver Fretscribe det ned som tab for instrumentet og stemmingen din.
>
> Tab for instrumentet ditt. Gitar, bass, ukulele eller mandolin, med strengene du har, stemmingen du spiller i og en capo.
>
> Se hva den hørte, og rett det. Den viser stemmingen, tonearten og tempoet den hørte, og er noe av det feil, retter du det, og tabben skrives på nytt.
>
> Et ? der den er usikker. Velg en tone med ?, så spiller den takten sakte, så du kan høre selv. Rett en tone ved å velge en annen streng og et annet bånd, eller merk den som dempet note.
>
> Hør tabben. Spill opptaket, tabbens egne toner eller begge, med inntelling og metronom.
>
> Øv. Gjenta de vanskelige taktene, saktere om du vil, og la tempotreneren øke tempoet litt for hver runde til du er oppe i tempo.
>
> Åpne eller ta opp. Åpne et opptak du har, spill inn i mikrofonen, eller ta opp det en annen app på telefonen spiller.
>
> Fretscribe skriver tabben på Bandroom, en gratis app til din egen Mac eller Windows-PC på samme nettverk. Musikken din går bare til din egen datamaskin: ingenting av den sendes til oss eller noen andre. Når Bandroom settes opp, laster den ned lyttemodellene sine fra internett; ingen musikk følger med.
>
> Fretscribe er et gratis, ikke-kommersielt prosjekt, uten reklame og uten konto.

### Contact and links (both apps)

| Field | Answer |
|---|---|
| E-mail | `<contact e-mail>` (placeholder: Play shows it publicly) |
| Website | `https://scribe.kalli.app/brasscribe/` and `https://scribe.kalli.app/fretscribe/` (both answer) |
| Phone | none |
| Privacy policy URL | `https://scribe.kalli.app/privacy/`. **SJEKK** that the page is live before anything is entered: it is being made separately, and Play refuses a listing whose policy does not answer. It should say exactly what Data safety says below: the music goes only to the player's own computer; Bandroom downloads its listening models (and the printed-music reader's files) from the internet when it is set up, with none of the player's music; what Android's backup keeps; and no account, no ads. |

### Pictures

Made by `scripts/play-store-images.py` (its first lines say how to fetch the catalogue it reads), into
`docs/play-store/<app>/`. All are 24-bit PNGs
without alpha.

| Asset | Play's rule | File |
|---|---|---|
| App icon | 512 x 512 PNG | `icon-512.png`. Brasscribe's is its brand build's `dist/icons/android/play-store-512.png`; Fretscribe had none, so it is rendered from `brand/app-icon-fullbleed.svg`. |
| Feature graphic | 1024 x 500, JPEG or 24-bit PNG | `feature-graphic.png`. Brasscribe's is the link-preview artwork (mark, wordmark, tagline) widened to 1024 x 500. Fretscribe's is its lockup on the brand's paper. **SJEKK** whether Fretscribe should carry a line of text as Brasscribe's does. |
| Phone screenshots | 2 to 8, at most 2:1, sides 320 to 3,840 px; 4 or more at 1,080 px or wider are recommended | `screenshots/<en|no>-<n>-<name>.png`, six per language. |

No existing screenshot fits as it is. The Android screen catalogue's screens are about 1080 x 2400, which is 2.22:1,
taller than Play's 2:1. The site's phone shots are iPhone screens, 600 x 1304, also over 2:1. The script takes the
catalogue as CI made it on `main` (the `screens-android-<app>` artifacts, which have no status bar) and pads each
screen at the sides to 1200 x 2400 in its own background colour, so nothing is cut. The catalogue shows only the
public-domain *Old Hundredth* or an invented song. Most of `apps/android/docs/screenshots/brasscribe/design/` shows a
real piece and must never be used.

| App | Screens (en and no) |
|---|---|
| Brasscribe | the score; checking the marked places; fixing a note; sheet music from a picture; practice; the music stand |
| Fretscribe | the tab; checking the song; fixing a note; tuning and capo; the sound; the speed trainer |

They are from `main` at the time of writing. Run the script again on a newer catalogue when a screen has changed.
Tablet screenshots are optional and not made.

## App content

### Category and tags

| | Answer |
|---|---|
| App or game | App |
| Category | Music & Audio |
| Tags (up to 5) | Music, Music education, Sheet music (**SJEKK** against Play's list of tags) |
| Free or paid | Free (this cannot be changed to paid later) |

### Ads

No. Neither app shows ads or contains an ad SDK. `VerifyNoGoogleServices` (the Gradle check in each product's
build) stops a build that brings in Google Play services or Firebase.

### App access

Neither app has a login, an account or a paid feature.

- **Brasscribe: "All functionality is available without any access restrictions"**, with instructions. A solo is
  written on the phone with no computer: record or open a recording of one instrument, choose "One instrument" and
  "On this phone". Opening a MusicXML file shows the score, playback and the music stand. A whole band, and sheet
  music from a picture, need Bandroom on a Mac or Windows PC on the same Wi-Fi
  (`https://scribe.kalli.app/brasscribe/guide/`), paired by its QR code.
- **Fretscribe: "Some functionality is restricted"**, with instructions. It has no listening on the phone
  (`OnPhone.None` in `Fretscribe.kt`) and opens no sheet music (`Product.opensScores`), so without Bandroom on a
  computer a reviewer sees the first run, the instrument and tuning, recording, and the screen that asks for a
  computer, but never a tab. A reviewer will not install a desktop app.

  Proposal: **a built-in example song** in Fretscribe, an invented bass line with its recording and its finished
  tab (the catalogue's "Bass line" fixture), offered on the home screen ("Try an example"), that opens the tab,
  the sound, Check the song, fixing a note and practice with no computer. It shows the reviewer the whole app,
  helps a new player too, and needs no video to keep up to date. Until it exists, a short unlisted video of a real
  session (pairing Bandroom, recording a riff, the tab) goes in the instructions. **SJEKK** which the owner
  prefers; the example song is a feature of its own (a pull request).

### Content rating (IARC questionnaire)

| Question | Answer |
|---|---|
| Category | All other app types (not a game, not social, not news) |
| Violence, sexuality, language, controlled substances, gambling | No |
| Do users interact or exchange content with each other in the app? | No. Sharing a score goes through Android's share sheet to another app; there is no exchange inside the app. |
| Does the app share the user's location? | No |
| Digital purchases? | No |
| Unrestricted internet access (a browser)? | No. The app opens the GitHub releases page in the phone's browser to download Bandroom, and connects to Bandroom on the local network. |

Expected result: the lowest rating in every system (PEGI 3, Everyone). **SJEKK** once the questionnaire is done.

### Target audience

| | Answer |
|---|---|
| Ages | 13 to 15, 16 to 17, and 18 and over. **SJEKK.** Young players in school and youth bands are an obvious audience. Including an age under 13 brings in the Families policy (Teacher Approved, stricter rules on ads and data), so stay at 13 and over unless the owner wants that. |
| Could the app appeal to children by accident? | No: no characters, no games, the language is for musicians |

### Data safety

Answer: **"Does your app collect or share any of the required user data types?" No.** The reasons, read from the
code:

- **What leaves the phone:** a recording (audio), and photos or PDFs of printed music, go to the engine in
  Bandroom on the player's own computer. That happens only when the player chooses "On your computer" and has paired
  that computer. The phone connects only to the address the player typed in, one in a pairing link on the local
  network, or one found there by mDNS (`network_security_config.xml`, `EngineDiscovery.kt`, `PairLink.kt`). The
  developer never receives any of it, and Bandroom's engine sends nothing to a third party (`engine/src` has no
  outbound call with user data). Play's rule: data is "collected" when it is sent off the device to the developer
  or a third party. Data that goes only to the user's own computer, and that the developer cannot read, is not
  collected.
- **What else goes over the network:** the "Get Bandroom" link opens the GitHub releases page in the browser. The
  app makes no call of its own to any server on the internet.
- **No analytics, crash reporting, advertising id, account or Google service.** `VerifyNoGoogleServices` and
  `GoogleLeftoversTest` keep Google Play services, Firebase and their leftovers out.
- **On the phone only:** recordings, scores, settings and the pairing token stay in the app's own storage. Play
  does not count data that never leaves the device.
- **Bandroom's downloads:** when it is set up, Bandroom downloads its listening models (and the printed-music
  reader's files) from the internet, on the player's computer. None of the player's music goes with that.

**SJEKK:**

- **ONNX Runtime's telemetry (Brasscribe).** Brasscribe for Android ships Microsoft's ONNX Runtime with its
  telemetry on today: it sends events with a device identifier to `mobile.events.data.microsoft.com`
  (THIRD_PARTY_NOTICES.md). Play counts a device id an SDK sends as collected and shared. "No data collected" holds
  only once the change that switches the telemetry off in every build has merged and is in the uploaded bundle.
  Until then, the honest answer is "Device or other IDs: collected and shared, for analytics, by an SDK", or wait.
  Bandroom's engine on the computer runs ONNX Runtime too; that is not the phone app's Data safety, but the privacy
  page should not claim more than is true of it.
- **Android's backup.** The manifest has `allowBackup="true"` with `data_extraction_rules.xml`. That file keeps
  the recordings (`takes`), the pairing token and the connection settings out of cloud backup and device transfer.
  So the saved scores and the other settings go to the player's own Google account backup, if the player has
  backup on. Google's guidance is that data the platform backs up to the user's own account is not collected by the
  developer; confirm that against the form's help text. Otherwise exclude the scores too (a small change to that
  file), or turn backup off. Either way the privacy page should say what is backed up.
- The link between the phone and Bandroom is plain HTTP on the local network, with a pairing code and a bearer
  token, and is not encrypted. That does not make it "collected", since the data still goes to no one but the
  player. But it rules out the "data is encrypted in transit" badge, and the answer must not claim it.
- If a later version adds crash reports, a model download through a service, or the Play Integrity API, this
  answer changes.

Deleting data: there is no account, so Play's account-deletion requirement does not apply. Answer "No account".

### Permissions and declarations

Play asks for a declaration, with a short video, for each foreground service type an app targeting Android 14 or
newer uses. The types are in `features/play/src/main/AndroidManifest.xml`; each is for one feature:

| Type | Service | The feature | Needed? |
|---|---|---|---|
| `microphone` | `CaptureService` | Recording with the microphone goes on with the screen off or in another app: a rehearsal is recorded with the phone on the stand or in a pocket. | Yes. Without it Android stops the microphone when the screen turns off, and a rehearsal take is cut. Both apps. |
| `mediaProjection` | `CaptureService` | "Record what's playing": recording the sound another app on the phone plays, started by the player and shown in the notification. | Yes. Android lets an app capture another app's sound only from a foreground service of this type. Both apps. |
| `dataSync` | `ComputerJobService` | Sending the recording to the player's own computer, and following the job there, goes on when the player leaves the app; a notification says when the score or tab is ready. | Yes for now: without it, leaving the app mid-send stops the upload of a long take, and nothing says when the score is ready. **SJEKK:** Play points apps that move data at Android's user-initiated data transfer jobs instead of `dataSync`; moving to one is a change to the send-and-follow flow, not a small one, and is not proposed here. Both apps. |
| `mediaProcessing` | `DraftService` | Brasscribe only: a band draft made on the phone goes on when the player leaves the app. | Yes in Brasscribe. Fretscribe writes nothing down on the phone and never starts it, so it leaves Fretscribe's manifest (#563); Fretscribe declares three types. |

None can be dropped from Brasscribe without losing a feature. Each needs a video link (an unlisted video, about
30 s). The shot lists below can be recorded in one sitting on the phone, with Bandroom running and paired on a
computer on the same Wi-Fi, the phone's screen recorder on, and only the public-domain *Old Hundredth*
(`apps/fixtures/old-hundredth`) or an invented line as the music. Record each for Brasscribe, then the first three
again for Fretscribe (with an invented bass line). The labels are the apps' English ones.

**Video 1, `microphone` (about 30 s).**
1. Open the app. On Home, tap **Record with the microphone**; allow the microphone if asked.
2. Recording starts; pull down the notification shade to show "Recording with the microphone", and close it.
3. Press the power button: the screen goes off. Wait 5 s, with some playing near the phone.
4. Wake and unlock the phone: the app is still recording, its time has gone on.
5. Tap **Stop recording**: the take is kept and the app asks what it is.

**Video 2, `mediaProjection` (about 30 s).**
1. In another app (the Files app, or a music player), start playing the *Old Hundredth* recording.
2. Open the app. On Home, tap **Record what's playing**.
3. Android asks whether the app may record what plays on the phone: allow it.
4. Show the notification ("Recording what's playing on this phone"). Switch to the other app for a few seconds:
   the music goes on, the notification stays.
5. Back in the app, tap **Stop recording**: the take is kept.

**Video 3, `dataSync` (about 40 s).**
1. Open the app, already paired with Bandroom (Home shows the computer as connected).
2. Open or record a take, say what it is, choose **On your computer**, and tap **Continue**.
3. While it says it is sending the recording to the computer, press Home: the app leaves the screen.
4. Pull down the notification shade: "Your computer is making the score" (in Fretscribe, its words for the tab).
5. Wait until the notification says it is ready, and tap it: the score (the tab) opens.

**Video 4, `mediaProcessing`, Brasscribe only (about 30 s).**
1. Open Brasscribe, open a recording of the band playing *Old Hundredth*, and choose **Brass band**.
2. Choose **On this phone: a quick draft**, and tap **Continue**.
3. While the draft is being made, press Home; pull down the shade to show "Making a band draft".
4. Go back to Brasscribe when it is done: the draft is there.

Other permissions (no declaration form, but the listing should not surprise): `RECORD_AUDIO`, `CAMERA` (a photo of
printed music, and scanning Bandroom's pairing code), `POST_NOTIFICATIONS`, `INTERNET`, `ACCESS_NETWORK_STATE`,
`ACCESS_LOCAL_NETWORK` (to reach the computer on the same network).

### Other declarations

| Question | Answer |
|---|---|
| News app | No |
| COVID-19 contact tracing or status | No |
| Government app | No |
| Financial features | None |
| Health features | None |
| Uses the advertising id | No. A release bundle's manifest has no `AD_ID` permission (`.github/scripts/check-aab.py` prints the permissions of each bundle the release builds). |

## Before the first upload

1. Settle every SJEKK above, with the privacy page live and ONNX Runtime's telemetry off in the uploaded build.
2. Play App Signing: choose the app's own key (Brasscribe's new key, the prototypes key for Fretscribe), as
   docs/shared/dev/release.md describes. After the first upload, check the certificate's SHA-256 there.
3. The first internal testing release of each app is made by hand in the Console, from the bundle of a GitHub
   release made after the move to `app.kalli.*`. The workflow uploads from then on.
