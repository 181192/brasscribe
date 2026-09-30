using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Brasscribe.Bandroom.Core.Downloads;

namespace Brasscribe.Bandroom.Core.Tests;

/// <summary>A fake web for the downloader: files by URL, honouring Range; drops, hangs and redirects on demand.</summary>
internal sealed class StubWeb : HttpMessageHandler
{
    public sealed record Route
    {
        public int Status { get; init; } = 200;
        public byte[] Body { get; init; } = [];
        /// <summary>Send only this many bytes, then drop the connection.</summary>
        public int? DropAfter { get; init; }
        /// <summary>Send this many bytes, then never finish (until cancelled).</summary>
        public int? HangAfter { get; init; }
        /// <summary>Answer with a 302 to this URL.</summary>
        public Uri? Redirect { get; init; }
        /// <summary>Ignore Range and always send the whole file.</summary>
        public bool IgnoresRange { get; init; }
    }

    public sealed record Seen(string Url, string Method, string? Range, string? Authorization);

    private readonly Lock _gate = new();
    private readonly Dictionary<string, Route> _routes = [];
    private readonly List<Seen> _seen = [];

    public void Set(string url, Route route) { lock (_gate) _routes[url] = route; }
    public void Update(string url, Func<Route, Route> change) { lock (_gate) _routes[url] = change(_routes[url]); }
    public IReadOnlyList<Seen> Requests(string url) { lock (_gate) return _seen.Where(s => s.Url == url).ToList(); }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        string url = request.RequestUri!.AbsoluteUri;
        Route? route;
        lock (_gate)
        {
            _seen.Add(new Seen(url, request.Method.Method, request.Headers.Range?.ToString(), request.Headers.Authorization?.ToString()));
            route = _routes.GetValueOrDefault(url);
        }
        if (route is null) return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
        if (route.Redirect is { } to)
        {
            var r = new HttpResponseMessage(HttpStatusCode.Found);
            r.Headers.Location = to;
            return Task.FromResult(r);
        }
        if (route.Status != 200) return Task.FromResult(new HttpResponseMessage((HttpStatusCode)route.Status));
        var body = route.Body;
        var status = HttpStatusCode.OK;
        if (!route.IgnoresRange && request.Headers.Range?.Ranges.FirstOrDefault()?.From is { } from)
        {
            if (from >= body.Length) return Task.FromResult(new HttpResponseMessage(HttpStatusCode.RequestedRangeNotSatisfiable));
            body = body[(int)from..];
            status = HttpStatusCode.PartialContent;
        }
        if (request.Method == HttpMethod.Head) body = [];
        var stream = new StubStream(body, route.DropAfter, route.HangAfter);
        return Task.FromResult(new HttpResponseMessage(status) { Content = new StreamContent(stream) });
    }

    /// <summary>Hands over exactly the first bytes, then drops or hangs on the next read.</summary>
    private sealed class StubStream(byte[] body, int? dropAfter, int? hangAfter) : Stream
    {
        private int _pos;
        private readonly int _limit = Math.Min(body.Length, dropAfter ?? hangAfter ?? body.Length);

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        {
            if (_pos >= _limit)
            {
                if (dropAfter is { } d && d < body.Length) throw new IOException("The connection was lost.");
                if (hangAfter is { } h && h < body.Length) await Task.Delay(Timeout.Infinite, ct);
                return 0;
            }
            int n = Math.Min(buffer.Length, _limit - _pos);
            body.AsMemory(_pos, n).CopyTo(buffer);
            _pos += n;
            return n;
        }

        public override int Read(byte[] buffer, int offset, int count) => ReadAsync(buffer.AsMemory(offset, count)).AsTask().GetAwaiter().GetResult();
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => _pos; set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
}

