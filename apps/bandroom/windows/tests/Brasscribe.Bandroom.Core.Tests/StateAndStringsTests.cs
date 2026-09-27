using System.Text.RegularExpressions;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.Pairing;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;

namespace Brasscribe.Bandroom.Core.Tests;

public sealed class StringsTests
{
    [Fact]
    public void Both_languages_have_the_same_keys_and_placeholders()
    {
        Assert.Equal(Strings.En.All.Keys.Order(), Strings.Nb.All.Keys.Order());
        foreach (var (key, en) in Strings.En.All)
        {
            var holes = (string s) => Regex.Matches(s, @"\{\d+\}").Select(m => m.Value).Distinct().Order().ToList();
            Assert.True(holes(en).SequenceEqual(holes(Strings.Nb[key])), key);
            Assert.False(string.IsNullOrWhiteSpace(Strings.Nb[key]), key);
        }
    }

    [Fact]
    public void Percent_is_62_percent_in_english_and_62_space_percent_in_norwegian()
    {
        Assert.Equal("Brasscribe: making a score, 62%", Strings.En.Format("Tooltip_Busy", 62));
        Assert.Equal("Brasscribe: lager partitur, 62 %", Strings.Nb.Format("Tooltip_Busy", 62));
        Assert.Equal("62% · about 3 min left", Strings.En.Format("Now_Progress", 62, 3));
        Assert.Equal("62 % · omtrent 3 min igjen", Strings.Nb.Format("Now_Progress", 62, 3));
    }

    [Fact]
    public void The_code_is_shown_in_two_groups_and_read_digit_by_digit()
    {
        Assert.Equal("482 913", CodeText.Display("482913"));
        Assert.Equal("Code: 4 8 2, 9 1 3", CodeText.Spoken(Strings.En, "482913"));
        Assert.Equal("Kode: 4 8 2, 9 1 3", CodeText.Spoken(Strings.Nb, "482 913"));
        Assert.Equal("192 dot 168 dot 1 dot 20", CodeText.SpokenAddress(Strings.En, "192.168.1.20"));
    }

    [Fact]
    public void No_technical_words_in_the_body_copy()
    {
        foreach (var (key, value) in Strings.En.All.Where(kv => !kv.Key.StartsWith("Tech_", StringComparison.Ordinal)))
            Assert.DoesNotMatch(@"\b(server|engine|token|localhost|API|HTTP)\b", value);
    }
}

public sealed class StateTests
{
    private static StateInputs In(EngineState e = EngineState.Running, bool setup = true, IReadOnlyList<Problem>? problems = null,
        double? job = null, int online = 2, bool updating = false) =>
        new(e, setup, 0.32, updating, problems ?? [], job, online);

    [Fact]
    public void Precedence_error_attention_updating_busy_starting_running_stopped()
    {
        var disk = Problems.LowDisk(Strings.En, 2_100_000_000, "C:\\data");
        Assert.Equal(DisplayState.Error, StateRules.Resolve(In(EngineState.Error, problems: [disk])));
        Assert.Equal(DisplayState.NeedsAttention, StateRules.Resolve(In(problems: [disk], job: 0.5)));
        Assert.Equal(DisplayState.Updating, StateRules.Resolve(In(job: 0.5, updating: true)));
        Assert.Equal(DisplayState.Busy, StateRules.Resolve(In(job: 0.5)));
        Assert.Equal(DisplayState.Starting, StateRules.Resolve(In(EngineState.Starting)));
        Assert.Equal(DisplayState.Running, StateRules.Resolve(In()));
        Assert.Equal(DisplayState.Stopped, StateRules.Resolve(In(EngineState.Stopped)));
        Assert.Equal(DisplayState.SettingUp, StateRules.Resolve(In(EngineState.Stopped, setup: false)));
    }

    [Fact]
    public void Every_state_has_its_own_badge_shape()
    {
        var badges = Enum.GetValues<DisplayState>().Select(StateRules.Badge).ToList();
        Assert.Equal(badges.Count, badges.Distinct().Count());
        Assert.Equal(TrayBadge.None, StateRules.Badge(DisplayState.Running));
        Assert.Equal(TrayBadge.Triangle, StateRules.Badge(DisplayState.NeedsAttention));
        Assert.Equal(TrayBadge.CrossCircle, StateRules.Badge(DisplayState.Error));
    }

