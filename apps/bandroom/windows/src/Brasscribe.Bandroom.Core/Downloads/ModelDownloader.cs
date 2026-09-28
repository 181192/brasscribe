using System.Net.Http.Headers;
using System.Security.Cryptography;

namespace Brasscribe.Bandroom.Core.Downloads;

/// <summary>Why the model download stopped, each with its own words and fix.</summary>
public abstract record DownloadError
{
    private DownloadError() { }

    /// <summary>The band writer needs the user's own Hugging Face key, and there is none.</summary>
    public sealed record KeyMissing : DownloadError;
    /// <summary>Hugging Face answered 401: the key was deleted, expired or mistyped.</summary>
    public sealed record KeyRefused : DownloadError;
    /// <summary>Hugging Face answered 403: signed in, but the licence isn't accepted on the model page yet.</summary>
    public sealed record LicenceNotAccepted : DownloadError;
    public sealed record NotEnoughSpace(long NeededBytes, long FreeBytes) : DownloadError;
    /// <summary>The finished file isn't what upstream published; it was deleted, so trying again starts it afresh.</summary>
    public sealed record ChecksumMismatch(string File) : DownloadError;
    public sealed record Http(int Status, string File) : DownloadError;
    public sealed record Network(string Message) : DownloadError;
    public sealed record Disk(string Message) : DownloadError;
}

/// <summary>Carries a <see cref="DownloadError"/> out of the run.</summary>
internal sealed class DownloadException(DownloadError error) : Exception(error.ToString())
{
    public DownloadError Error { get; } = error;
}

public enum DownloadPhase
{
    Idle,
    /// <summary>The key and the free space, before any large file.</summary>
    Checking,
    Downloading,
    Paused,
    Done,
    Failed,
}

/// <summary>
/// Fetches the missing components (<see cref="ModelCatalog"/>) from their original release URLs into the models
/// folder and the Hugging Face hub cache. Resumable: a stopped or paused file stays as <c>&lt;name&gt;.part</c> and
/// continues with an HTTP Range request. Checks the free space first and each file's size and SHA-256 when it's
/// complete. The Hugging Face key goes to huggingface.co only: redirects are followed here, and the key is
/// dropped on any hop to another host (the files come from a CDN).
/// <see cref="Changed"/> is raised on a background thread.
/// </summary>
public sealed class ModelDownloader : IDisposable
{
    /// <summary>Head room left on the disk after the downloads: results need space too.</summary>
    public const long SpareBytes = 1_000_000_000;
    public static readonly Uri WhoAmI = new($"https://{ModelCatalog.HuggingFaceHost}/api/whoami-v2");
    private const int MaxRedirects = 10;
    private static readonly TimeSpan RaiseEvery = TimeSpan.FromMilliseconds(200);

    private readonly HttpClient _http;
    private readonly Func<string?> _token;
    private readonly Func<string, long> _freeSpace;
    private readonly Func<ModelComponent, IReadOnlyList<ModelFile>> _catalog;
    private readonly TimeProvider _time;
    private readonly Lock _gate = new();
    private CancellationTokenSource? _cts;
    private Task _run = Task.CompletedTask;
    private List<ModelComponent> _finished = [];
    private (long At, long Bytes)? _lastSample;
    private long _lastRaised;

    /// <param name="models">The models folder (BRASSCRIBE_MODELS).</param>
    /// <param name="hub">The Hugging Face hub cache.</param>
    /// <param name="token">The user's Hugging Face key, read at each run (null or empty when there is none).</param>
    /// <param name="handler">The HTTP stack; a handler that doesn't follow redirects itself.</param>
    /// <param name="freeSpace">Free bytes on the drive holding a folder.</param>
    /// <param name="catalog">The files of each component.</param>
    /// <param name="time">For the transfer rate.</param>
    public ModelDownloader(string models, string hub, Func<string?> token, HttpMessageHandler? handler = null,
        Func<string, long>? freeSpace = null, Func<ModelComponent, IReadOnlyList<ModelFile>>? catalog = null, TimeProvider? time = null)
    {
        Models = models;
        Hub = hub;
        _token = token;
        _freeSpace = freeSpace ?? DiskFree;
        _catalog = catalog ?? ModelCatalog.Files;
        _time = time ?? TimeProvider.System;
        _http = new HttpClient(handler ?? new SocketsHttpHandler { AllowAutoRedirect = false }, disposeHandler: handler is null)
        {
            Timeout = Timeout.InfiniteTimeSpan,
        };
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("Brasscribe-Bandroom");
    }