public sealed class ModelDownloadTests : IDisposable
{
    private const string SepUrl = "https://example.org/sep/BS-Roformer-SW.ckpt";
    private const string YamlUrl = "https://example.org/sep/BS-Roformer-SW.yaml";
    private const string HfModel = "https://huggingface.co/MuScriptor/muscriptor-medium/resolve/r1/model.safetensors";
    private const string HfConfig = "https://huggingface.co/MuScriptor/muscriptor-medium/resolve/r1/config.json";
    private const string WhoAmI = "https://huggingface.co/api/whoami-v2";
    private static readonly TimeSpan Patience = TimeSpan.FromSeconds(10);

    private readonly StubWeb _web = new();
    private readonly string _root = Directory.CreateTempSubdirectory("bandroom-dl").FullName;
    private readonly byte[] _big = Enumerable.Range(0, 300_000).Select(i => (byte)(i % 251)).ToArray();
    private readonly byte[] _small = Encoding.UTF8.GetBytes("dim: 1024\n");

    private string ModelsDir => Path.Combine(_root, "models");
    private string HubDir => Path.Combine(_root, "hub");
    private string SepFile => Path.Combine(ModelsDir, "separator", "BS-Roformer-SW.ckpt");

    public void Dispose()
    {
        _web.Dispose();
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    internal static string Sha256Hex(byte[] d) => Convert.ToHexStringLower(SHA256.HashData(d));

    private static string GitBlob(byte[] d)
    {
        var header = Encoding.ASCII.GetBytes($"blob {d.Length}\0");
#pragma warning disable CA5350 // git's object id is SHA-1 by definition
        return Convert.ToHexStringLower(SHA1.HashData([.. header, .. d]));
#pragma warning restore CA5350
    }

    private Func<ModelComponent, IReadOnlyList<ModelFile>> Catalog(string? bigSha = null) => c => c switch
    {
        ModelComponent.SoloistSeparator =>
        [
            new("BS-Roformer-SW.ckpt", new Uri(SepUrl), _big.Length, Sha256: bigSha ?? Sha256Hex(_big)),
            new("BS-Roformer-SW.yaml", new Uri(YamlUrl), 0),
        ],
        ModelComponent.InstrumentSeparator => [],
        _ =>
        [
            new("model.safetensors", new Uri(HfModel), _big.Length, Sha256: Sha256Hex(_big)),
            new("config.json", new Uri(HfConfig), _small.Length, GitBlob: GitBlob(_small)),
        ],
    };

    private ModelDownloader Downloader(string? token = "hf_test", long free = 100_000_000_000, string? bigSha = null, bool links = true) =>
        new(ModelsDir, HubDir, () => token, _web, _ => free, Catalog(bigSha)) { SymbolicLinks = links };

    private void ServeSeparator()
    {
        _web.Set(SepUrl, new() { Body = _big });
        _web.Set(YamlUrl, new() { Body = _small });
    }

    private void ServeBandWriter(StubWeb.Route? model = null)
    {
        _web.Set(WhoAmI, new() { Body = "{}"u8.ToArray() });
        _web.Set(HfModel, model ?? new() { Body = _big });
        _web.Set(HfConfig, new() { Body = _small });
    }

    private static async Task Settle(ModelDownloader d) => await d.Completion.WaitAsync(Patience);

    private static async Task WaitUntil(Func<bool> condition)
    {
        var until = DateTime.UtcNow + Patience;
        while (!condition() && DateTime.UtcNow < until) await Task.Delay(10);
        Assert.True(condition(), "timed out");
    }

    [Fact]
    public async Task Downloads_into_the_models_folder_and_checks_the_sum()
    {
        ServeSeparator();
        using var d = Downloader();
        d.Start([ModelComponent.SoloistSeparator]);
        await Settle(d);
        Assert.Equal(DownloadPhase.Done, d.Phase);
        Assert.Equal(_big, File.ReadAllBytes(SepFile));
        Assert.False(File.Exists(SepFile + ".part"));
        Assert.Equal(1, d.Fraction);
        Assert.Equal([ModelComponent.BandWriter], ModelCheck.Check(ModelsDir, HubDir, Catalog()).Missing);
    }

    private const string ChecksUrl = "https://example.org/lists/download_checks.json";
    private static readonly byte[] ChecksJson = "{\"roformer_download_list\": {}}"u8.ToArray();

    [Fact]
    public async Task A_file_upstream_edits_is_fetched_whole_and_must_be_json()
    {
        var catalog = (ModelComponent c) => c == ModelComponent.SoloistSeparator
            ? (IReadOnlyList<ModelFile>)[new("download_checks.json", new Uri(ChecksUrl), 0)]
            : [];
        string file = Path.Combine(ModelsDir, "separator", "download_checks.json");
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        // A sign-in page answered in its place.
        _web.Set(ChecksUrl, new() { Body = "<html>Sign in to the Wi-Fi</html>"u8.ToArray() });
        using (var d = new ModelDownloader(ModelsDir, HubDir, () => null, _web, _ => long.MaxValue, catalog))
        {
            d.Start([ModelComponent.SoloistSeparator]);
            await Settle(d);
            Assert.Equal(DownloadPhase.Failed, d.Phase);
            Assert.IsType<DownloadError.ChecksumMismatch>(d.Error);
        }
        Assert.False(File.Exists(file));
        Assert.False(File.Exists(file + ".part"));

        // Part of an earlier copy is left: never resumed, the whole file comes again.
        File.WriteAllBytes(file + ".part", "{\"old\":"u8.ToArray());
        _web.Set(ChecksUrl, new() { Body = ChecksJson });
        using (var d = new ModelDownloader(ModelsDir, HubDir, () => null, _web, _ => long.MaxValue, catalog))
        {
            d.Start([ModelComponent.SoloistSeparator]);
            await Settle(d);
            Assert.Equal(DownloadPhase.Done, d.Phase);
        }
        Assert.Equal(ChecksJson, File.ReadAllBytes(file));
        Assert.All(_web.Requests(ChecksUrl).Where(r => r.Method == "GET"), r => Assert.Null(r.Range));
        Assert.True(ModelCheck.IsPresent(ModelComponent.SoloistSeparator, ModelsDir, HubDir, catalog(ModelComponent.SoloistSeparator)));

        // One that isn't JSON in place (saved by something else) counts as missing.
        File.WriteAllText(file, "<html>Sign in</html>");
        File.SetLastWriteTimeUtc(file, DateTime.UtcNow.AddMinutes(1));
        Assert.False(ModelCheck.IsPresent(ModelComponent.SoloistSeparator, ModelsDir, HubDir, catalog(ModelComponent.SoloistSeparator)));
    }

    [Fact]
    public async Task A_dropped_connection_resumes_with_Range()
    {
        _web.Set(SepUrl, new() { Body = _big, DropAfter = 100_000 });
        _web.Set(YamlUrl, new() { Body = _small });
        using var d = Downloader();
        d.Start([ModelComponent.SoloistSeparator]);
        await Settle(d);
        Assert.Equal(DownloadPhase.Failed, d.Phase);
        Assert.IsType<DownloadError.Network>(d.Error);
        Assert.Equal(100_000, new FileInfo(SepFile + ".part").Length);

        _web.Update(SepUrl, r => r with { DropAfter = null });
        d.Resume();
        await Settle(d);
        Assert.Equal(DownloadPhase.Done, d.Phase);
        Assert.Equal("bytes=100000-", _web.Requests(SepUrl)[^1].Range);
        Assert.Equal(_big, File.ReadAllBytes(SepFile));
    }

    [Fact]
    public async Task A_server_that_ignores_Range_starts_the_file_over()
    {
        _web.Set(SepUrl, new() { Body = _big, DropAfter = 50_000 });
        _web.Set(YamlUrl, new() { Body = _small });
        using var d = Downloader();
        d.Start([ModelComponent.SoloistSeparator]);
        await Settle(d);
        _web.Update(SepUrl, r => r with { DropAfter = null, IgnoresRange = true });
        d.Resume();
        await Settle(d);
        Assert.Equal(DownloadPhase.Done, d.Phase);
        Assert.Equal(_big, File.ReadAllBytes(SepFile));
    }

    [Fact]
    public async Task Pause_keeps_the_part_and_resume_finishes_it()
    {
        _web.Set(SepUrl, new() { Body = _big, HangAfter = 120_000 });
        _web.Set(YamlUrl, new() { Body = _small });
        using var d = Downloader();
        d.Start([ModelComponent.SoloistSeparator]);
        await WaitUntil(() => d.BytesDone >= 120_000);
        Assert.Equal(DownloadPhase.Downloading, d.Phase);
        d.Pause();
        Assert.Equal(DownloadPhase.Paused, d.Phase);
        await Settle(d);
        Assert.Equal(DownloadPhase.Paused, d.Phase);
        Assert.Equal(120_000, new FileInfo(SepFile + ".part").Length);

        _web.Update(SepUrl, r => r with { HangAfter = null });
        d.Resume();
        await Settle(d);
        Assert.Equal(DownloadPhase.Done, d.Phase);
        Assert.Equal("bytes=120000-", _web.Requests(SepUrl)[^1].Range);
        Assert.Equal(_big, File.ReadAllBytes(SepFile));
    }

    [Fact]
    public async Task A_wrong_checksum_deletes_the_file()
    {
        ServeSeparator();
        using var d = Downloader(bigSha: new string('0', 64));
        d.Start([ModelComponent.SoloistSeparator]);
        await Settle(d);
        Assert.Equal(DownloadPhase.Failed, d.Phase);
        Assert.Equal(new DownloadError.ChecksumMismatch("BS-Roformer-SW.ckpt"), d.Error);
        Assert.False(File.Exists(SepFile));
        Assert.False(File.Exists(SepFile + ".part"));
    }

    [Fact]
    public async Task Not_enough_space_stops_before_any_download()
    {
        ServeSeparator();
        using var d = Downloader(free: 2_000_000);
        d.Start([ModelComponent.SoloistSeparator]);
        await Settle(d);
        Assert.Equal(new DownloadError.NotEnoughSpace(_big.Length + ModelDownloader.SpareBytes, 2_000_000), d.Error);
        Assert.Empty(_web.Requests(SepUrl));
    }

    [Fact]
    public async Task The_band_writer_needs_a_key()
    {
        ServeBandWriter();
        using var d = Downloader(token: null);
        d.Start([ModelComponent.BandWriter]);
        await Settle(d);
        Assert.Equal(new DownloadError.KeyMissing(), d.Error);
        Assert.Empty(_web.Requests(HfModel));
        Assert.Empty(_web.Requests(WhoAmI));
    }

    [Fact]
    public async Task A_refused_key_is_said_so()
    {
        ServeBandWriter();
        _web.Set(WhoAmI, new() { Status = 401 });
        using var d = Downloader();
        d.Start([ModelComponent.BandWriter]);
        await Settle(d);
        Assert.Equal(new DownloadError.KeyRefused(), d.Error);
        Assert.Equal("Bearer hf_test", _web.Requests(WhoAmI).Single().Authorization);
    }

    [Fact]
    public async Task A_licence_not_accepted_is_403()
    {
        ServeBandWriter(new() { Status = 403 });
        using var d = Downloader();
        d.Start([ModelComponent.BandWriter]);
        await Settle(d);
        Assert.Equal(new DownloadError.LicenceNotAccepted(), d.Error);
        Assert.Equal("HEAD", _web.Requests(HfModel).First().Method);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task The_band_writer_lands_in_the_hub_cache_as_hugging_face_lays_it_out(bool links)
    {
        const string cdn = "https://cdn.example.org/xet/blob";
        ServeBandWriter(new() { Redirect = new Uri(cdn) });
        _web.Set(cdn, new() { Body = _big });
        using var d = Downloader(links: links);
        d.Start([ModelComponent.BandWriter]);
        await Settle(d);
        Assert.Equal(DownloadPhase.Done, d.Phase);

        string repo = Path.Combine(HubDir, "models--MuScriptor--muscriptor-medium");
        Assert.Equal(ModelCatalog.MuscriptorRevision, File.ReadAllText(Path.Combine(repo, "refs", "main")));
        string snapshot = Path.Combine(repo, "snapshots", ModelCatalog.MuscriptorRevision);
        string model = Path.Combine(snapshot, "model.safetensors"), blob = Path.Combine(repo, "blobs", Sha256Hex(_big));
        if (new FileInfo(model).LinkTarget is { } target)
            Assert.Equal(Path.Combine("..", "..", "blobs", Sha256Hex(_big)), target);
        else
            Assert.False(File.Exists(blob), "a snapshot copy while the blob stays is twice the space"); // moved, as without symlink rights
        Assert.True(links || new FileInfo(model).LinkTarget is null);
        Assert.Equal(_big, File.ReadAllBytes(model));
        Assert.Equal(_small, File.ReadAllBytes(Path.Combine(snapshot, "config.json")));

        // The key went to Hugging Face, never to the CDN it redirects to.
        Assert.All(_web.Requests(HfModel), r => Assert.Equal("Bearer hf_test", r.Authorization));
        Assert.NotEmpty(_web.Requests(cdn));
        Assert.All(_web.Requests(cdn), r => Assert.Null(r.Authorization));
        Assert.Equal([ModelComponent.SoloistSeparator], ModelCheck.Check(ModelsDir, HubDir, Catalog()).Missing);

        // Done stays done: a second run fetches nothing.
        int before = _web.Requests(cdn).Count;
        d.Start([ModelComponent.BandWriter]);
        await Settle(d);
        Assert.Equal(DownloadPhase.Done, d.Phase);
        Assert.Equal(before, _web.Requests(cdn).Count);
    }

    [Fact]
    public async Task Only_what_is_missing_is_fetched()
    {
        ServeSeparator();
        Directory.CreateDirectory(Path.GetDirectoryName(SepFile)!);
        File.WriteAllBytes(SepFile, _big);
        using var d = Downloader();
        d.Start([ModelComponent.SoloistSeparator]);
        await Settle(d);
        Assert.Equal(DownloadPhase.Done, d.Phase);
        Assert.Empty(_web.Requests(SepUrl));
        Assert.Single(_web.Requests(YamlUrl));
    }

    [Fact]
    public async Task Progress_counts_bytes_and_nothing_to_fetch_is_done_at_once()
    {
        ServeSeparator();
        using var d = Downloader();
        int changes = 0;
        d.Changed += () => Interlocked.Increment(ref changes);
        d.Start([ModelComponent.SoloistSeparator]);
        Assert.Equal(_big.Length, d.BytesTotal);
        await Settle(d);
        Assert.Equal(d.BytesTotal, d.BytesDone);
        Assert.True(changes >= 3); // checking, downloading, done

        bool completed = false;
        d.Completed += () => completed = true;
        d.Start([]);
        Assert.Equal(DownloadPhase.Done, d.Phase);
        Assert.True(completed);
    }
}

public sealed class ModelCheckTests : IDisposable
{
    private readonly string _home = Directory.CreateTempSubdirectory("bandroom-check").FullName;
    private string ModelsDir => Path.Combine(_home, "AppData", "Local", "Brasscribe", "models");
    private string HubDir => Path.Combine(_home, ".cache", "huggingface", "hub");

    public void Dispose()
    {
        try { Directory.Delete(_home, true); } catch (IOException) { }
    }

    /// <summary>A file of <paramref name="size"/> bytes that takes no disk (sparse where the file system allows).</summary>
    private static void Sparse(string path, long size)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        using var f = File.Create(path);
        f.SetLength(size);
    }

    /// <summary>A stand-in of <paramref name="size"/> bytes; one with no size known is some bytes, and a .json is JSON.</summary>
    private static void Place(string path, long size)
    {
        if (size > 0) { Sparse(path, size); return; }
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, path.EndsWith(".json", StringComparison.Ordinal) ? "{}" : "x");
    }

