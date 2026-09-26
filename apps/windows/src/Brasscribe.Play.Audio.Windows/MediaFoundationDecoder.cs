using System.Runtime.Versioning;
using Brasscribe.Play.Core.Capture;
using NAudio.MediaFoundation;
using NAudio.Wave;

namespace Brasscribe.Play.Audio.Windows;

/// <summary>
/// Decodes audio files and the audio track of video files with Media Foundation (the codecs Windows
/// has: MP3, AAC/M4A, WMA, FLAC, ALAC, MP4/MOV/WMV video) to 16-bit PCM WAV for the engine.
/// </summary>
[SupportedOSPlatform("windows10.0.19041")]
public sealed class MediaFoundationDecoder : IMediaDecoder
{
    static MediaFoundationDecoder() => MediaFoundationApi.Startup();

    public Task<DecodedMedia> DecodeToWavAsync(string inputPath, string outputPath, int? sampleRate = null, CancellationToken ct = default) =>
        Task.Run(() =>
        {
            using var reader = new MediaFoundationReader(inputPath);
            IWaveProvider source = reader;
            int rate = sampleRate ?? reader.WaveFormat.SampleRate;
            MediaFoundationResampler? resampler = null;
            if (reader.WaveFormat.SampleRate != rate || reader.WaveFormat.BitsPerSample != 16 || reader.WaveFormat.Encoding != WaveFormatEncoding.Pcm)
            {
                resampler = new MediaFoundationResampler(reader, new WaveFormat(rate, 16, reader.WaveFormat.Channels)) { ResamplerQuality = 60 };
                source = resampler;
            }
            try
            {
                using var writer = new WaveFileWriter(outputPath, source.WaveFormat);
                var buffer = new byte[source.WaveFormat.AverageBytesPerSecond];
                int read;
                while ((read = source.Read(buffer, 0, buffer.Length)) > 0)
                {
                    ct.ThrowIfCancellationRequested();
                    writer.Write(buffer, 0, read);
                }
            }
            finally
            {
                resampler?.Dispose();
            }
            return new DecodedMedia(outputPath, reader.TotalTime, Brasscribe.Play.Core.Capture.MediaTypes.Classify(inputPath) == MediaKind.Video, rate, reader.WaveFormat.Channels);
        }, ct);
}
