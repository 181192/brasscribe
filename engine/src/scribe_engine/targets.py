"""Targets: the kinds of output the engine makes, and what each one calls its files.

A target turns the notes that were heard into one kind of output: a score for a brass band, a tab for a
fretted instrument. Every profile belongs to one target. What a target's files are called and the title
a job gets when none is given are defined here and nowhere else: shared code asks the target of a job's
profile instead of naming a file itself.

The pipelines themselves are built in profiles.py (the band's) and tab.py, bass_tab.py (the tab's).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    id: str
    stem: str  # the score's file name without its suffix: <stem>.musicxml, <stem>.pdf, <stem>.mid, …
    titles: dict[str, str]  # profile id -> a job's title when it has none ({name}: the recording's name)

    @property
    def profiles(self) -> tuple[str, ...]:
        return tuple(self.titles)

    def file(self, suffix: str) -> str:
        """The score in one format: file("pdf")."""
        return f"{self.stem}.{suffix.lstrip('.')}"

    @property
    def musicxml(self) -> str:
        return self.file("musicxml")

    @property
    def rendered(self) -> tuple[str, ...]:
        """What MuseScore renders from the MusicXML for every job: the page and the MIDI."""
        return (self.file("pdf"), self.file("mid"))


BRASS = Target(
    id="brass",
    stem="brass-band",
    titles={
        "solo": "{name} — solo (draft)",
        "brass-band": "{name} — brass band (draft)",
        "pop-rock": "{name} — brass band (draft)",
        "orchestra-with-soloist": "{name} — solo cornet & brass band (draft)",
    },
)

FRETTED = Target(
    id="fretted",
    stem="tab",
    titles={
        "tab": "{name} — tab (draft)",
        "bass-tab": "{name} — bass tab (draft)",
    },
)

TARGETS: dict[str, Target] = {t.id: t for t in (BRASS, FRETTED)}


def of(profile: str) -> Target:
    """The target `profile` belongs to. KeyError for a profile no target has."""
    for t in TARGETS.values():
        if profile in t.titles:
            return t
    raise KeyError(f"unknown profile {profile!r}; choose from {', '.join(p for t in TARGETS.values() for p in t.titles)}")


def in_dir(outputs) -> Target | None:
    """The target whose score is in a run's `outputs` directory, or None when it holds none."""
    for t in TARGETS.values():
        if (outputs / t.musicxml).exists():
            return t
    return None
