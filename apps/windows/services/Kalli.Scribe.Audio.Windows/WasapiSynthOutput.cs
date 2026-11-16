using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using Kalli.Scribe.Playback;
using Kalli.Scribe.Services;
using NAudio.CoreAudioApi;
using NAudio.Wave;

namespace Kalli.Scribe.Audio.Windows;

/// <summary>
/// Plays the alphaTab synth buffer through WASAPI shared mode on the default output device.
/// The stream is open only while the band plays: it opens on Play and closes once the pause fade has
/// played out, so an idle app holds no audio stream (which keeps Windows from sleeping). When the device
/// goes away or Windows' default output changes (headphones plugged in, a Bluetooth speaker), playing
/// moves to the new default device; a stream that could not open (no device at all) is tried again
/// when a device appears (<see cref="OutputRouting"/> decides). All opening and closing happens on one thread of
/// its own.
/// </summary>
public sealed class WasapiSynthOutput : IAudioOutput
{
    private readonly BlockingCollection<Action> _work = new();
    private readonly Thread _thread;
    private readonly OutputRouting _routing = new();
    private MMDeviceEnumerator? _devices;
    private MMDeviceNotificationClient? _notifications;
    private BufferedSynthOutput? _source;
    private WasapiPlayer? _out;

    public WasapiSynthOutput()
    {
        _thread = new Thread(() =>
        {
            foreach (var work in _work.GetConsumingEnumerable())
            {
                try { work(); }
                catch (Exception e)
                {
                    // A thread of our own: nothing above it would catch this, and no audio must never mean no app.
                    System.Diagnostics.Trace.TraceWarning($"Audio output: {e.Message}");
                }
            }
        }) { IsBackground = true, Name = "Audio output" };
        _thread.SetApartmentState(ApartmentState.MTA);
        _thread.Start();
        Post(() =>
        {
            _devices = new MMDeviceEnumerator();
            // Windows' device notifications arrive on a system thread (no synchronization context) and only post work.
            _notifications = _devices.CreateNotificationClient(useSynchronizationContext: false);
            _notifications.DeviceStateChanged += (_, e) => { if (e.NewState == DeviceState.Active) DeviceArrived(); };
            _notifications.DeviceAdded += (_, _) => DeviceArrived();
            _notifications.DefaultDeviceChanged += (_, e) =>
            {
                DefaultChanged(e.Flow == DataFlow.Render && e.Role == Role.Multimedia, e.DeviceId);
                DeviceArrived();
            };
        });
    }

    /// <summary>Plays <paramref name="source"/> whenever it plays; the device opens with the first Play.</summary>
    public void Start(BufferedSynthOutput source)
    {
        Post(() =>
        {
            if (!ReferenceEquals(_source, source))
            {
                Close();
                if (_source is { } old)
                {
                    old.PlayRequested -= OnPlayRequested;
                    old.Drained -= OnDrained;
                }
                _source = source;
                source.PlayRequested += OnPlayRequested;
                source.Drained += OnDrained;
            }
            if (source.IsPlaying) Open();
        });
    }

    public void Stop() => Post(Close);

    public void Dispose()
    {
        if (_work.IsAddingCompleted) return;
        Post(() =>
        {
            Close();
            if (_source is { } s)
            {
                s.PlayRequested -= OnPlayRequested;
                s.Drained -= OnDrained;
            }
            _notifications?.Dispose();
            _devices?.Dispose();
        });
        _work.CompleteAdding();
        _thread.Join(TimeSpan.FromSeconds(2));
    }

    private void Post(Action action)
    {
        try { _work.Add(action); }
        catch (InvalidOperationException) { } // disposed
    }

    private void OnPlayRequested(object? sender, EventArgs e) => Post(Open);

    // On the audio thread: the stream can't be stopped from inside its own callback, so the worker does it,
    // and only if nothing started playing again in the meantime.
    private void OnDrained(object? sender, EventArgs e) => Post(() => { if (_source is { IsPlaying: false }) Close(); });

    private void Open()
    {
        if (_out is not null || _source is not { } source || _devices is null) return;
        _routing.Opening();
        var device = _devices.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia);
        // Shared mode, event-driven, 80 ms: as the band's stream has always been opened.
        var output = new WasapiPlayerBuilder().WithDevice(device).WithSharedMode().WithEventSync().WithLatency(80).Build();
        try
        {
            output.Init(new SynthSampleProvider(source));
            output.PlaybackStopped += OnPlaybackStopped;
            output.Play();
        }
        catch
        {
            output.Dispose();
            throw;
        }
        _out = output;
        _routing.Opened(device.ID);
    }

    private void Close()
    {
        if (_out is not { } output) return;
        _out = null;
        _routing.Closed();
        output.PlaybackStopped -= OnPlaybackStopped;
        output.Stop();
        output.Dispose();
    }

    /// <summary>The stream ended by itself: the device was unplugged, disabled or taken for exclusive use.</summary>
    private void OnPlaybackStopped(object? sender, StoppedEventArgs e)
    {
        if (e.Exception is null) return;
        System.Diagnostics.Trace.TraceWarning($"Audio output stopped: {e.Exception.Message}");
        Post(() =>
        {
            if (!ReferenceEquals(sender, _out)) return;
            Do(_routing.StreamEnded(Playing));
        });
    }

    private bool Playing => _source is { IsPlaying: true };

    /// <summary>Windows' default device changed: an open stream moves to the new default output.</summary>
    private void DefaultChanged(bool mediaOutput, string? deviceId) =>
        Post(() => Do(_routing.DefaultChanged(mediaOutput, deviceId, Playing)));

    /// <summary>A device came (back): a stream that could not open tries again.</summary>
    private void DeviceArrived() => Post(() => Do(_routing.DeviceArrived(Playing)));

    private void Do(OutputAction action)
    {
        if (action is OutputAction.Close or OutputAction.Reopen) Close();
        if (action is OutputAction.Open or OutputAction.Reopen) Open();
    }

    private sealed class SynthSampleProvider(BufferedSynthOutput source) : ISampleProvider
    {
        public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat((int)source.SampleRate, 2);

        public int Read(Span<float> buffer) => source.Read(buffer);
    }
}
