namespace Brasscribe.Bandroom.Core.Supervisor;

/// <summary>
/// Bandroom's side of an environment's lock file (<see cref="BandroomPaths.EnvironmentLocks"/>), the one the engine
/// holds while a stage uses that environment (scribe_engine/envlock.py): opened with no sharing, so it is had only
/// when no stage has the file open, and no stage can open it until it is let go. The system lets it go when Bandroom
/// ends.
/// </summary>
public static class EnvironmentLock
{
    /// <summary>Waits until no stage uses the environment, then holds it until disposed.</summary>
    public static async Task<FileStream> HoldAsync(string path, CancellationToken ct, TimeSpan? poll = null)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                return new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            }
            catch (IOException)
            {
                await Task.Delay(poll ?? TimeSpan.FromMilliseconds(250), ct).ConfigureAwait(false);
            }
        }
    }
}