    /// <summary>As huggingface_hub leaves it: a link to the blob, or (without symlink rights) the file itself.</summary>
    private static void Fill(ModelComponent c, string models, string hub)
    {
        switch (c.Home())
        {
            case ModelHome.Models m:
                foreach (var f in ModelCatalog.Files(c)) Place(Path.Combine(models, m.Folder, f.Name), f.Size);
                break;
            case ModelHome.Hub h:
                string folder = ModelCatalog.HubRepoFolder(h.Repo, hub);
                foreach (var f in ModelCatalog.Files(c))
                {
                    string blob = Path.Combine(folder, "blobs", f.BlobName), link = Path.Combine(folder, "snapshots", h.Revision, f.Name);
                    Sparse(blob, f.Size);
                    Directory.CreateDirectory(Path.GetDirectoryName(link)!);
                    try { File.CreateSymbolicLink(link, Path.Combine("..", "..", "blobs", f.BlobName)); }
                    catch (Exception e) when (e is IOException or UnauthorizedAccessException) { File.Move(blob, link); }
                }
                Directory.CreateDirectory(Path.Combine(folder, "refs"));
                File.WriteAllText(Path.Combine(folder, "refs", "main"), h.Revision);
                break;
        }
    }

    [Fact]
    public void Nothing_there_misses_all_three_in_order()
    {
        var result = ModelCheck.Check(ModelsDir, HubDir);
        Assert.Equal([ModelComponent.SoloistSeparator, ModelComponent.InstrumentSeparator, ModelComponent.BandWriter], result.Missing);
        Assert.Contains(result.MissingFiles, f => f.EndsWith("BS-Roformer-SW.ckpt", StringComparison.Ordinal));
        Assert.False(result.IsReady);
    }

