using AlphaTab;
using AlphaTab.Core.EcmaScript;
using AlphaTab.Synth;

namespace Brasscribe.Play.Core.Playback;

/// <summary>
/// alphaTab synth output that buffers interleaved stereo float samples and lets an audio device
/// (WASAPI on Windows, a test loop elsewhere) pull them with <see cref="Read"/>. The synth renders
/// on the pulling thread when the buffer runs low, as alphaTab's own NAudio output does. Every
/// sample goes through the shared output stage (make-up gain, then the soft limiter) on its way in.
/// </summary>
public sealed class BufferedSynthOutput : ISynthOutput
{
    private readonly object _gate = new();
    private float[] _ring = new float[1];
    private int _read, _count;
    private int _lowWater;
    private bool _playing;
    private float[] _fade = [];
    private int _fadeAt;
    private bool _drainedSaid;

    /// <summary>How long a pause or stop takes to fade out: short enough to feel immediate, long enough not to click.</summary>
    public const double StopFadeMs = 80;

    public BufferedSynthOutput(int sampleRate = 44100) => SampleRate = sampleRate;

    public double SampleRate { get; }
    public bool IsPlaying => _playing;

    /// <summary>
    /// Lock shared with the player: alphaTab's synth is not thread-safe, and it renders on the
    /// audio thread (through <see cref="SampleRequest"/>) while the UI thread seeks, mutes and loads.
    /// </summary>
    public object SyncRoot { get; } = new();

    public IEventEmitter Ready { get; } = new Emitter();
    public IEventEmitterOfT<double> SamplesPlayed { get; } = new Emitter<double>();
    public IEventEmitter SampleRequest { get; } = new Emitter();

    public void Open(double bufferTimeInMilliseconds)
    {
        int frames = (int)Math.Ceiling(SampleRate * Math.Max(bufferTimeInMilliseconds, 50) / 1000.0);
        lock (_gate)
        {
            _ring = new float[frames * 2 * 4];
            _lowWater = frames * 2;
            _read = _count = 0;
        }
        ((Emitter)Ready).Trigger();
    }

    public void Activate() { }

    /// <summary>
    /// Playing starts: the audio device should be open. Raised on the thread that called Play; the device
    /// can open a moment later, as the samples wait in the buffer.
    /// </summary>
    public event EventHandler? PlayRequested;

    /// <summary>
    /// Paused or stopped, and the stop fade has been played out: the audio device can close, so an idle app
    /// keeps no audio stream open (which would keep the PC awake). Raised once per pause, on the audio thread.
    /// </summary>
    public event EventHandler? Drained;