    public string Models { get; }
    public string Hub { get; }

    /// <summary>How long a connection may send nothing before the download counts as stopped.</summary>
    public TimeSpan IdleTimeout { get; init; } = TimeSpan.FromSeconds(60);

    /// <summary>Links snapshot files to their blobs, as huggingface_hub does; off, or when Windows refuses, the blob is moved there.</summary>
    internal bool SymbolicLinks { get; init; } = true;

    public DownloadPhase Phase { get; private set; }
    /// <summary>Why it stopped, while <see cref="Phase"/> is Failed.</summary>
    public DownloadError? Error { get; private set; }
    /// <summary>What this run fetches, in catalogue order.</summary>
    public IReadOnlyList<ModelComponent> Components { get; private set; } = [];
    public ModelComponent? Current { get; private set; }
    public IReadOnlyList<ModelComponent> Finished => _finished;
    public long BytesDone { get; private set; }
    public long BytesTotal { get; private set; }
    /// <summary>Smoothed, for "about 12 min left".</summary>
    public double BytesPerSecond { get; private set; }

    public double Fraction => BytesTotal > 0 ? Math.Min(1, (double)BytesDone / BytesTotal) : Phase == DownloadPhase.Done ? 1 : 0;

    public int? MinutesLeft => Phase == DownloadPhase.Downloading && BytesPerSecond > 0
        ? Math.Max(1, (int)Math.Ceiling((BytesTotal - BytesDone) / BytesPerSecond / 60))
        : null;

    public bool IsActive => Phase is DownloadPhase.Checking or DownloadPhase.Downloading;

    /// <summary>The current (or last) run; it never throws.</summary>
    public Task Completion => _run;

    /// <summary>Phase, error or progress changed (progress at most five times a second).</summary>
    public event Action? Changed;
    /// <summary>A run fetched everything it was asked for.</summary>
    public event Action? Completed;
    public Action<string>? Log { get; set; }

    /// <summary>Starts (or continues) fetching <paramref name="components"/>; files already complete are skipped.</summary>
    public void Start(IEnumerable<ModelComponent> components)
    {
        bool nothing;
        lock (_gate)
        {
            if (IsActive) return;
            var previous = _run;
            Components = components.Distinct().Order().ToList();
            _finished = [];
            BytesTotal = Components.Sum(c => _catalog(c).Sum(f => f.Size));
            BytesDone = 0;
            BytesPerSecond = 0;
            _lastSample = null;
            Error = null;
            Current = null;
            nothing = Components.Count == 0;
            if (nothing) Phase = DownloadPhase.Done;
            else
            {
                Phase = DownloadPhase.Checking;
                _cts?.Dispose();
                _cts = new CancellationTokenSource();
                var ct = _cts.Token;
                // The previous run may still hold a .part open while it winds down from a pause.
                _run = Task.Run(() => RunAsync(previous, ct));
            }
        }
        Changed?.Invoke();
        if (nothing) Completed?.Invoke();
    }

    /// <summary>Stops the current file where it is; <see cref="Resume"/> continues it.</summary>
    public void Pause()
    {
        lock (_gate)
        {
            if (!IsActive) return;
            Phase = DownloadPhase.Paused;
            _cts?.Cancel();
        }
        Changed?.Invoke();
    }

