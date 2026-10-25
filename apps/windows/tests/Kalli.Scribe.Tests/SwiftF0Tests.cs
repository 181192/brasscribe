using System.Diagnostics;
using Brasscribe.Play.Core.OnDevice;
using Xunit.Abstractions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>SwiftF0 ONNX on the CPU execution provider (the same code path uses DirectML on Windows).</summary>
public class SwiftF0Tests(ITestOutputHelper log)
{
    private static float[] Sine(double hz, double seconds, float amp = 0.3f) =>
        Enumerable.Range(0, (int)(seconds * SwiftF0Detector.SampleRate))
            .Select(i => (float)(amp * Math.Sin(2 * Math.PI * hz * i / SwiftF0Detector.SampleRate))).ToArray();

    [SkippableTheory]
    [InlineData("models/converted/swift-f0/swift-f0-stream.onnx", 440.0)]
    [InlineData("models/converted/swift-f0/swift-f0-stream.onnx", 233.08)] // B-flat 3
    [InlineData("models/converted/swift-f0/swift-f0-window.onnx", 440.0)]
    public void Detects_a_sine(string model, double hz)
    {
        var path = TestPaths.RepoFile(model);
        Skip.If(path is null, TestPaths.Missing(model));
        using var det = new SwiftF0Detector(path, preferGpu: false);
        Assert.Equal(ExecutionTarget.Cpu, det.Target);

        var audio = Sine(hz, 3.0);
        var sw = Stopwatch.StartNew();
        var frames = det.Detect(audio);
        sw.Stop();

        Assert.Equal((audio.Length + 255) / 256, frames.Count);
        var inner = frames.Where(f => f.TimeS > 0.2 && f.TimeS < 2.8).ToList();
        double voiced = inner.Count(f => f.Voiced) / (double)inner.Count;
        var cents = inner.Where(f => f.Voiced).Select(f => 1200 * Math.Log2(f.Hz / hz)).Order().ToList();
        double median = cents[cents.Count / 2];
        log.WriteLine($"swiftf0 {Path.GetFileName(path)} {hz} Hz: {frames.Count} frames in {sw.ElapsedMilliseconds} ms, voiced {voiced:P0}, median error {median:0.0} cents");
        Assert.True(voiced > 0.9, $"voiced share {voiced:P0}");
        Assert.InRange(median, -20, 20);
    }

    [SkippableFact]
    public void Silence_is_unvoiced()
    {
        var path = TestPaths.RepoFile(TestPaths.SwiftF0Stream);
        Skip.If(path is null, TestPaths.Missing(TestPaths.SwiftF0Stream));
        using var det = new SwiftF0Detector(path, preferGpu: false);
        var frames = det.Detect(new float[SwiftF0Detector.SampleRate]);
        Assert.All(frames, f => Assert.False(f.Voiced));
    }
}
