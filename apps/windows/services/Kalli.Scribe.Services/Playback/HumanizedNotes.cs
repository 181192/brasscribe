namespace Kalli.Scribe.Playback;

/// <summary>One part note for the humanizer: Composition ticks (24 per beat), score-tempo seconds, concert MIDI pitch.</summary>
public sealed record HumanizeNote(long Tick, long DurTick, double StartS, double EndS, int Pitch, int Velocity);

/// <summary>A humanized note: played start and end in seconds and velocity.</summary>
public sealed record PlayedNote(double Start, double End, int Pitch, int Velocity, bool Staccato, bool FromComposition);

/// <summary>A player's humanized notes (in <see cref="HumanizeNote"/> order sorted by tick, pitch) and their detune in cents.</summary>
public sealed record HumanizedPart(IReadOnlyList<PlayedNote> Notes, double DetuneCents);

/// <summary>Humanizes one player's notes; null when no humanizer is available.</summary>
public delegate HumanizedPart? Humanize(IReadOnlyList<HumanizeNote> notes, string part, int player, string? compositionJson);
