namespace Kalli.Scribe.Tab;

/// <summary>
/// The recording as the sound of the tab: played from its file at any speed with the pitch kept, from any second,
/// and over a stretch again and again. The app implements it on its platform's player; used from the UI thread only.
/// </summary>
public interface IRecordingPlayer : IDisposable
{
    /// <summary>
    /// The recording is sounding, or about to: asked to play, not at its end, and the system lets it (a moment of
    /// reading the file after a jump is still playing; another app that takes the sound away for a while is not).
    /// </summary>
    bool Playing { get; }

    /// <summary>It was asked to play and has not been paused, whether or not the system lets it sound now.</summary>
    bool Asked { get; }

    /// <summary>Where the recording is, in seconds.</summary>
    double Position { get; }

    /// <summary>How long the recording is, in seconds; 0 until it has been read.</summary>
    double Duration { get; }

    /// <summary>1 is the recording's own speed. The pitch is the recording's at every speed.</summary>
    double Speed { get; set; }

    /// <summary>The stretch to play again and again; null plays on to the end.</summary>
    SecondsRange? Repeat { get; set; }

    void Play();
    void Pause();
    void SeekTo(double seconds);
}

/// <summary>What the player tells the screen of: playing began or stopped, the end was reached, or the file cannot be played.</summary>
public interface IRecordingPlayerListener
{
    void OnPlaying(bool playing);
    void OnEnded();
    void OnFailed();
}

/// <summary>Opens a recording's file in the app's player; it tells the listener what it does, on the UI thread.</summary>
public interface IRecordingPlayers
{
    IRecordingPlayer Open(string path, IRecordingPlayerListener listener);
}
