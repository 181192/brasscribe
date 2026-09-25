using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using Brasscribe.Play.Audio.Windows.Interop;
using NAudio.Wave;

namespace Brasscribe.Play.Audio.Windows;

/// <summary>Whether this Windows build has process loopback (Windows 11, Windows Server 2022, build 20348+).</summary>
public static class ProcessLoopback
{
    [SupportedOSPlatformGuard("windows10.0.20348")]
    public static bool IsSupported => OperatingSystem.IsWindowsVersionAtLeast(10, 0, 20348);
}

/// <summary>
/// Records one process and its children with WASAPI process loopback: ActivateAudioInterfaceAsync
/// on the virtual "VAD\Process_Loopback" device with AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK.
/// Follows Microsoft's ApplicationLoopback sample: the process-loopback client has no mix format,
/// so it is initialised with an explicit PCM format and AUTOCONVERTPCM, event-driven, 200 ms buffer.
/// Protected (DRM) streams arrive as silent buffers, which is reported through
/// <see cref="BufferCaptured"/>'s silent flag instead of being hidden.
/// </summary>
[SupportedOSPlatform("windows10.0.20348")]
public sealed class ProcessLoopbackCapture : IDisposable
{
    public const int MinimumBuild = 20348;

    private readonly int _processId;
    private readonly bool _includeTree;
    private IAudioClient? _client;
    private IAudioCaptureClient? _capture;
    private nint _event;
    private Thread? _thread;
    private volatile bool _stop;

    public ProcessLoopbackCapture(int processId, bool includeProcessTree = true, int sampleRate = 48000, int channels = 2)
    {
        _processId = processId;
        _includeTree = includeProcessTree;
        WaveFormat = new WaveFormat(sampleRate, 16, channels);
    }

    public WaveFormat WaveFormat { get; }

    /// <summary>Raised on the capture thread with PCM bytes and whether the engine flagged the buffer silent.</summary>
    public event Action<byte[], int, bool>? BufferCaptured;

    public event Action<Exception?>? Stopped;

    public async Task StartAsync(CancellationToken ct = default)
    {
        _client = await ActivateAsync(_processId, _includeTree, ct).ConfigureAwait(false);

        var format = WaveFormatEx.Pcm16(WaveFormat.SampleRate, WaveFormat.Channels);
        const long bufferDuration = 2_000_000; // 200 ms in 100-ns units
        Check(_client.Initialize(AudioConstants.AUDCLNT_SHAREMODE_SHARED,
            AudioConstants.AUDCLNT_STREAMFLAGS_LOOPBACK | AudioConstants.AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AudioConstants.AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
            bufferDuration, 0, ref format, 0), "IAudioClient.Initialize");

        var iid = AudioConstants.IID_IAudioCaptureClient;
        Check(_client.GetService(ref iid, out var service), "IAudioClient.GetService");
        _capture = (IAudioCaptureClient)service;

        _event = NativeMethods.CreateEvent(0, false, false, null);
        if (_event == 0) throw new InvalidOperationException("CreateEvent failed");
        Check(_client.SetEventHandle(_event), "IAudioClient.SetEventHandle");
        Check(_client.Start(), "IAudioClient.Start");

        _stop = false;
        _thread = new Thread(CaptureLoop) { IsBackground = true, Name = "Process loopback capture", Priority = ThreadPriority.AboveNormal };
        _thread.Start();
    }

    public void Stop()
    {
        _stop = true;
        _thread?.Join(2000);
        _thread = null;
        _client?.Stop();
    }

    private void CaptureLoop()
    {
        Exception? error = null;
        int blockAlign = WaveFormat.BlockAlign;
        var scratch = new byte[WaveFormat.AverageBytesPerSecond];
        try
        {
            while (!_stop)
            {
                if (NativeMethods.WaitForSingleObject(_event, 200) != NativeMethods.WAIT_OBJECT_0) continue;
                while (true)
                {
                    Check(_capture!.GetNextPacketSize(out uint packet), "GetNextPacketSize");
                    if (packet == 0) break;
                    Check(_capture.GetBuffer(out nint data, out uint frames, out uint flags, out _, out _), "GetBuffer");
                    int bytes = (int)frames * blockAlign;
                    if (bytes > scratch.Length) scratch = new byte[bytes];
                    bool silent = (flags & AudioConstants.AUDCLNT_BUFFERFLAGS_SILENT) != 0;
                    if (silent) Array.Clear(scratch, 0, bytes);
                    else Marshal.Copy(data, scratch, 0, bytes);
                    Check(_capture.ReleaseBuffer(frames), "ReleaseBuffer");
                    BufferCaptured?.Invoke(scratch, bytes, silent);
                }
            }
        }
        catch (Exception e) when (e is COMException or InvalidOperationException)
        {
            error = e;
        }
        Stopped?.Invoke(error);
    }

    private static async Task<IAudioClient> ActivateAsync(int processId, bool includeTree, CancellationToken ct)
    {
        var parameters = new AudioClientActivationParams
        {
            ActivationType = AudioClientActivationType.ProcessLoopback,
            TargetProcessId = (uint)processId,
            ProcessLoopbackMode = includeTree ? ProcessLoopbackMode.IncludeTargetProcessTree : ProcessLoopbackMode.ExcludeTargetProcessTree,
        };
        int size = Marshal.SizeOf<AudioClientActivationParams>();
        nint blob = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(parameters, blob, false);
            var variant = new PropVariantBlob { vt = AudioConstants.VT_BLOB, cbSize = (uint)size, pBlobData = blob };
            var handler = new ActivationHandler();
            var iid = AudioConstants.IID_IAudioClient;
            Check(NativeMethods.ActivateAudioInterfaceAsync(AudioConstants.VirtualProcessLoopbackDevice, ref iid, ref variant, handler, out _),
                "ActivateAudioInterfaceAsync");
            using (ct.Register(() => handler.Completion.TrySetCanceled(ct)))
                return await handler.Completion.Task.ConfigureAwait(false);
        }
        finally
        {
            // The activation call copies the parameters before returning.
            Marshal.FreeHGlobal(blob);
        }
    }

    private static void Check(int hr, string what)
    {
        if (hr < 0) throw new COMException($"{what} failed (0x{hr:X8})", hr);
    }

    public void Dispose()
    {
        Stop();
        if (_event != 0) NativeMethods.CloseHandle(_event);
        _event = 0;
        if (_capture is not null) Marshal.ReleaseComObject(_capture);
        if (_client is not null) Marshal.ReleaseComObject(_client);
        _capture = null;
        _client = null;
    }

    /// <summary>Completion handler for the asynchronous activation; agile, as the API requires.</summary>
    [ComVisible(true)]
    private sealed class ActivationHandler : IActivateAudioInterfaceCompletionHandler, IAgileObject
    {
        public TaskCompletionSource<IAudioClient> Completion { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public void ActivateCompleted(IActivateAudioInterfaceAsyncOperation operation)
        {
            int hr = operation.GetActivateResult(out int result, out object unknown);
            if (hr < 0 || result < 0)
            {
                Completion.TrySetException(new COMException("Process loopback activation failed", hr < 0 ? hr : result));
                return;
            }
            Completion.TrySetResult((IAudioClient)unknown);
        }
    }
}
