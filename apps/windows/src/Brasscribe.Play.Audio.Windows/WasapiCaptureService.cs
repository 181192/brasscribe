using System.Diagnostics;
using System.Runtime.Versioning;
using Brasscribe.Play.Core.Capture;
using NAudio.CoreAudioApi;
using NAudio.Wave;

namespace Brasscribe.Play.Audio.Windows;

/// <summary>
/// <see cref="ICaptureService"/> on WASAPI: microphone (shared-mode capture), everything the default
/// output plays (endpoint loopback) and one app (process loopback, build 20348+). Writes a WAV file
/// and reports peak level per buffer for the meter and the silence watch.
/// </summary>
[SupportedOSPlatform("windows10.0.19041")]
public sealed class WasapiCaptureService : ICaptureService, IDisposable
{
    private IWaveIn? _waveIn;
    private ProcessLoopbackCapture? _process;
    private WaveFileWriter? _writer;
    private Stopwatch _clock = new();
    private string? _path;
    private CaptureNotice? _lastNotice;
    private Task<CaptureResult>? _stopping;
    private readonly object _gate = new();

    public bool SupportsAppCapture => ProcessLoopback.IsSupported;
    public bool IsCapturing { get; private set; }

    public event EventHandler<CaptureLevel>? Level;
    public event EventHandler<CaptureNotice>? Notice;

    public Task<IReadOnlyList<AudioDevice>> ListMicrophonesAsync(CancellationToken ct = default)
    {
        using var enumerator = new MMDeviceEnumerator();
        string? defaultId = enumerator.HasDefaultAudioEndpoint(DataFlow.Capture, Role.Communications)
            ? enumerator.GetDefaultAudioEndpoint(DataFlow.Capture, Role.Communications).ID
            : null;
        IReadOnlyList<AudioDevice> list = enumerator.EnumerateAudioEndPoints(DataFlow.Capture, DeviceState.Active)
            .Select(d => new AudioDevice(d.ID, d.FriendlyName, d.ID == defaultId)).ToList();
        return Task.FromResult(list);
    }

