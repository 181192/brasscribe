# Google Play: the Console answers, drafted

A draft of every answer the Play Console asks for, for **Brasscribe** (`app.kalli.brasscribe`) and **Fretscribe**
(`app.kalli.fretscribe`), for the owner to read before anything is submitted. Both apps go to the **internal
testing** track only (docs/shared/dev/release.md, Google Play). Every point marked **SJEKK** is a doubt to settle
first. Nothing here has been entered in the Console.

The answers come from the code and docs as they are when this was written. Where they rest on code, the file is
named, so a change there means the answer must be checked again.

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

Full description, en-US (1,106 characters):

> Record a rehearsal or open a recording, and Brasscribe writes down a part for every player in the band.
>
> A part for every player. Full brass band, a small band or a quartet. Each part in its range, written for B flat or E flat as the player reads it.
>
> A ? where it is not sure. A note Brasscribe was not sure of gets a ?. You hear that bar, keep the note or change it, and go on to the next.
>
> The band to practise with. The score plays back with band sounds. Mute your own part, slow it down, repeat the hard bars.
>
> Your part on the stand. Your own part fills the screen, with page turns from a pedal. Print it, or share the score as PDF, MusicXML or MIDI.
>
> Readable and audible. Large text, dark mode, a talking score that reads the music aloud, and braille music for those who use it.
>
> A solo is written on the phone. For a whole band, Brasscribe sends the recording to Bandroom, a free app for your own Mac or Windows PC on the same network. Your recordings go only to your own computer: nothing is sent to us or to anyone else.
>
> Brasscribe is a free, non-commercial project, with no ads and no account.

Full description, no-NO (1,136 characters):

> Ta opp en øvelse eller åpne et opptak, så skriver Brasscribe ned en stemme til hver musiker i bandet.
>
> En stemme til hver musiker. Fullt brassband, et lite band eller en kvartett. Hver stemme i sitt register, skrevet i B eller Ess slik musikeren leser den.
>
> Et ? der den er usikker. En tone Brasscribe var usikker på, får et ?. Du hører den takten, beholder tonen eller endrer den, og går videre til neste.
>
> Et band å øve med. Partituret spilles av med bandlyder. Demp din egen stemme, sett ned tempoet, gjenta de vanskelige taktene.
>
> Din stemme på notestativet. Din egen stemme fyller skjermen, og du blar med en pedal. Skriv den ut, eller del partituret som PDF, MusicXML eller MIDI.
>
> Lett å lese og høre. Stor tekst, mørk modus, et partitur som leser musikken høyt, og punktskrift for dem som bruker det.
>
> En solo skrives på telefonen. For et helt band sender Brasscribe opptaket til Bandroom, en gratis app til din egen Mac eller Windows-PC på samme nettverk. Opptakene dine går bare til din egen datamaskin: ingenting sendes til oss eller noen andre.
>
> Brasscribe er et gratis, ikke-kommersielt prosjekt, uten reklame og uten konto.

### Fretscribe

| Field | en-US | no-NO |
|---|---|---|
| App name | Fretscribe (10) | Fretscribe (10) |
| Short description | Play a riff or open a recording, and get tab for your instrument and tuning. (76) | Spill et riff eller åpne et opptak, og få tab for instrumentet og stemmingen. (77) |

Full description, en-US (969 characters):

> Play a riff or open a recording, and Fretscribe writes it down as tab for your instrument and your tuning.
>
> Tab for your instrument. Guitar, bass, ukulele or mandolin, with the strings you have and the tuning you play in.
>
> A look before it writes. First it shows the tuning, the key and the tempo it heard. If one of them is off, you put it right before a single fret is written.
>
> A ? where it is not sure. Choose a note with a ? and it plays that bar slowly, so you can hear for yourself.
>
> Practise. Play along with the recording, slower if you like, the hard bars again and again.
>
> Open or record. Open a recording you have, play into the microphone, or record what another app on the phone is playing.
>
> Fretscribe writes the tab on Bandroom, a free app for your own Mac or Windows PC on the same network. Your recordings go only to your own computer: nothing is sent to us or to anyone else.
>
> Fretscribe is a free, non-commercial project, with no ads and no account.

Full description, no-NO (954 characters):

> Spill et riff eller åpne et opptak, så skriver Fretscribe det ned som tab for instrumentet og stemmingen din.
>
> Tab for instrumentet ditt. Gitar, bass, ukulele eller mandolin, med strengene du har og stemmingen du spiller i.
>
> En titt før den skriver. Først viser den stemmingen, tonearten og tempoet den hørte. Er noe av det feil, retter du det før én eneste bånd skrives.
>
> Et ? der den er usikker. Velg en tone med ?, så spiller den takten sakte, så du kan høre selv.
>
> Øv. Spill sammen med opptaket, saktere om du vil, de vanskelige taktene om og om igjen.
>
> Åpne eller ta opp. Åpne et opptak du har, spill inn i mikrofonen, eller ta opp det en annen app på telefonen spiller.
>
> Fretscribe skriver taben på Bandroom, en gratis app til din egen Mac eller Windows-PC på samme nettverk. Opptakene dine går bare til din egen datamaskin: ingenting sendes til oss eller noen andre.
>
> Fretscribe er et gratis, ikke-kommersielt prosjekt, uten reklame og uten konto.

**SJEKK:** "før én eneste bånd skrives" is a literal rendering of "before a single fret is written"; a guitarist
may say it otherwise.

