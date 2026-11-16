using System.Reflection;
using Kalli.Scribe.OnDevice;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Kalli.Brasscribe.Catalogue;

/// <summary>
/// Play's own build, with the files it ships, runs a model with the ONNX Runtime it pins, built with DirectML: not
/// another package's copy of onnxruntime.dll (the Windows App SDK's Windows ML once brought one, which took the place
/// of ours). The model is Fixtures/twice-plus-one.onnx: y = 2 x + 1, written by make_twice_plus_one.py beside it. Not a
/// screen: CI runs this class on its own (windows.yml, "Play runs a model on DirectML").
/// </summary>
/// <remarks>
/// DirectML needs a display adapter. GitHub's Windows runners have none, so there DirectML stops at the adapter
/// (ERROR_GRAPHICS_INVALID_DISPLAY_ADAPTER) and the model runs on the CPU: the DirectML test is inconclusive there,
/// and says so. On a PC with a graphics adapter it must run on DirectML.
/// </remarks>
[TestClass]
public sealed class OnnxRuntimeInPlay
{
    /// <summary>ERROR_GRAPHICS_INVALID_DISPLAY_ADAPTER: Windows has no display adapter for DirectML to use.</summary>
    private const string NoDisplayAdapter = "C0262002";

    private static string Model => Path.Combine(AppContext.BaseDirectory, "Catalogue", "twice-plus-one.onnx");

    private static readonly float[] X = [0, 1, 2.5f, -3];
    private static readonly float[] Y = [1, 3, 6, -5];

    private static float[] Run(InferenceSession session)
    {
        using var results = session.Run([NamedOnnxValue.CreateFromTensor("x", new DenseTensor<float>(X, [1, 4]))]);
        return results.First().AsEnumerable<float>().ToArray();
    }

    [TestMethod]
    public void The_native_runtime_is_the_version_of_its_managed_library()
    {
        var managed = typeof(OrtEnv).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
            .Split('+')[0];
        Assert.AreEqual(managed, OrtEnv.Instance().GetVersionString(), "the app's onnxruntime.dll is not the build of Microsoft.ML.OnnxRuntime it pins");
    }

    [TestMethod]
    public void The_runtime_is_built_with_DirectML()
    {
        CollectionAssert.Contains(OrtEnv.Instance().GetAvailableProviders(), "DmlExecutionProvider");
    }

    [TestMethod]
    public void A_model_runs_and_on_DirectML_where_Windows_has_a_display_adapter()
    {
        var (session, target) = OnnxSessions.Create(Model, preferGpu: true);
        using (session)
        {
            CollectionAssert.AreEqual(Y, Run(session));
            if (target == ExecutionTarget.DirectMl) return;
            var why = OnnxSessions.DirectMlUnavailable ?? "";
            if (why.Contains(NoDisplayAdapter, StringComparison.Ordinal))
                Assert.Inconclusive($"no display adapter here, so the model ran on the CPU: {why}");
            Assert.Fail($"the session fell back to the CPU: {why}");
        }
    }
}