    [Fact]
    public void All_there_is_ready()
    {
        foreach (var c in ModelCatalog.All) Fill(c, ModelsDir, HubDir);
        var result = ModelCheck.Check(ModelsDir, HubDir);
        Assert.True(result.IsReady);
        Assert.Empty(result.MissingFiles);
    }

    /// <summary>The owner's case: MuScriptor in the hub cache, the separators not in the models folder.</summary>
    [Fact]
    public void The_band_writer_in_the_hub_cache_counts_and_the_separators_are_named()
    {
        Fill(ModelComponent.BandWriter, ModelsDir, HubDir);
        Assert.Equal([ModelComponent.SoloistSeparator, ModelComponent.InstrumentSeparator], ModelCheck.Check(ModelsDir, HubDir).Missing);
    }

    [Fact]
    public void A_folder_alone_or_a_wrong_size_is_not_enough()
    {
        Directory.CreateDirectory(Path.Combine(ModelsDir, "separator"));
        Fill(ModelComponent.InstrumentSeparator, ModelsDir, HubDir);
        Sparse(Path.Combine(ModelsDir, "mega53", "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"), 1000);
        var missing = ModelCheck.Check(ModelsDir, HubDir).Missing;
        Assert.Contains(ModelComponent.SoloistSeparator, missing);
        Assert.Contains(ModelComponent.InstrumentSeparator, missing);
    }

