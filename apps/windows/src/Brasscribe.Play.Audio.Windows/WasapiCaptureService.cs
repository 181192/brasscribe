using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using Brasscribe.Play.Core.Capture;
using NAudio.CoreAudioApi;
using NAudio.Wave;

namespace Brasscribe.Play.Audio.Windows;

/// <summary>
/// <see cref="ICaptureService"/> on WASAPI: microphone (shared-mode capture), everything the default
/// output plays (endpoint loopback) and one app (process loopback, build 20348+). Writes a WAV file
/// and reports peak level per buffer for the meter and the silence watch. Loopback gets no audio
/// while nothing plays, so silence is written for those stretches (<see cref="LoopbackGap"/>). A
/// recording that stops by itself (device unplugged, disk full) is said at once, and what was
/// recorded until then is kept.
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
    private TaskCompletionSource? _stopped;
    private Timer? _gapTimer;
    private WaveFormat? _gapFormat;
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
        _stopped = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        try
        {
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
                    StartGapFill(_waveIn!.WaveFormat);
                    break;
                case CaptureKind.App:
                {
                    if (!ProcessLoopback.IsSupported)
                        throw new InvalidOperationException("Recording one app needs Windows 11 or Windows Server 2022 (build 20348).");
                    if (request.ProcessId is not { } pid) throw new ArgumentException("No process chosen", nameof(request));
                    var capture = new ProcessLoopbackCapture(pid);
                    var format = capture.WaveFormat;
                    _process = capture;
                    _writer = new WaveFileWriter(_path, format);
                    capture.BufferCaptured += (buffer, count, silent) => OnData(buffer, count, silent, format);
                    capture.Stopped += e =>
                    {
                        _stopped?.TrySetResult();
                        if (e is null) return;
                        StopGapFill(); // nothing more is recorded: no silence after the end
                        // The app closing ends its audio (a COM error); anything else stopped the recording itself.
                        Say(e is COMException ? CaptureNoticeKind.NothingPlaying : CaptureNoticeKind.Interrupted);
                    };
                    _clock = Stopwatch.StartNew();
                    await capture.StartAsync(ct).ConfigureAwait(false);
                    StartGapFill(format);
                    break;
                }
            }
        }
        catch
        {
            // Nothing is recording: close what was opened and leave no empty file behind.
            Abandon();
            throw;
        }
        IsCapturing = true;
    }

    private void Attach(WasapiCapture capture)
    {
        _waveIn = capture;
        _writer = new WaveFileWriter(_path!, capture.WaveFormat);
        capture.DataAvailable += (_, e) => OnData(e.Buffer, e.BytesRecorded, false, capture.WaveFormat);
        // Also when the device goes away mid-take: then it comes with the reason, and is said at once.
        capture.RecordingStopped += (_, e) =>
        {
            _stopped?.TrySetResult();
            if (e.Exception is null) return;
            StopGapFill(); // nothing more is recorded: no silence after the end
            Say(CaptureNoticeKind.Interrupted);
        };
        _clock = Stopwatch.StartNew();
        capture.StartRecording();
    }

    private void Say(CaptureNoticeKind kind)
    {
        var notice = new CaptureNotice(kind, _clock.Elapsed);
        _lastNotice = notice;
        Notice?.Invoke(this, notice);
    }

    /// <summary>A start that failed: every device object and the file are released, and the file deleted.</summary>
    private void Abandon()
    {
        StopGapFill();
        try { _waveIn?.Dispose(); }
        catch (Exception e) when (e is COMException or InvalidOperationException) { }
        _waveIn = null;
        if (_process is not null && ProcessLoopback.IsSupported) _process.Dispose();
        _process = null;
        lock (_gate)
        {
            _writer?.Dispose();
            _writer = null;
        }
        try { if (_path is not null) File.Delete(_path); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        _stopped = null;
    }

    private void OnData(byte[] buffer, int count, bool silent, WaveFormat format)
    {
        lock (_gate) _writer?.Write(buffer, 0, count);
        Level?.Invoke(this, new CaptureLevel(_clock.Elapsed, Peak(buffer, count, format), silent));
    }

    private void StartGapFill(WaveFormat format)
    {
        _gapFormat = format;
        _gapTimer = new Timer(_ => FillGap(), null, TimeSpan.FromMilliseconds(100), TimeSpan.FromMilliseconds(100));
    }

    private void StopGapFill()
    {
        Interlocked.Exchange(ref _gapTimer, null)?.Dispose();
    }

    /// <summary>On a timer: silence for the time loopback delivered nothing, and a silent level for the meter and the silence watch.</summary>
    private void FillGap()
    {
        TimeSpan at;
        try
        {
            lock (_gate)
            {
                if (_writer is null || _gapFormat is not { } format) return;
                at = _clock.Elapsed;
                long frames = LoopbackGap.FramesToFill(at, _writer.Length / format.BlockAlign, format.SampleRate);
                if (frames <= 0) return;
                var zeros = new byte[Math.Min(frames, format.SampleRate) * format.BlockAlign];
                for (long left = frames; left > 0; left -= zeros.Length / format.BlockAlign)
                    _writer.Write(zeros, 0, (int)Math.Min(zeros.Length, left * format.BlockAlign));
            }
        }
        catch (Exception e) when (e is IOException or ObjectDisposedException or UnauthorizedAccessException)
        {
            StopGapFill();
            Say(CaptureNoticeKind.Interrupted);
            return;
        }
        Level?.Invoke(this, new CaptureLevel(at, 0, true));
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
        StopGapFill();
        WaveFormat? format = null;
        if (waveIn is not null)
        {
            var done = _stopped?.Task ?? Task.CompletedTask;
            format = waveIn.WaveFormat;
            // Stopped already when the device went away mid-take: then there is nothing to wait for.
            if (!done.IsCompleted) waveIn.StopRecording();
            // RecordingStopped comes through the UI thread's context: wait without holding that thread.
            await StopWait.WithinAsync(done, StopWait.Limit, ct).ConfigureAwait(false);
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