    /// <summary>Apps with an audio session on the default output; IsPlaying when the session is active.</summary>
    public Task<IReadOnlyList<AudioApp>> ListAudioAppsAsync(CancellationToken ct = default)
    {
        var apps = new Dictionary<int, AudioApp>();
        using var enumerator = new MMDeviceEnumerator();
        if (enumerator.HasDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia))
        {
            var device = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Multimedia);
            var sessions = device.AudioSessionManager.Sessions;
            for (int i = 0; i < sessions.Count; i++)
            {
                var s = sessions[i];
                int pid = (int)s.GetProcessID;
                if (pid == 0 || pid == Environment.ProcessId) continue;
                string name;
                try { name = Process.GetProcessById(pid).MainModule?.FileVersionInfo.FileDescription ?? Process.GetProcessById(pid).ProcessName; }
                catch (Exception e) when (e is ArgumentException or InvalidOperationException or System.ComponentModel.Win32Exception)
                {
                    name = string.IsNullOrEmpty(s.DisplayName) ? $"Process {pid}" : s.DisplayName;
                }
                bool playing = s.State == NAudio.CoreAudioApi.Interfaces.AudioSessionState.AudioSessionStateActive;
                if (!apps.TryGetValue(pid, out var existing) || playing && !existing.IsPlaying)
                    apps[pid] = new AudioApp(pid, name, playing);
            }
        }
        IReadOnlyList<AudioApp> result = apps.Values.OrderByDescending(a => a.IsPlaying).ThenBy(a => a.Name).ToList();
        return Task.FromResult(result);
    }

    public async Task StartAsync(CaptureRequest request, CancellationToken ct = default)
    {
        if (IsCapturing) throw new InvalidOperationException("Already recording");
        _stopping = null;
        _path = request.OutputPath;
        _lastNotice = null;
        switch (request.Kind)
        {
            case CaptureKind.Microphone:
            {
                MMDevice? device = null;
                if (request.DeviceId is { } id)
                {
                    using var enumerator = new MMDeviceEnumerator();
                    device = enumerator.GetDevice(id);
                }
                var mic = device is null ? new WasapiCapture() : new WasapiCapture(device);
                Attach(mic);
                break;
            }
            case CaptureKind.SystemAudio:
                Attach(new WasapiLoopbackCapture());
                break;
            case CaptureKind.App:
            {
                if (!ProcessLoopback.IsSupported)
                    throw new InvalidOperationException("Recording one app needs Windows 11 or Windows Server 2022 (build 20348).");
                if (request.ProcessId is not { } pid) throw new ArgumentException("No process chosen", nameof(request));
                var capture = new ProcessLoopbackCapture(pid);
                var format = capture.WaveFormat;
                _writer = new WaveFileWriter(_path, format);
                capture.BufferCaptured += (buffer, count, silent) => OnData(buffer, count, silent, format);
                capture.Stopped += e => { if (e is not null) Notice?.Invoke(this, new CaptureNotice(CaptureNoticeKind.NothingPlaying, _clock.Elapsed)); };
                _process = capture;
                _clock = Stopwatch.StartNew();
                await capture.StartAsync(ct).ConfigureAwait(false);
                break;
            }
        }
        IsCapturing = true;
    }

    private void Attach(WasapiCapture capture)
    {
        _writer = new WaveFileWriter(_path!, capture.WaveFormat);
        capture.DataAvailable += (_, e) => OnData(e.Buffer, e.BytesRecorded, false, capture.WaveFormat);
        _waveIn = capture;
        _clock = Stopwatch.StartNew();
        capture.StartRecording();
    }

    private void OnData(byte[] buffer, int count, bool silent, WaveFormat format)
    {
        lock (_gate) _writer?.Write(buffer, 0, count);
        Level?.Invoke(this, new CaptureLevel(_clock.Elapsed, Peak(buffer, count, format), silent));
    }

    private static float Peak(byte[] buffer, int count, WaveFormat format)
    {
        float peak = 0;
        if (format.Encoding == WaveFormatEncoding.IeeeFloat || format is WaveFormatExtensible { SubFormat: var sf } && sf == NAudio.Dmo.AudioMediaSubtypes.MEDIASUBTYPE_IEEE_FLOAT)
        {
            for (int i = 0; i + 3 < count; i += 4) peak = Math.Max(peak, Math.Abs(BitConverter.ToSingle(buffer, i)));
        }
        else if (format.BitsPerSample == 16)
        {
            for (int i = 0; i + 1 < count; i += 2) peak = Math.Max(peak, Math.Abs(BitConverter.ToInt16(buffer, i) / 32768f));
        }
        else if (format.BitsPerSample == 32)
        {
            for (int i = 0; i + 3 < count; i += 4) peak = Math.Max(peak, Math.Abs(BitConverter.ToInt32(buffer, i) / 2147483648f));
        }
        return peak;
    }

    /// <summary>A second stop while the first still waits for the device gets the first one's result.</summary>
    public Task<CaptureResult> StopAsync(CancellationToken ct = default) => _stopping ??= StopCoreAsync(ct);

    private async Task<CaptureResult> StopCoreAsync(CancellationToken ct)
    {
        var waveIn = _waveIn;
        var process = _process;
        _waveIn = null;
        _process = null;
        WaveFormat? format = null;
        if (waveIn is not null)
        {
            var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            waveIn.RecordingStopped += (_, _) => done.TrySetResult();
            format = waveIn.WaveFormat;
            waveIn.StopRecording();
            // RecordingStopped comes through the UI thread's context: wait without holding that thread.
            await StopWait.WithinAsync(done.Task, StopWait.Limit, ct).ConfigureAwait(false);
            waveIn.Dispose();
        }
        if (process is not null && ProcessLoopback.IsSupported)
        {
            format = process.WaveFormat;
            process.Dispose();
        }
        TimeSpan duration;
        lock (_gate)
        {
            duration = _writer?.TotalTime ?? TimeSpan.Zero;
            _writer?.Dispose();
            _writer = null;
        }
        IsCapturing = false;
        return new CaptureResult(_path ?? "", duration, format?.SampleRate ?? 0, format?.Channels ?? 0, _lastNotice);
    }

    public void Dispose()
    {
        if (IsCapturing) StopAsync().GetAwaiter().GetResult();
    }
}