    [Fact]
    public void Tooltips_spell_the_state_out()
    {
        Assert.Equal("Brasscribe: running · 2 phones connected", StateRules.Describe(In(), Strings.En).Tooltip);
        Assert.Equal("Brasscribe: running · 1 phone connected", StateRules.Describe(In(online: 1), Strings.En).Tooltip);
        Assert.Equal("Brasscribe: kjører · 1 telefon tilkoblet", StateRules.Describe(In(online: 1), Strings.Nb).Tooltip);
        var busy = StateRules.Describe(In(job: 0.62), Strings.En);
        Assert.Equal("Brasscribe: making a score, 62%", busy.Tooltip);
        Assert.Equal(4, busy.PieEighths);
        Assert.Equal("Brasscribe: setting up, 32%", StateRules.Describe(In(EngineState.Stopped, setup: false), Strings.En).Tooltip);
        var port = StateRules.Describe(In(EngineState.Stopped, problems: [Problems.NoFreePort(Strings.En)]), Strings.En);
        Assert.Equal("Brasscribe needs attention: Brasscribe can't start", port.Tooltip);
        Assert.Equal(PrimaryAction.Fix, port.Primary);
        Assert.Equal("Restart", port.PrimaryLabel);
        Assert.Equal("Brasscribe stopped unexpectedly", StateRules.Describe(In(EngineState.Error), Strings.En).Tooltip);
    }

    [Fact]
    public void One_primary_per_state()
    {
        Assert.Equal(PrimaryAction.PairPhone, StateRules.Describe(In(), Strings.En).Primary);
        Assert.Equal(PrimaryAction.PairPhone, StateRules.Describe(In(job: 0.2), Strings.En).Primary);
        Assert.Equal(PrimaryAction.StartEngine, StateRules.Describe(In(EngineState.Stopped), Strings.En).Primary);
        Assert.Equal(PrimaryAction.TryAgain, StateRules.Describe(In(EngineState.Error), Strings.En).Primary);
        Assert.Equal(PrimaryAction.FinishSetup, StateRules.Describe(In(EngineState.Stopped, setup: false), Strings.En).Primary);
        Assert.Equal(PrimaryAction.None, StateRules.Describe(In(EngineState.Starting), Strings.En).Primary);
    }

    [Theory]
    [InlineData(10, Level.Low)]
    [InlineData(39.9, Level.Low)]
    [InlineData(40, Level.Mid)]
    [InlineData(85, Level.Mid)]
    [InlineData(85.1, Level.High)]
    public void Work_load_words(double pct, Level level) => Assert.Equal(level, HealthWords.Load(pct));

    [Theory]
    [InlineData(0.5, Level.Low)]
    [InlineData(0.25, Level.Mid)]
    [InlineData(0.10, Level.Mid)]
    [InlineData(0.09, Level.High)]
    public void Memory_words(double free, Level level) => Assert.Equal(level, HealthWords.Memory(free));

    [Fact]
    public void Load_is_a_thirty_second_average()
    {
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider();
        var avg = new LoadAverager(time);
        avg.Add(100);
        time.Advance(TimeSpan.FromSeconds(10));
        Assert.Equal(50, avg.Add(0));
        time.Advance(TimeSpan.FromSeconds(25));
        Assert.Equal(0, avg.Add(0), 3); // the 100 is older than 30 s
    }

    [Fact]
    public void The_running_job_gives_the_step_and_time_left()
    {
        var now = DateTimeOffset.FromUnixTimeSeconds(1_000_600);
        var jobs = new List<JobInfo>
        {
            new("j0", "p", "Old", "succeeded", 1, 2, 3, 1, []),
            new("j1", "p", "Mikkel", "running", 1_000_000, 1_000_000, null, 0.5,
                [new("beats", "ran"), new("transcribe.muscriptor", "started"), new("arrange", "pending")]),
        };
        var job = JobView.From(jobs, now)!;
        Assert.Equal("Mikkel", job.Title);
        Assert.Equal("Step_Notes", job.StepKey);
        Assert.Equal(10, job.MinutesLeft);
        Assert.Null(JobView.From([jobs[0]], now));
    }

    [Fact]
    public void The_qr_is_a_png_with_a_quiet_zone()
    {
        var uri = "brasscribe://pair?v=1&id=3f9c2a7e11&name=Brasscribe%20on%20Kalli%27s%20PC&h=192.168.1.20:8765&code=482913";
        var png = QrImage.Png(uri);
        Assert.Equal(new byte[] { 0x89, 0x50, 0x4E, 0x47 }, png[..4]);
        Assert.True(QrImage.Modules(uri) >= 21 + 8);
    }
}