    public void Play()
    {
        lock (_gate)
        {
            _fade = [];
            _drainedSaid = false;
        }
        _playing = true;
        RequestIfLow();
        PlayRequested?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>
    /// Stops pulling from the synth, but plays the next <see cref="StopFadeMs"/> of what is already
    /// rendered with a fade to silence, so stopping never cuts the band off with a click.
    /// </summary>
    public void Pause()
    {
        if (!_playing) return;
        lock (_gate)
        {
            int n = Math.Min(_count, 2 * (int)(SampleRate * StopFadeMs / 1000)) & ~1;
            _fade = new float[n];
            for (int i = 0; i < n; i++)
            {
                double g = 1 - (double)(i / 2) / Math.Max(1, n / 2);
                _fade[i] = (float)(_ring[(_read + i) % _ring.Length] * g * g);
            }
            _fadeAt = 0;
        }
        _playing = false;
    }

    public void Destroy() => _playing = false;

    public void AddSamples(Float32Array f)
    {
        lock (_gate)
        {
            int n = (int)f.Length;
            if (_count + n > _ring.Length) Grow(_count + n);
            int write = (_read + _count) % _ring.Length;
            float g = Gain;
            for (int i = 0; i < n; i++)
            {
                _ring[write] = OutputStage.Limit((float)f[i] * g);
                if (++write == _ring.Length) write = 0;
            }
            _count += n;
        }
    }

    /// <summary>
    /// Make-up gain before the soft limiter (<see cref="OutputStage"/>): the band's, from
    /// sounds/playback-levels.json. Applied as samples arrive, so the stop fade runs on the output.
    /// </summary>
    public float Gain { get; set; } = OutputStage.BandGain;

    public void ResetSamples()
    {
        lock (_gate) _read = _count = 0;
    }

    public Task<IList<ISynthOutputDevice>> EnumerateOutputDevices() => Task.FromResult<IList<ISynthOutputDevice>>([]);
    public Task SetOutputDevice(ISynthOutputDevice? device) => Task.CompletedTask;
    public Task<ISynthOutputDevice?> GetOutputDevice() => Task.FromResult<ISynthOutputDevice?>(null);

    /// <summary>Fills <paramref name="destination"/> with interleaved stereo samples; silence when paused or starved.</summary>
    public int Read(Span<float> destination)
    {
        if (!_playing)
        {
            destination.Clear();
            bool drained;
            lock (_gate)
            {
                int n = Math.Min(destination.Length, _fade.Length - _fadeAt);
                if (n > 0) _fade.AsSpan(_fadeAt, n).CopyTo(destination);
                _fadeAt += Math.Max(0, n);
                drained = n <= 0 && !_drainedSaid;
                if (drained) _drainedSaid = true;
            }
            if (drained) Drained?.Invoke(this, EventArgs.Empty);
            return destination.Length;
        }
        RequestIfLow(destination.Length);
        int copied;
        lock (_gate)
        {
            copied = Math.Min(destination.Length, _count);
            for (int i = 0; i < copied; i++)
            {
                destination[i] = _ring[_read];
                if (++_read == _ring.Length) _read = 0;
            }
            _count -= copied;
        }
        destination[copied..].Clear();
        if (copied > 0) ((Emitter<double>)SamplesPlayed).Trigger(copied / 2);
        RequestIfLow();
        return destination.Length;
    }

    private void RequestIfLow(int wanted = 0)
    {
        for (int guard = 0; guard < 64; guard++)
        {
            int count;
            lock (_gate) count = _count;
            if (count >= Math.Max(_lowWater, wanted)) return;
            int before = count;
            // Never wait long behind the player's lock (a SoundFont load holds it for seconds, and alphaTab keeps
            // its SoundFont parser internal, so it can't be parsed outside it): play what is buffered, and render
            // on the next pull.
            if (!Monitor.TryEnter(SyncRoot, LockWait)) return;
            try { ((Emitter)SampleRequest).Trigger(); }
            finally { Monitor.Exit(SyncRoot); }
            lock (_gate) if (_count == before) return; // the synth has nothing more to give
        }
    }

    /// <summary>How long a pull waits for the player's lock: well inside the device's 80 ms buffer.</summary>
    private static readonly TimeSpan LockWait = TimeSpan.FromMilliseconds(10);

    private void Grow(int needed)
    {
        var bigger = new float[Math.Max(needed, _ring.Length * 2)];
        for (int i = 0; i < _count; i++) bigger[i] = _ring[(_read + i) % _ring.Length];
        _ring = bigger;
        _read = 0;
    }
}

/// <summary>Minimal alphaTab event emitters (alphaTab's own are internal).</summary>
internal class Emitter : IEventEmitter
{
    private readonly List<Action> _handlers = [];

    public Action On(Action value)
    {
        lock (_handlers) _handlers.Add(value);
        return () => Off(value);
    }

    public void Off(Action value)
    {
        lock (_handlers) _handlers.Remove(value);
    }

    public void Trigger()
    {
        Action[] copy;
        lock (_handlers) copy = [.. _handlers];
        foreach (var h in copy) h();
    }
}

internal sealed class Emitter<T> : IEventEmitterOfT<T>
{
    private readonly List<Action<T>> _typed = [];
    private readonly List<Action> _plain = [];

    public Action On(Action<T> value)
    {
        lock (_typed) _typed.Add(value);
        return () => Off(value);
    }

    public void Off(Action<T> value)
    {
        lock (_typed) _typed.Remove(value);
    }

    public Action On(Action value)
    {
        lock (_typed) _plain.Add(value);
        return () => Off(value);
    }

    public void Off(Action value)
    {
        lock (_typed) _plain.Remove(value);
    }

    public void Trigger(T arg)
    {
        Action<T>[] typed;
        Action[] plain;
        lock (_typed)
        {
            typed = [.. _typed];
            plain = [.. _plain];
        }
        foreach (var h in typed) h(arg);
        foreach (var h in plain) h();
    }
}
