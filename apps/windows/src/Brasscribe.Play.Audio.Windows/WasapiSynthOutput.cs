using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using NAudio.CoreAudioApi;
using NAudio.CoreAudioApi.Interfaces;
using NAudio.Wave;

namespace Brasscribe.Play.Audio.Windows;

/// <summary>
/// Plays the alphaTab synth buffer through WASAPI shared mode on the default output device.
/// The stream is open only while the band plays: it opens on Play and closes once the pause fade has
/// played out, so an idle app holds no audio stream (which keeps Windows from sleeping). When the device
/// goes away or Windows' default output changes (headphones plugged in, a Bluetooth speaker), playing
/// moves to the new default device; a stream that could not open (no device at all) is tried again
/// when a device appears. All opening and closing happens on one thread of its own.
/// </summary>
[SupportedOSPlatform("windows10.0.19041")]
public sealed class WasapiSynthOutput : IAudioOutput
{
    private readonly BlockingCollection<Action> _work = new();
    private readonly Thread _thread;
    private MMDeviceEnumerator? _devices;
    private DeviceWatcher? _watcher;
    private BufferedSynthOutput? _source;
    private WasapiOut? _out;
    private string? _deviceId;
    private bool _failed;

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
            _watcher = new DeviceWatcher(this);
            _devices.RegisterEndpointNotificationCallback(_watcher);
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
            if (_devices is not null && _watcher is not null) _devices.UnregisterEndpointNotificationCallback(_watcher);
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
        _failed = true; // until the stream plays: no device, or one that refused, is tried again when a device appears
        var device = _devices.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia);
        var output = new WasapiOut(device, AudioClientShareMode.Shared, useEventSync: true, latency: 80);
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
        _deviceId = device.ID;
        _failed = false;
    }

    private void Close()
    {
        if (_out is not { } output) return;
        _out = null;
        _deviceId = null;
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
            Close();
            _failed = true;
            if (_source is { IsPlaying: true }) Open();
        });
    }

    /// <summary>Windows' default output changed: an open stream moves to it.</summary>
    private void DefaultChanged(string? deviceId) => Post(() =>
    {
        if (_out is null || deviceId == _deviceId) return;
        Close();
        if (_source is { IsPlaying: true }) Open();
    });

    /// <summary>A device came (back): a stream that could not open tries again.</summary>
    private void DeviceArrived() => Post(() =>
    {
        if (_failed && _out is null && _source is { IsPlaying: true }) Open();
    });

    private sealed class SynthSampleProvider(BufferedSynthOutput source) : ISampleProvider
    {
        public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat((int)source.SampleRate, 2);

        public int Read(float[] buffer, int offset, int count) => source.Read(buffer.AsSpan(offset, count));
    }

    /// <summary>Windows' device notifications; they arrive on a system thread and only post work.</summary>
    private sealed class DeviceWatcher(WasapiSynthOutput owner) : IMMNotificationClient
    {
        public void OnDeviceStateChanged(string deviceId, DeviceState newState)
        {
            if (newState == DeviceState.Active) owner.DeviceArrived();
        }

        public void OnDeviceAdded(string pwstrDeviceId) => owner.DeviceArrived();

        public void OnDeviceRemoved(string deviceId) { }

        public void OnDefaultDeviceChanged(DataFlow flow, Role role, string defaultDeviceId)
        {
            if (flow != DataFlow.Render || role != Role.Multimedia) return;
            owner.DefaultChanged(defaultDeviceId);
            owner.DeviceArrived();
        }

        public void OnPropertyValueChanged(string pwstrDeviceId, PropertyKey key) { }
    }
}