### Contact and links (both apps)

| Field | Answer |
|---|---|
| E-mail | `<contact e-mail>` (placeholder: Play shows it publicly) |
| Website | `https://scribe.kalli.app/brasscribe/` and `https://scribe.kalli.app/fretscribe/` (both answer) |
| Phone | none |
| Privacy policy URL | **none exists. SJEKK.** The site has no privacy page (`https://scribe.kalli.app/privacy/` does not answer). Play requires one for every app, and for apps that use the microphone and the camera in any case. A short page on the site would do: what the apps record, where it goes (only to the player's own computer, see Data safety), that nothing reaches the developer or a third party, no accounts, no analytics, no ads, and how to remove everything (uninstall the app; delete Bandroom's data folder). |

### Pictures

Made by `python3 scripts/play-store-images.py`, into `docs/play-store/<app>/`. All are 24-bit PNGs
without alpha.

| Asset | Play's rule | File |
|---|---|---|
| App icon | 512 x 512 PNG | `icon-512.png`. Brasscribe's is its brand build's `dist/icons/android/play-store-512.png`; Fretscribe had none, so it is rendered from `brand/app-icon-fullbleed.svg`. |
| Feature graphic | 1024 x 500, JPEG or 24-bit PNG | `feature-graphic.png`. Brasscribe's is the link-preview artwork (mark, wordmark, tagline) widened to 1024 x 500. Fretscribe's is its lockup on the brand's paper. **SJEKK** whether Fretscribe should carry a line of text as Brasscribe's does. |
| Phone screenshots | 2 to 8, at most 2:1, sides 320 to 3,840 px; 4 or more at 1,080 px or wider are recommended | `screenshots/<lang>-<n>-<screen>.png`, four per language. |

No existing screenshot fits as it is. The Android catalogue's screenshots are 1080 x 2400, which is 2.22:1, taller
than Play's 2:1, and most have an alpha channel. The site's phone shots are iPhone screens, 600 x 1304, also over 2:1.
The script pads the catalogue's screens at the sides to 1200 x 2400 in the screen's own background colour, so
nothing is cut. It uses only screens that show the public-domain *Old Hundredth* or an invented song. Most of
`apps/android/docs/screenshots/brasscribe/design/` shows a real piece and must not be used.

| App | Screens (en and no) |
|---|---|
| Brasscribe | first run with an instrument chosen; the score; checking the marked places; the music stand |
| Fretscribe | the tab; your instrument; checking the song; practise with repeats |

**SJEKK:** the screens are the latest committed catalogue images, not a fresh run. Re-run the catalogue first if a
screen has changed since. Tablet screenshots are optional and not made.

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

Neither app has a login, an account or a paid feature. Answer **"All functionality is available without any access
restrictions"**, and still give the reviewer instructions (Play lets you add them):

- **Brasscribe:** works without a computer for a solo. Record or open a recording of one instrument, choose "One
  instrument" and "On this phone", and the score is written on the phone. Opening a MusicXML file shows the score,
  playback and the music stand. A whole band needs Bandroom on a Mac or Windows PC on the same Wi-Fi
  (`https://scribe.kalli.app/brasscribe/guide/`), paired by its QR code.
- **Fretscribe:** has no listening on the phone (`OnPhone.None` in `Fretscribe.kt`). Tab is written only by
  Bandroom on a computer on the same network. Without it, the reviewer gets through the first run, the choice of
  instrument and tuning, recording, and the screen that says to connect a computer.

**SJEKK:** whether Fretscribe without Bandroom is enough for a review, or the reviewer must be told how to set up
Bandroom. Can Fretscribe open a tab or MusicXML file with no computer?

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

**SJEKK:**

- The link between the phone and Bandroom is plain HTTP on the local network, with a pairing code and a bearer
  token, and is not encrypted. That does not make it "collected", since the data still goes to no one but the
  player. But it rules out the "data is encrypted in transit" badge, and the answer must not claim it.
- If a later version adds crash reports, a model download through a service, or the Play Integrity API, this
  answer changes.

Deleting data: there is no account, so Play's account-deletion requirement does not apply. Answer "No account".

### Permissions and declarations

Play asks for a declaration, with a short video, for each foreground service type an app targeting Android 14 or
newer uses. Both apps declare (`features/play/src/main/AndroidManifest.xml`):

| Foreground service type | Why (draft for the declaration) |
|---|---|
| `microphone` | Recording a rehearsal or a solo continues when the screen turns off or the player switches app. |
| `mediaProjection` | "Record what's playing": recording the sound another app on the phone plays, which the player starts and sees in the notification. |
| `dataSync` | Sending a long recording to the player's own computer continues in the background. |
| `mediaProcessing` | Writing a solo down on the phone continues in the background (Brasscribe). **SJEKK** whether Fretscribe uses it at all, as it has no listening on the phone; if not, the declaration can say so or the type can leave its manifest. |

**SJEKK:** each declaration needs a video link (an unlisted video showing the feature). None exists yet.

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

1. Settle every SJEKK above, and publish a privacy policy page.
2. Play App Signing: choose the app's own key (Brasscribe's new key, the prototypes key for Fretscribe), as
   docs/shared/dev/release.md describes. After the first upload, check the certificate's SHA-256 there.
3. The first internal testing release of each app is made by hand in the Console, from the bundle of a GitHub
   release made after the move to `app.kalli.*`. The workflow uploads from then on.
