using Brasscribe.Bandroom.Core.Downloads;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class DownloadTextTests
{
    private const ModelComponent Soloist = ModelComponent.SoloistSeparator;
    private const ModelComponent Instrument = ModelComponent.InstrumentSeparator;
    private const ModelComponent Writer = ModelComponent.BandWriter;

    [Fact]
    public void The_problem_names_what_is_missing()
    {
        Assert.Equal("The band writer isn't downloaded yet.", DownloadText.NotDownloaded(Strings.En, [Writer]));
        Assert.Equal("The soloist separator isn't downloaded yet.", DownloadText.NotDownloaded(Strings.En, [Soloist]));
        Assert.Equal("The instrument separator isn't downloaded yet.", DownloadText.NotDownloaded(Strings.En, [Instrument]));
        Assert.Equal("The soloist separator and the band writer aren't downloaded yet.", DownloadText.NotDownloaded(Strings.En, [Writer, Soloist]));
        Assert.Equal("The soloist separator, the instrument separator and the band writer aren't downloaded yet.",
            DownloadText.NotDownloaded(Strings.En, [Soloist, Instrument, Writer]));
        Assert.Equal("Brasscribe's own tools aren't installed yet.", DownloadText.NotDownloaded(Strings.En, []));
    }

    [Fact]
    public void The_problem_in_norwegian()
    {
        Assert.Equal("Bandskriveren er ikke lastet ned ennå.", DownloadText.NotDownloaded(Strings.Nb, [Writer]));
        Assert.Equal("Solistskilleren og bandskriveren er ikke lastet ned ennå.", DownloadText.NotDownloaded(Strings.Nb, [Soloist, Writer]));
        Assert.Equal("Solistskilleren, instrumentskilleren og bandskriveren er ikke lastet ned ennå.",
            DownloadText.NotDownloaded(Strings.Nb, [Soloist, Instrument, Writer]));
        Assert.Equal("Brasscribes egne verktøy er ikke installert ennå.", DownloadText.NotDownloaded(Strings.Nb, []));
    }

    [Fact]
    public void The_missing_download_problem_lists_the_files_for_the_tech_person()
    {
        var p = Problems.MissingDownload(Strings.En, [Soloist, Writer], [@"models\separator\BS-Roformer-SW.ckpt", "model.safetensors"]);
        Assert.Equal(ProblemKind.MissingDownload, p.Kind);
        Assert.Equal("Full-band scores need one more step", p.Title);
        Assert.Equal("The soloist separator and the band writer aren't downloaded yet.", p.Why);
        Assert.Equal("Finish setting up", p.FixLabel);
        Assert.Contains("BS-Roformer-SW.ckpt", p.Details);
        Assert.Contains("model.safetensors", p.Details);
    }

    [Fact]
    public void The_health_row_counts_the_downloads()
    {
        Assert.Equal("Ready", DownloadText.ReadyWord(Strings.En, 0));
        Assert.Equal("Missing one download", DownloadText.ReadyWord(Strings.En, 1));
        Assert.Equal("Missing 2 downloads", DownloadText.ReadyWord(Strings.En, 2));
        Assert.Equal("Mangler 3 nedlastinger", DownloadText.ReadyWord(Strings.Nb, 3));
    }

    [Fact]
    public void Progress_in_gigabytes_and_minutes()
    {
        Assert.Equal("3.1 of 9.8 GB · about 12 min left", DownloadText.Progress(Strings.En, 3_100_000_000, 9_800_000_000, 12, false));
        Assert.Equal("3,1 av 9,8 GB · omtrent 12 min igjen", DownloadText.Progress(Strings.Nb, 3_100_000_000, 9_800_000_000, 12, false));
        Assert.Equal("Paused · 3.1 of 9.8 GB", DownloadText.Progress(Strings.En, 3_100_000_000, 9_800_000_000, null, true));
        Assert.Equal("0.0 of 9.8 GB", DownloadText.Progress(Strings.En, 0, 9_800_000_000, null, false));
        Assert.Equal("Solistskiller", DownloadText.ComponentItem(Strings.Nb, Soloist));
        Assert.Equal("Instrument separator", DownloadText.ComponentItem(Strings.En, Instrument));
        Assert.Equal("Band writer (MuScriptor)", DownloadText.ComponentItem(Strings.En, Writer));
    }

    [Fact]
    public void Each_download_error_has_the_setup_windows_words()
    {
        var key = Problems.DownloadStopped(Strings.En, new DownloadError.KeyMissing());
        Assert.Equal("The band writer needs your Hugging Face access key", key.Title);
        Assert.Equal("Add an access key", key.FixLabel);
        var refused = Problems.DownloadStopped(Strings.En, new DownloadError.KeyRefused());
        Assert.Equal(ProblemKind.KeyRefused, refused.Kind);
        Assert.Equal("Hugging Face didn't accept the access key", refused.Title);
        Assert.Equal("Paste a new key", refused.FixLabel);
        var licence = Problems.DownloadStopped(Strings.Nb, new DownloadError.LicenceNotAccepted());
        Assert.Equal("Godta lisensen på Hugging Face, og prøv igjen", licence.Title);
        Assert.Equal("Åpne MuScriptor-siden", licence.FixLabel);
        var space = Problems.DownloadStopped(Strings.En, new DownloadError.NotEnoughSpace(4_200_000_000, 1_500_000_000));
        Assert.Equal("The downloads need about 4.2 GB; 1.5 GB is free.", space.Why);
        Assert.Equal("Free up space…", space.FixLabel);
        Assert.Equal("A download arrived damaged", Problems.DownloadStopped(Strings.En, new DownloadError.ChecksumMismatch("x")).Title);
        var network = Problems.DownloadStopped(Strings.En, new DownloadError.Http(500, "x"));
        Assert.Equal("The download stopped", network.Title);
        Assert.Equal("Try again", network.FixLabel);
        Assert.Equal("Disk full", Problems.DownloadStopped(Strings.En, new DownloadError.Disk("Disk full")).Why);
    }

    [Fact]
    public void The_engine_gets_the_shown_name_the_key_and_the_hub_cache()
    {
        var vars = new Dictionary<string, string?> { ["PATH"] = "/bin", ["HF_HUB_CACHE"] = @"D:\hub" };
        var config = new EngineLaunchConfig(new BandroomPaths(@"C:\data"), "pixi.exe", ComputerName.Shown("DESKTOP-4F2K9QZ", "Korpset"), "t", false)
        {
            HuggingFaceToken = () => "hf_saved",
            Variable = n => vars.GetValueOrDefault(n),
        };
        var env = config.Build(8765).Environment;
        Assert.Equal("Korpset", env["BRASSCRIBE_COMPUTER_NAME"]);
        Assert.Equal("hf_saved", env["HF_TOKEN"]);
        Assert.Equal(@"D:\hub", env["HF_HUB_CACHE"]);
        Assert.False(env.ContainsKey("HF_HOME"));

        vars["HF_TOKEN"] = "hf_env";
        Assert.Equal("hf_env", config.Build(8765).Environment["HF_TOKEN"]);
        Assert.False((config with { HuggingFaceToken = null, Variable = _ => null }).Build(8765).Environment.ContainsKey("HF_TOKEN"));
    }
}
