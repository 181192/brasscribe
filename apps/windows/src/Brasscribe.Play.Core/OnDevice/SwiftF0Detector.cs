using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;

namespace Brasscribe.Play.Core.OnDevice;

/// <summary>One pitch frame: time of the frame, f0 in Hz and a voicing confidence (voiced at ≥ 0.5).</summary>
public readonly record struct PitchFrame(double TimeS, double Hz, float Confidence)
{
    public bool Voiced => Confidence >= SwiftF0Detector.VoicedThreshold;
    public double Midi => 69 + 12 * Math.Log2(Hz / 440.0);
}

/// <summary>
/// SwiftF0 pitch detection on ONNX Runtime with the static-shape models from models/convert
/// (swift-f0-window.onnx: one 30.3 s window; swift-f0-stream.onnx: 128 frames, 2.05 s).
/// Audio is mono float at 16 kHz. Each frame needs 11 frames of left context and 10 of lookahead;
/// the detector slides the model over the audio so every frame is computed with that context.
/// Constants follow swift_f0.core (HOP 256, FMIN 46.875, FMAX 2093.75, SILENCE_PEAK 1e-3).
/// </summary>
public sealed class SwiftF0Detector : IDisposable
{
    public const int SampleRate = 16000;
    public const int Hop = 256;
    public const int LeftFrames = 11;
    public const int LookaheadFrames = 10;
    public const double FMin = 46.875;
    public const double FMax = 2093.75;
    public const float VoicedThreshold = 0.5f;
    public const float SilencePeak = 1e-3f;

    private readonly InferenceSession _session;
    private readonly int _inputSamples;
    private readonly int _outputFrames;

    public SwiftF0Detector(string modelPath, bool preferGpu = true)
    {
        (_session, Target) = OnnxSessions.Create(modelPath, preferGpu);
        var shape = _session.InputMetadata["audio"].Dimensions;
        _inputSamples = shape[^1];
        _outputFrames = _session.OutputMetadata["confidence"].Dimensions[^1];
        if (_inputSamples <= 0) throw new ArgumentException("SwiftF0 model must have a static audio length", nameof(modelPath));
    }

    public ExecutionTarget Target { get; }
    /// <summary>Frames each model call finalises (the output minus the context on both sides).</summary>
    public int FramesPerCall => _outputFrames - LeftFrames - LookaheadFrames;

    public IReadOnlyList<PitchFrame> Detect(ReadOnlySpan<float> audio16k, double fmin = FMin, double fmax = FMax)
    {
        int totalFrames = (audio16k.Length + Hop - 1) / Hop;
        var frames = new List<PitchFrame>(totalFrames);
        var input = new DenseTensor<float>([1, _inputSamples]);
        var fminT = new DenseTensor<float>(new[] { (float)Math.Max(FMin, fmin) }, ReadOnlySpan<int>.Empty);
        var fmaxT = new DenseTensor<float>(new[] { (float)Math.Min(FMax, fmax) }, ReadOnlySpan<int>.Empty);

        for (int first = 0; first < totalFrames; first += FramesPerCall)
        {
            int start = (first - LeftFrames) * Hop;
            var span = input.Buffer.Span;
            for (int i = 0; i < _inputSamples; i++)
            {
                int s = start + i;
                span[i] = s >= 0 && s < audio16k.Length ? audio16k[s] : 0f;
            }
            using var results = _session.Run([
                NamedOnnxValue.CreateFromTensor("audio", input),
                NamedOnnxValue.CreateFromTensor("fmin", fminT),
                NamedOnnxValue.CreateFromTensor("fmax", fmaxT),
            ]);
            var pitch = results.First(r => r.Name == "pitch");
            var conf = results.First(r => r.Name == "confidence").AsTensor<float>();
            int count = Math.Min(FramesPerCall, totalFrames - first);
            for (int k = 0; k < count; k++)
            {
                int outIndex = LeftFrames + k;
                int frame = first + k;
                double hz = pitch.ElementType == TensorElementType.Double
                    ? pitch.AsTensor<double>()[0, outIndex]
                    : pitch.AsTensor<float>()[0, outIndex];
                float c = conf[0, outIndex];
                if (Peak(audio16k, frame) < SilencePeak) c = 0f;
                frames.Add(new PitchFrame(frame * (double)Hop / SampleRate, hz, c));
            }
        }
        return frames;
    }

    /// <summary>Peak level of the 32 ms of audio centred on a frame.</summary>
    private static float Peak(ReadOnlySpan<float> audio, int frame)
    {
        int centre = frame * Hop, half = 256;
        int a = Math.Max(0, centre - half), b = Math.Min(audio.Length, centre + half);
        float peak = 0;
        for (int i = a; i < b; i++) peak = Math.Max(peak, Math.Abs(audio[i]));
        return peak;
    }

    public void Dispose() => _session.Dispose();
}
