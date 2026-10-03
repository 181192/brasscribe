using Microsoft.ML.OnnxRuntime;

namespace Brasscribe.Play.Core.OnDevice;

public enum ExecutionTarget { Cpu, DirectMl }

/// <summary>
/// Creates ONNX Runtime sessions. On Windows the app ships the DirectML build of ONNX Runtime, so
/// DirectML (any DirectX 12 GPU) is tried first and the CPU provider is the fallback; elsewhere the
/// CPU provider is used. Which one ran is reported so the UI and manifests can say so.
/// </summary>
public static class OnnxSessions
{
    private static readonly Lazy<bool> Quiet = new(() =>
    {
        // ONNX Runtime on Windows reports to Microsoft through ETW, which Windows collects as the computer's
        // diagnostic data setting allows. This turns its events off before the first session. Its first event,
        // when the runtime starts, comes before this call can, and an ETW session that enables the runtime's
        // provider later turns its events on again.
        OrtEnv.Instance().DisableTelemetryEvents();
        return true;
    });

    /// <remarks>The session keeps what it needs from its options, so they are released once it exists.</remarks>
    public static (InferenceSession Session, ExecutionTarget Target) Create(string modelPath, bool preferGpu = true, int deviceId = 0)
    {
        _ = Quiet.Value;
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