    /// <summary>Continues after a pause or a failure, with the same components.</summary>
    public void Resume()
    {
        lock (_gate)
        {
            if (Phase is not (DownloadPhase.Paused or DownloadPhase.Failed)) return;
            Phase = DownloadPhase.Idle;
        }
        Start(Components);
    }

    public void Dispose()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        _http.Dispose();
    }

    // ----- The run -----

    private async Task RunAsync(Task previous, CancellationToken ct)
    {
        try
        {
            await previous.ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();
            await PreflightAsync(ct).ConfigureAwait(false);
            if (!SetPhase(DownloadPhase.Downloading)) return;
            foreach (var c in Components)
            {
                Current = c;
                await FetchComponentAsync(c, ct).ConfigureAwait(false);
                _finished.Add(c);
            }
            Current = null;
            BytesDone = BytesTotal;
            if (!SetPhase(DownloadPhase.Done)) return;
            Log?.Invoke($"models: {string.Join(", ", Components)} downloaded");
            Completed?.Invoke();
        }
        catch (Exception) when (ct.IsCancellationRequested)
        {
            // Paused: the .part files stay.
        }
        catch (DownloadException e)
        {
            Fail(e.Error);
        }
        catch (Exception e) when (e is HttpRequestException or IOException or OperationCanceledException)
        {
            Fail(new DownloadError.Network(e.Message));
        }
        catch (Exception e)
        {
            // Anything else (a Changed handler that throws, say) must not poison the next run.
            Fail(new DownloadError.Network(e.Message));
        }
    }

    /// <summary>False when a pause got there first.</summary>
    private bool SetPhase(DownloadPhase phase)
    {
        lock (_gate)
        {
            if (Phase == DownloadPhase.Paused) return false;
            Phase = phase;
        }
        Changed?.Invoke();
        return true;
    }

    private void Fail(DownloadError error)
    {
        lock (_gate)
        {
            if (Phase == DownloadPhase.Paused) return;
            Error = error;
            Phase = DownloadPhase.Failed;
        }
        Log?.Invoke($"models: download stopped: {error}");
        Changed?.Invoke();
    }

    /// <summary>The key (before any large file, so a refused key or licence shows at once) and the free space.</summary>
    private async Task PreflightAsync(CancellationToken ct)
    {
        if (Components.Any(c => c.NeedsHuggingFaceKey()))
        {
            if (Key() is null) throw new DownloadException(new DownloadError.KeyMissing());
            if (await StatusOfAsync(HttpMethod.Get, WhoAmI, ct).ConfigureAwait(false) == 401)
                throw new DownloadException(new DownloadError.KeyRefused());
            if (_catalog(ModelComponent.BandWriter).FirstOrDefault() is { } file && !IsComplete(file, ModelComponent.BandWriter))
            {
                switch (await StatusOfAsync(HttpMethod.Head, file.Url, ct).ConfigureAwait(false))
                {
                    case 401: throw new DownloadException(new DownloadError.KeyRefused());
                    case 403: throw new DownloadException(new DownloadError.LicenceNotAccepted());
                }
            }
        }
        CheckSpace();
    }

    /// <summary>Needed bytes per drive (the hub cache is usually under the user profile, the models under the data folder).</summary>
    internal void CheckSpace()
    {
        var needed = new Dictionary<string, (string Root, long Bytes)>(StringComparer.OrdinalIgnoreCase);
        foreach (var c in Components)
        {
            string root = RootFolder(c);
            string drive = Path.GetPathRoot(Path.GetFullPath(root)) ?? root;
            foreach (var f in _catalog(c).Where(f => !IsComplete(f, c)))
            {
                long part = SizeOf(PartPath(f, c)) ?? 0;
                var n = needed.GetValueOrDefault(drive, (root, 0));
                needed[drive] = (n.Root, n.Bytes + Math.Max(0, f.Size - part));
            }
        }
        foreach (var (_, n) in needed)
        {
            if (n.Bytes <= 0) continue;
            long free = _freeSpace(n.Root);
            if (free < n.Bytes + SpareBytes) throw new DownloadException(new DownloadError.NotEnoughSpace(n.Bytes + SpareBytes, free));
        }
    }

    private async Task FetchComponentAsync(ModelComponent c, CancellationToken ct)
    {
        foreach (var f in _catalog(c))
        {
            ct.ThrowIfCancellationRequested();
            long before = BytesDone;
            if (!IsComplete(f, c)) await FetchFileAsync(f, c, before, ct).ConfigureAwait(false);
            BytesDone = before + f.Size;
        }
        if (c.Home() is ModelHome.Hub hub) LinkSnapshot(c, hub);
    }

    private async Task FetchFileAsync(ModelFile f, ModelComponent c, long already, CancellationToken ct)
    {
        string dest = Destination(f, c), part = PartPath(f, c);
        try { Directory.CreateDirectory(Path.GetDirectoryName(dest)!); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { throw new DownloadException(new DownloadError.Disk(e.Message)); }

        long offset = SizeOf(part) ?? 0;
        using var idle = CancellationTokenSource.CreateLinkedTokenSource(ct);
        idle.CancelAfter(IdleTimeout);
        Log?.Invoke($"models: fetching {f.Url}");
        using (var response = await NetworkAsync(() => SendAsync(HttpMethod.Get, f.Url, offset, idle.Token), ct).ConfigureAwait(false))
        {
            int status = (int)response.StatusCode;
            FileStream? output = status switch
            {
                206 => OpenPart(part, FileMode.Append),
                // The server ignored Range (or there was nothing yet): start the file over.
                200 => OpenPart(part, FileMode.Create),
                // Nothing left to send: the part is already whole. The checksum decides.
                416 => null,
                401 => throw new DownloadException(new DownloadError.KeyRefused()),
                403 when f.Url.Host == ModelCatalog.HuggingFaceHost => throw new DownloadException(new DownloadError.LicenceNotAccepted()),
                _ => throw new DownloadException(new DownloadError.Http(status, f.Name)),
            };
            if (output is not null)
            {
                try
                {
                    long written = output.Length;
                    Progress(already + written);
                    var body = await NetworkAsync(() => response.Content.ReadAsStreamAsync(idle.Token), ct).ConfigureAwait(false);
                    var buffer = new byte[1 << 20];
                    while (true)
                    {
                        idle.CancelAfter(IdleTimeout);
                        int n = await NetworkAsync(() => body.ReadAsync(buffer, idle.Token).AsTask(), ct).ConfigureAwait(false);
                        if (n == 0) break;
                        // What arrived is kept even when a pause comes now: the next run continues after it.
                        try { await output.WriteAsync(buffer.AsMemory(0, n), CancellationToken.None).ConfigureAwait(false); }
                        catch (IOException e) { throw new DownloadException(new DownloadError.Disk(e.Message)); }
                        written += n;
                        Progress(already + written);
                    }
                }
                finally
                {
                    await output.DisposeAsync().ConfigureAwait(false);
                }
            }
        }
        ct.ThrowIfCancellationRequested();
        Verify(part, f);
        try { File.Move(part, dest, overwrite: true); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { throw new DownloadException(new DownloadError.Disk(e.Message)); }
    }

    private static FileStream OpenPart(string part, FileMode mode)
    {
        try { return new FileStream(part, mode, FileAccess.Write, FileShare.Read, 1 << 16, useAsync: true); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { throw new DownloadException(new DownloadError.Disk(e.Message)); }
    }

    /// <summary>
    /// Runs one network step. A cancelled <paramref name="ct"/> (a pause) passes through; anything else the
    /// network does, including the idle timeout, is a <see cref="DownloadError.Network"/>.
    /// </summary>
    private static async Task<T> NetworkAsync<T>(Func<Task<T>> step, CancellationToken ct)
    {
        try { return await step().ConfigureAwait(false); }
        catch (Exception e) when (!ct.IsCancellationRequested && e is OperationCanceledException)
        {
            throw new DownloadException(new DownloadError.Network("No data for a while: the connection timed out."));
        }
        catch (Exception e) when (!ct.IsCancellationRequested && e is HttpRequestException or IOException)
        {
            throw new DownloadException(new DownloadError.Network(e.Message));
        }
    }

    private void Progress(long done)
    {
        BytesDone = Math.Min(done, BytesTotal);
        long now = _time.GetTimestamp();
        if (_lastSample is { } last)
        {
            double dt = _time.GetElapsedTime(last.At, now).TotalSeconds;
            if (dt < 0.5) { RaiseProgress(now); return; }
            double rate = (done - last.Bytes) / dt;
            if (rate >= 0) BytesPerSecond = BytesPerSecond == 0 ? rate : BytesPerSecond * 0.8 + rate * 0.2;
        }
        _lastSample = (now, done);
        RaiseProgress(now);
    }

    private void RaiseProgress(long now)
    {
        if (_lastRaised != 0 && _time.GetElapsedTime(_lastRaised, now) < RaiseEvery) return;
        _lastRaised = now;
        Changed?.Invoke();
    }

    // ----- HTTP -----

    private string? Key() => _token()?.Trim() is { Length: > 0 } key ? key : null;

    /// <summary>Follows redirects itself, carrying Range; the key goes only to huggingface.co.</summary>
    private async Task<HttpResponseMessage> SendAsync(HttpMethod method, Uri url, long rangeFrom, CancellationToken ct)
    {
        string? key = Key();
        for (int hop = 0; ; hop++)
        {
            var request = new HttpRequestMessage(method, url);
            if (rangeFrom > 0) request.Headers.Range = new RangeHeaderValue(rangeFrom, null);
            if (key is not null && url.Host == ModelCatalog.HuggingFaceHost) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", key);
            var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
            int status = (int)response.StatusCode;
            if (status is 301 or 302 or 303 or 307 or 308 && response.Headers.Location is { } location && hop < MaxRedirects)
            {
                response.Dispose();
                url = location.IsAbsoluteUri ? location : new Uri(url, location);
                continue;
            }
            return response;
        }
    }

    /// <summary>The HTTP status of a request, or null when the network didn't answer (the download then says so itself).</summary>
    private async Task<int?> StatusOfAsync(HttpMethod method, Uri url, CancellationToken ct)
    {
        using var idle = CancellationTokenSource.CreateLinkedTokenSource(ct);
        idle.CancelAfter(IdleTimeout);
        try
        {
            using var response = await SendAsync(method, url, 0, idle.Token).ConfigureAwait(false);
            return (int)response.StatusCode;
        }
        catch (Exception e) when (!ct.IsCancellationRequested && e is HttpRequestException or IOException or OperationCanceledException)
        {
            return null;
        }
    }

    // ----- Files -----

    private string RootFolder(ModelComponent c) => c.Home() switch
    {
        ModelHome.Models m => Path.Combine(Models, m.Folder),
        ModelHome.Hub h => ModelCatalog.HubRepoFolder(h.Repo, Hub),
        _ => Models,
    };

    /// <summary>Where a finished file lives: <c>&lt;models&gt;\&lt;folder&gt;\&lt;name&gt;</c>, or the hub cache's <c>blobs\&lt;blob&gt;</c>.</summary>
    internal string Destination(ModelFile f, ModelComponent c) => c.Home() is ModelHome.Hub
        ? Path.Combine(RootFolder(c), "blobs", f.BlobName)
        : Path.Combine(RootFolder(c), f.Name);

    internal string PartPath(ModelFile f, ModelComponent c) => Destination(f, c) + ".part";

    private string SnapshotPath(ModelFile f, ModelHome.Hub hub) =>
        Path.Combine(ModelCatalog.HubRepoFolder(hub.Repo, Hub), "snapshots", hub.Revision, f.Name);

    /// <summary>In place: the blob, or (where it was moved there) the snapshot file.</summary>
    internal bool IsComplete(ModelFile f, ModelComponent c) =>
        ModelCheck.FileMatches(Destination(f, c), f.Size)
        || (c.Home() is ModelHome.Hub hub && ModelCheck.FileMatches(SnapshotPath(f, hub), f.Size));

    /// <summary>Size, then SHA-256 or git blob id where upstream publishes them. A bad file is deleted.</summary>
    private static void Verify(string part, ModelFile f)
    {
        bool ok;
        try
        {
            long size = SizeOf(part) ?? -1;
            ok = f.Size <= 0 || size == f.Size;
            if (ok && f.Sha256 is { } sha) ok = Sha256Hex(part) == sha;
            else if (ok && f.GitBlob is { } blob) ok = GitBlobId(part) == blob;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { throw new DownloadException(new DownloadError.Disk(e.Message)); }
        if (ok) return;
        try { File.Delete(part); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        throw new DownloadException(new DownloadError.ChecksumMismatch(f.Name));
    }

    /// <summary>
    /// <c>snapshots\&lt;rev&gt;\&lt;name&gt;</c> → <c>..\..\blobs\&lt;blob&gt;</c> and <c>refs\main</c>, as huggingface_hub writes
    /// them. Without the right to make symbolic links (Windows outside developer mode) the blob moves into the
    /// snapshot instead, which is what huggingface_hub itself does there.
    /// </summary>
    private void LinkSnapshot(ModelComponent c, ModelHome.Hub hub)
    {
        string folder = ModelCatalog.HubRepoFolder(hub.Repo, Hub);
        string snapshot = Path.Combine(folder, "snapshots", hub.Revision);
        try
        {
            Directory.CreateDirectory(snapshot);
            foreach (var f in _catalog(c))
            {
                string link = Path.Combine(snapshot, f.Name);
                string blob = Path.Combine(folder, "blobs", f.BlobName);
                string target = Path.Combine("..", "..", "blobs", f.BlobName);
                var info = new FileInfo(link);
                if (info.LinkTarget == target) continue;
                bool blobThere = File.Exists(blob);
                if (info.LinkTarget is null && info.Exists && !blobThere) continue; // moved here by an earlier run
                if (info.LinkTarget is not null || info.Exists) File.Delete(link);
                if (SymbolicLinks)
                {
                    try { File.CreateSymbolicLink(link, target); continue; }
                    catch (Exception e) when (e is IOException or UnauthorizedAccessException) { Log?.Invoke($"models: no symbolic link ({e.Message}); moving the file"); }
                }
                File.Move(blob, link, overwrite: true);
            }
            Directory.CreateDirectory(Path.Combine(folder, "refs"));
            File.WriteAllText(Path.Combine(folder, "refs", "main"), hub.Revision);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { throw new DownloadException(new DownloadError.Disk(e.Message)); }
    }

    // ----- Helpers -----

    internal static long? SizeOf(string path)
    {
        try { var info = new FileInfo(path); return info.Exists ? info.Length : null; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return null; }
    }

    internal static string Sha256Hex(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    /// <summary><c>git hash-object</c>: SHA-1 of "blob &lt;size&gt;\0" and the bytes.</summary>
    internal static string GitBlobId(string path)
    {
        using var stream = File.OpenRead(path);
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA1);
        hash.AppendData(System.Text.Encoding.ASCII.GetBytes($"blob {stream.Length}\0"));
        var buffer = new byte[1 << 20];
        int n;
        while ((n = stream.Read(buffer)) > 0) hash.AppendData(buffer, 0, n);
        return Convert.ToHexStringLower(hash.GetHashAndReset());
    }

    /// <summary>Free bytes on the drive holding <paramref name="path"/> (or its nearest existing parent).</summary>
    public static long DiskFree(string path)
    {
        try
        {
            string root = Path.GetPathRoot(Path.GetFullPath(path)) is { Length: > 0 } r ? r : path;
            return new DriveInfo(root).AvailableFreeSpace;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return long.MaxValue; // unknown: let the download say so itself if the disk fills
        }
    }
}
