using Microsoft.ML.OnnxRuntime;

namespace Kalli.Scribe.OnDevice;

public enum ExecutionTarget { Cpu, DirectMl }

/// <summary>
/// Creates ONNX Runtime sessions. On Windows the app ships the DirectML build of ONNX Runtime, so
/// DirectML (any DirectX 12 GPU) is tried first and the CPU provider is the fallback; elsewhere the
/// CPU provider is used. Which one ran is reported so the UI and manifests can say so.
/// </summary>
/// <remarks>
/// Every session is made here, with ONNX Runtime's telemetry events switched off first. On Windows the runtime writes
/// its events to ETW for Windows' diagnostic data; switched off, it writes none. Its switch is per process and does
/// not last against Windows itself: when a Windows trace session turns the runtime's ETW provider on, the runtime
/// turns its events back on. So it is switched off again before every session.
/// </remarks>
public static class OnnxSessions
{
    /// <summary>Switches ONNX Runtime's telemetry events off, for this process. Makes the runtime's environment.</summary>
    public static void TelemetryOff() => OrtEnv.Instance().DisableTelemetryEvents();

    /// <remarks>The session keeps what it needs from its options, so they are released once it exists.</remarks>
    public static (InferenceSession Session, ExecutionTarget Target) Create(string modelPath, bool preferGpu = true, int deviceId = 0)
    {
        TelemetryOff();
        if (preferGpu && OperatingSystem.IsWindows())
        {
            using var dml = new SessionOptions
            {
                // DirectML requires sequential execution and no memory pattern.
                ExecutionMode = ExecutionMode.ORT_SEQUENTIAL,
                EnableMemoryPattern = false,
                GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL,
            };
            try
            {
                dml.AppendExecutionProvider_DML(deviceId);
                return (new InferenceSession(modelPath, dml), ExecutionTarget.DirectMl);
            }
            catch (Exception e) when (e is OnnxRuntimeException or EntryPointNotFoundException or DllNotFoundException or NotSupportedException)
            {
                // No DirectML here: the CPU provider below.
            }
        }
        using var cpu = new SessionOptions { GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL };
        return (new InferenceSession(modelPath, cpu), ExecutionTarget.Cpu);
    }
}
