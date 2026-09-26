using Brasscribe.Play.Core.Engine;

namespace Brasscribe.Play.Core.Arrangement;

/// <summary>
/// Fetches the layered arranger's inputs from an engine job's stage files and keeps them in a local
/// folder per job, so later re-arrangements of the same recording read them from disk.
/// </summary>
public static class EngineLayerSource
{
    /// <summary>The layer inputs of a job, or null when the job's pipeline has no layered stages.</summary>
    public static async Task<LayerInputs?> LoadAsync(IEngineClient engine, string jobId, string cacheRoot, CancellationToken ct = default)
    {
        string dir = Path.Combine(cacheRoot, string.Concat(jobId.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c)));
        string complete = Path.Combine(dir, ".complete");
        if (File.Exists(complete) && LayerInputs.FromDirectory(dir) is { } cached) return cached;

        var stages = await engine.ListStagesAsync(jobId, ct).ConfigureAwait(false);
        var where = new Dictionary<string, string>();
        foreach (var stage in stages)
            foreach (var file in stage.Files)
                if (LayerInputs.FileNames.Contains(file.Name)) where.TryAdd(file.Name, stage.Stage);
        if (!LayerInputs.MidiNames.Append(LayerInputs.BeatsName).All(where.ContainsKey)) return null;

        Directory.CreateDirectory(dir);
        foreach (var (name, stage) in where)
        {
            string target = Path.Combine(dir, name);
            string partial = target + ".partial";
            await using (var src = await engine.GetStageFileAsync(jobId, stage, name, ct).ConfigureAwait(false))
            await using (var dst = File.Create(partial))
                await src.CopyToAsync(dst, ct).ConfigureAwait(false);
            File.Move(partial, target, overwrite: true);
        }
        await File.WriteAllTextAsync(complete, "", ct).ConfigureAwait(false);
        return LayerInputs.FromDirectory(dir);
    }
}
