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
    public static (InferenceSession Session, ExecutionTarget Target) Create(string modelPath, bool preferGpu = true, int deviceId = 0)
    {
        if (preferGpu && OperatingSystem.IsWindows())
        {
            var dml = new SessionOptions
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
                dml.Dispose();
            }
        }
        var cpu = new SessionOptions { GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL };
        return (new InferenceSession(modelPath, cpu), ExecutionTarget.Cpu);
    }
}
