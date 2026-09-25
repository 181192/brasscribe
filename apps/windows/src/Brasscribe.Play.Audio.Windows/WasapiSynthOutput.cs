using System.Runtime.Versioning;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using NAudio.CoreAudioApi;
using NAudio.Wave;

namespace Brasscribe.Play.Audio.Windows;

/// <summary>Plays the alphaTab synth buffer through WASAPI shared mode on the default output device.</summary>
[SupportedOSPlatform("windows10.0.19041")]
public sealed class WasapiSynthOutput : IAudioOutput
{
    private WasapiOut? _out;

    public void Start(BufferedSynthOutput source)
    {
        Stop();
        _out = new WasapiOut(AudioClientShareMode.Shared, useEventSync: true, latency: 80);
        _out.Init(new SynthSampleProvider(source));
        _out.Play();
    }

    public void Stop()
    {
        _out?.Stop();
        _out?.Dispose();
        _out = null;
    }

    public void Dispose() => Stop();

    private sealed class SynthSampleProvider(BufferedSynthOutput source) : ISampleProvider
    {
        public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat((int)source.SampleRate, 2);

        public int Read(float[] buffer, int offset, int count) => source.Read(buffer.AsSpan(offset, count));
    }
}