    [Fact]
    public void A_newer_revision_in_refs_main_counts_when_its_files_are_there()
    {
        string folder = ModelCatalog.HubRepoFolder(ModelCatalog.MuscriptorRepo, HubDir);
        foreach (var f in ModelCatalog.Files(ModelComponent.BandWriter)) Place(Path.Combine(folder, "snapshots", "newer", f.Name), 0);
        Directory.CreateDirectory(Path.Combine(folder, "refs"));
        File.WriteAllText(Path.Combine(folder, "refs", "main"), "newer\n");
        Assert.DoesNotContain(ModelComponent.BandWriter, ModelCheck.Check(ModelsDir, HubDir).Missing);
    }

    [Fact]
    public void HF_HUB_CACHE_then_HF_HOME_then_the_profile()
    {
        Assert.Equal("/x", ModelCatalog.HubCache(new Dictionary<string, string?> { ["HF_HUB_CACHE"] = "/x", ["HF_HOME"] = "/y" }, "/home"));
        Assert.Equal(Path.Combine("/y", "hub"), ModelCatalog.HubCache(new Dictionary<string, string?> { ["HF_HUB_CACHE"] = "", ["HF_HOME"] = "/y" }, "/home"));
        Assert.Equal(Path.Combine("/home", ".cache", "huggingface", "hub"), ModelCatalog.HubCache(new Dictionary<string, string?>(), "/home"));
        Assert.Equal(Path.Combine("/h", "models--MuScriptor--muscriptor-medium"), ModelCatalog.HubRepoFolder(ModelCatalog.MuscriptorRepo, "/h"));
    }

