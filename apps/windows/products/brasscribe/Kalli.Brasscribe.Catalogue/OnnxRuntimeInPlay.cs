using System.Reflection;
using Kalli.Scribe.OnDevice;
using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Kalli.Brasscribe.Catalogue;

/// <summary>
/// Play's own build, with the files it ships, runs a model on DirectML with the ONNX Runtime it pins: not another
/// package's copy of onnxruntime.dll (the Windows App SDK's Windows ML once brought one, which took the place of
/// ours). The model is Fixtures/twice-plus-one.onnx: y = 2 x + 1, written by make_twice_plus_one.py beside it. Not a
/// screen: CI runs this class on its own (windows.yml, "Play runs a model on DirectML").
/// </summary>
[TestClass]
public sealed class OnnxRuntimeInPlay
{
    private static string Model => Path.Combine(AppContext.BaseDirectory, "Catalogue", "twice-plus-one.onnx");

    [TestMethod]
    public void The_native_runtime_is_the_version_of_its_managed_library()
    {
        var managed = typeof(OrtEnv).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
            .Split('+')[0];
        Assert.AreEqual(managed, OrtEnv.Instance().GetVersionString(), "the app's onnxruntime.dll is not the build of Microsoft.ML.OnnxRuntime it pins");
    }

    /// <summary>What DirectML says when a session cannot have it (OnnxSessions falls back to the CPU without a word).</summary>
    private static string WhyNotDirectMl()
    {
        try
        {
            using var options = new SessionOptions { ExecutionMode = ExecutionMode.ORT_SEQUENTIAL, EnableMemoryPattern = false };
            options.AppendExecutionProvider_DML(0);
            using var session = new InferenceSession(Model, options);
            return "a second try worked";
        }
        catch (Exception e)
        {
            return $"{e.GetType().Name}: {e.Message}";
        }
    }

    [TestMethod]
    public void A_model_runs_on_DirectML()
    {
        var (session, target) = OnnxSessions.Create(Model, preferGpu: true);
        using (session)
        {
            Assert.AreEqual(ExecutionTarget.DirectMl, target, $"the session fell back to the CPU: {WhyNotDirectMl()}");
            var x = new DenseTensor<float>(new float[] { 0, 1, 2.5f, -3 }, new[] { 1, 4 });
            using var results = session.Run([NamedOnnxValue.CreateFromTensor("x", x)]);
            CollectionAssert.AreEqual(new float[] { 1, 3, 6, -5 }, results.First().AsEnumerable<float>().ToArray());
        }
    }
}