    [Fact]
    public void The_catalogue_matches_the_adapters()
    {
        Assert.Contains("BS-Roformer-SW.ckpt", ModelCatalog.Files(ModelComponent.SoloistSeparator).Select(f => f.Name));
        Assert.Equal(["mvsep_mega_model_bs_roformer_53_stems_v1.ckpt", "mvsep_mega_model_bs_roformer_53_stems.yaml"],
            ModelCatalog.Files(ModelComponent.InstrumentSeparator).Select(f => f.Name));
        foreach (var f in ModelCatalog.All.SelectMany(ModelCatalog.Files))
        {
            if (f.Sha256 is { } sha) Assert.Matches("^[0-9a-f]{64}$", sha);
            if (f.GitBlob is { } blob) Assert.Matches("^[0-9a-f]{40}$", blob);
            if (f.Size > 1000) Assert.NotNull(f.Sha256);
        }
        Assert.Equal([ModelComponent.BandWriter], ModelCatalog.All.Where(c => c.NeedsHuggingFaceKey()));
        Assert.Equal(new ModelHome.Models("separator"), ModelComponent.SoloistSeparator.Home());
        Assert.Equal(new ModelHome.Models("mega53"), ModelComponent.InstrumentSeparator.Home());
    }

    /// <summary>The same files, URLs, sizes and checksums as Bandroom for macOS: read from its ModelCatalog.swift.</summary>
    [SkippableFact]
    public void The_catalogue_is_the_macOS_catalogue()
    {
        const string Relative = "apps/bandroom/macos/Packages/BandroomKit/Sources/BandroomKit/ModelCatalog.swift";
        string? swift = null;
        try
        {
            swift = Path.Combine(TestPaths.RepoRoot, "apps", "bandroom", "macos", "Packages", "BandroomKit", "Sources", "BandroomKit", "ModelCatalog.swift");
        }
        catch (DirectoryNotFoundException) { }
        Skip.If(swift is null, $"{Relative} not found: the tests run outside a checkout");
        Skip.If(!File.Exists(swift), $"{Relative} not found: this checkout has no macOS app");
        string source = File.ReadAllText(swift);

        var constants = Regex.Matches(source, @"static let (\w+) = ""([^""]*)""").ToDictionary(m => m.Groups[1].Value, m => m.Groups[2].Value);
        string Resolve(string s)
        {
            for (int i = 0; i < 5; i++) s = Regex.Replace(s, @"\\\((\w+)\)", m => constants[m.Groups[1].Value]);
            return s;
        }
        foreach (var k in constants.Keys.ToList()) constants[k] = Resolve(constants[k]);
        Assert.Equal(ModelCatalog.MuscriptorRevision, constants["muscriptorRevision"]);
        Assert.Equal(ModelCatalog.MuscriptorRepo, constants["muscriptorRepo"]);

        var parsed = Regex.Matches(source,
                @"ModelFile\(name:\s*""(?<name>[^""]+)"",\s*url:\s*URL\(string:\s*""(?<url>[^""]+)""\)!,\s*size:\s*(?<size>[\d_]+)(?:,\s*(?<kind>sha256|gitBlob):\s*""(?<hex>[0-9a-f]+)"")?\)")
            .Select(m => new ModelFile(m.Groups["name"].Value, new Uri(Resolve(m.Groups["url"].Value)),
                long.Parse(m.Groups["size"].Value.Replace("_", "", StringComparison.Ordinal), CultureInfo.InvariantCulture),
                Sha256: m.Groups["kind"].Value == "sha256" ? m.Groups["hex"].Value : null,
                GitBlob: m.Groups["kind"].Value == "gitBlob" ? m.Groups["hex"].Value : null))
            .ToList();
        var ours = ModelCatalog.All.SelectMany(ModelCatalog.Files).ToList();
        Assert.Equal(7, ours.Count);
        Assert.Equal(ours, parsed);
    }
}

public sealed class ComputerNameTests
{
    [Theory]
    [InlineData("DDPW3GWFDK")]
    [InlineData("C02XK1ZJJG5H")]
    [InlineData("DESKTOP-4F2K9QZ")]
    [InlineData("LAPTOP-8KD2M1QX")]
    public void Serial_like_names_are_machine_generated(string name) => Assert.True(ComputerName.LooksMachineGenerated(name));

    [Theory]
    [InlineData("Kalli's PC")]
    [InlineData("Surface Pro")]
    [InlineData("Studio")]
    [InlineData("BANDROOM")]
    [InlineData("PC-2")]
    [InlineData("Kallis-PC")]
    [InlineData("M3PRO")]
    [InlineData("korps-pc-01")]
    public void Names_people_chose_are_kept(string name) => Assert.False(ComputerName.LooksMachineGenerated(name));

    [Fact]
    public void The_shown_name_defaults_to_the_computer_name()
    {
        Assert.Equal("DESKTOP-4F2K9QZ", ComputerName.Shown("DESKTOP-4F2K9QZ", null));
        Assert.Equal("DESKTOP-4F2K9QZ", ComputerName.Shown("DESKTOP-4F2K9QZ", "  "));
        Assert.Equal("Øvingslokalet", ComputerName.Shown("DESKTOP-4F2K9QZ", " Øvingslokalet "));
    }

    [Fact]
    public void Settings_offers_the_field_for_machine_names_or_once_set()
    {
        Assert.True(ComputerName.OffersCustomName("DESKTOP-4F2K9QZ", null));
        Assert.False(ComputerName.OffersCustomName("Kalli's PC", null));
        Assert.True(ComputerName.OffersCustomName("Kalli's PC", "Korpset"));
    }

    [Fact]
    public void The_name_is_stored_on_this_pc_and_an_empty_one_removes_it()
    {
        var dir = Directory.CreateTempSubdirectory("bandroom-name").FullName;
        try
        {
            var store = new ComputerNameStore(Path.Combine(dir, "bandroom", "computer-name"));
            Assert.Null(store.Load());
            Assert.True(store.Save(" Korpset "));
            Assert.Equal("Korpset", store.Load());
            Assert.True(store.Save(""));
            Assert.Null(store.Load());
            Assert.False(File.Exists(store.FilePath));
        }
        finally { Directory.Delete(dir, true); }
    }
}
