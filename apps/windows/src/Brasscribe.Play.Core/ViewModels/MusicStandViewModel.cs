using System.ComponentModel;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.Stand;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>
/// The music stand (design/music-stand.md): the score alone, in pages, for playing from a stand. It
/// opens on your part (the player's own part, else the part shown; §12.1), keeps the position as plain
/// text in a band at the top with Leave, and has one control layer that hides itself while the music
/// plays (<see cref="StandLayer"/>). Playback turns the pages unless Settings says not to (§12.2).
/// The view lays out the score, hands the systems over with <see cref="SetPages"/>, and scrolls to
/// <see cref="Page"/> when <see cref="PageChanged"/> fires.
/// </summary>
public sealed partial class MusicStandViewModel : ObservableObject
{
    private readonly ScoreViewModel _score;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private StandPages _pages = StandPages.Empty;
    private int _savedPart = -1;
    private bool _savedTalkingScore;
    private int _followed = -1;
    private bool _applyingPart;

    public MusicStandViewModel(ScoreViewModel score, IAnnouncer announcer, IStrings strings)
    {
        _score = score;
        _announcer = announcer;
        _s = strings;
        Layer = NewLayer(false);
        score.Player.PropertyChanged += OnPlayerChanged;
        score.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(ScoreViewModel.Title) or nameof(ScoreViewModel.SelectedPartIndex) or nameof(ScoreViewModel.IsLoaded))
                UpdateTexts();
        };
    }

    public StandLayer Layer { get; private set; }

    private StandLayer NewLayer(bool hintSeen)
    {
        var layer = new StandLayer(hintSeen);
        layer.Changed += (_, _) =>
        {
            if (!ReferenceEquals(layer, Layer)) return;
            IsLayerShown = layer.IsShown;
            IsHintShown = layer.HintShown;
            if (layer.HintSeen && !HintSeen) HintSeen = true;
        };
        return layer;
    }

    [ObservableProperty] public partial bool IsOpen { get; private set; }
    [ObservableProperty] public partial bool IsLayerShown { get; private set; }
    [ObservableProperty] public partial bool IsHintShown { get; private set; }

    /// <summary>Settings → Display → Keep the stand controls visible.</summary>
    [ObservableProperty] public partial bool KeepControlsVisible { get; set; }

    /// <summary>Settings → Display → Turn the pages while playing (on by default).</summary>
    [ObservableProperty] public partial bool TurnPagesWhilePlaying { get; set; } = true;

    /// <summary>The first-time hint was dismissed; it never comes back (persisted by the settings).</summary>
    [ObservableProperty] public partial bool HintSeen { get; set; }

    /// <summary>Only my part: on shows your part alone; off goes back to the parts shown before.</summary>
    [ObservableProperty] public partial bool OnlyMyPart { get; set; } = true;

    /// <summary>The page on the left (the only page when there is no spread), 0-based.</summary>
    [ObservableProperty] public partial int Page { get; private set; }

    [ObservableProperty] public partial string PositionTitle { get; private set; } = "";
    [ObservableProperty] public partial string PositionDetail { get; private set; } = "";
    [ObservableProperty] public partial string PositionName { get; private set; } = "";
    [ObservableProperty] public partial string SpeedText { get; private set; } = "";
    [ObservableProperty] public partial string RepeatText { get; private set; } = "";

    /// <summary>There is a part to call yours: without one, Only my part is hidden (my-instrument §3.4).</summary>
    public bool HasMyPart => _score.MyPartIndex >= 0;

    /// <summary>The player's part changed (Make this my part, or the seat in Settings): Only my part follows it.</summary>
    public void YourPartChanged()
    {
        OnPropertyChanged(nameof(HasMyPart));
        if (!IsOpen) return;
        ApplyPart();
        UpdateTexts();
    }

    public StandPages Pages => _pages;
    public int PageCount => _pages.Count;

    /// <summary>The bar the stand follows: the player's position (1-based).</summary>
    public int CurrentBar => Math.Max(1, _score.Player.CurrentBar);

    /// <summary>The page changed; the argument is true when the player turned it (the view may animate either way).</summary>
    public event EventHandler<bool>? PageChanged;

    /// <summary>The stand opened or closed (the view takes the window full screen, and moves focus).</summary>
    public event EventHandler? Opened;
    public event EventHandler? Closed;

    [RelayCommand]
    public void Toggle()
    {
        if (IsOpen) Leave();
        else Enter();
    }

    /// <summary>Tells whether a screen reader runs (the platform's check; none in tests).</summary>
    public Func<bool>? DetectScreenReader { get; set; }

    /// <summary>Opens the stand on your part; with a screen reader the layer stays and the touch hint is not said.</summary>
    public void Enter(bool? screenReader = null)
    {
        if (IsOpen || !_score.IsLoaded) return;
        bool reader = screenReader ?? DetectScreenReader?.Invoke() ?? false;
        Layer = NewLayer(HintSeen);
        _savedPart = _score.SelectedPartIndex;
        // The stand is the music: Read aloud's text list gives way while it is open.
        _savedTalkingScore = _score.ShowTalkingScore;
        _score.ShowTalkingScore = false;
        _followed = -1;
        _applyingPart = true;
        OnlyMyPart = true;
        _applyingPart = false;
        IsOpen = true;
        ApplyPart();
        Layer.Enter(new StandContext(_score.Player.IsPlaying, reader, KeepVisible: KeepControlsVisible));
        OnPropertyChanged(nameof(HasMyPart));
        UpdateTexts();
        Opened?.Invoke(this, EventArgs.Empty);
        string said = _s.Format("Stand_Entered", PartText(), CurrentBar, Math.Max(1, _score.Player.BarCount));
        if (!reader) said += " " + _s["Stand_EnteredTouch"];
        _announcer.Announce(said);
    }

    [RelayCommand]
    public void Leave() => Leave(announce: true);

    public void Leave(bool announce)
    {
        if (!IsOpen) return;
        IsOpen = false;
        if (_score.SelectedPartIndex != _savedPart) _score.ShowPartQuietly(_savedPart);
        _score.ShowTalkingScore = _savedTalkingScore;
        _pages = StandPages.Empty;
        Page = 0;
        IsLayerShown = false;
        IsHintShown = false;
        Closed?.Invoke(this, EventArgs.Empty);
        if (announce) _announcer.Announce(_s["Stand_Left"]);
    }

    partial void OnOnlyMyPartChanged(bool value)
    {
        if (_applyingPart || !IsOpen) return;
        ApplyPart();
        UpdateTexts();
    }

    /// <summary>Your part alone, or the parts shown before the stand; quietly (the stand speaks for itself).</summary>
    private void ApplyPart()
    {
        int wanted = OnlyMyPart && HasMyPart ? _score.MyPartIndex : _savedPart;
        if (_score.SelectedPartIndex != wanted) _score.ShowPartQuietly(wanted);
    }

    /// <summary>A new layout: the page that holds the current bar is shown, without an announcement.</summary>
    public void SetPages(StandPages pages)
    {
        _pages = pages;
        OnPropertyChanged(nameof(Pages));
        OnPropertyChanged(nameof(PageCount));
        int page = pages.PageOfBar(CurrentBar - 1);
        _followed = page;
        Page = page;
        UpdateTexts();
        PageChanged?.Invoke(this, false);
    }

    public void NextPage() => TurnTo(Page + 1);
    public void PreviousPage() => TurnTo(Page - 1);
    public void FirstPage() => TurnTo(0);
    public void LastPage() => TurnTo(_pages.LastLeftPage);

    /// <summary>A turn the player makes: it is announced ("Page 4 of 33, bars 13 to 20."); at either end it says so.</summary>
    private void TurnTo(int page)
    {
        if (_pages.Count == 0) return;
        int target = _pages.Clamp(page);
        if (target == Page)
        {
            _announcer.Announce(_s[page < Page ? "Stand_FirstPage" : "Stand_LastPage"]);
            return;
        }
        Page = target;
        UpdateTexts();
        PageChanged?.Invoke(this, true);
        var (first, last) = _pages.BarsInView(target);
        _announcer.Announce(_s.Format("Stand_PageTurned", target + 1, _pages.Count, first + 1, last + 1));
    }

    /// <summary>
    /// The current bar moved. While playing, the pages follow it when the setting allows (a turn made
    /// by playback is not announced). Otherwise a bar move that leaves the view brings its page.
    /// </summary>
    private void FollowBar()
    {
        if (!IsOpen || _pages.Count == 0) return;
        int bar = CurrentBar - 1;
        int target = _pages.PageOfBar(bar);
        bool turn = _score.Player.IsPlaying
            ? TurnPagesWhilePlaying && target != _followed && target != Page
            : !_pages.IsInView(Page, bar);
        _followed = target;
        if (turn)
        {
            Page = target;
            PageChanged?.Invoke(this, false);
        }
    }

    private void OnPlayerChanged(object? sender, PropertyChangedEventArgs e)
    {
        switch (e.PropertyName)
        {
            case nameof(PlayerViewModel.CurrentBar):
                FollowBar();
                UpdateTexts();
                break;
            case nameof(PlayerViewModel.SpeedPercent) or nameof(PlayerViewModel.IsLooping) or nameof(PlayerViewModel.LoopStart) or nameof(PlayerViewModel.LoopEnd):
                UpdateTexts();
                break;
        }
    }

    /// <summary>"Solo Cornet (you)" for your part, the plain name for another, "All parts" for the full score.</summary>
    public string PartText()
    {
        int shown = _score.SelectedPartIndex;
        if (shown < 0 || shown >= _score.Parts.Count) return _s["Score_FullScore"];
        string name = _score.Parts[shown].Name;
        return shown == _score.MyPartIndex ? _s.Format("Stand_PartYours", name) : name;
    }

    /// <summary>"page 4 of 33", or "pages 1–2 of 6" in a spread.</summary>
    public string PageText()
    {
        int count = Math.Max(1, _pages.Count);
        int page = Math.Min(Page, count - 1);
        return _pages.IsSpread && page + 1 < _pages.Count
            ? _s.Format("Stand_Pages", page + 1, page + 2, count)
            : _s.Format("Stand_Page", page + 1, count);
    }

    private void UpdateTexts()
    {
        PositionTitle = _score.Title;
        PositionDetail = _s.Format("Stand_Detail", PartText(), CurrentBar, PageText());
        PositionName = PositionTitle.Length > 0 ? $"{PositionTitle} · {PositionDetail}" : PositionDetail;
        SpeedText = _s.Format("Stand_Speed", Screens.Percent(_score.Player.SpeedPercent, _s.Language));
        var p = _score.Player;
        RepeatText = p.IsLooping ? _s.Format("Stand_RepeatOn", (int)Math.Round(p.LoopStart), (int)Math.Round(p.LoopEnd)) : _s["Stand_Repeat"];
    }

    /// <summary>Repeat in the stand: stops a repeat, repeats the bars already chosen; false when bars have to be chosen first (the view opens the bar fields).</summary>
    public bool ToggleRepeat()
    {
        var p = _score.Player;
        if (p.IsLooping)
        {
            p.ClearLoopCommand.Execute(null);
            return true;
        }
        if (p.LoopChosen)
        {
            p.SetLoopCommand.Execute(null);
            return true;
        }
        return false;
    }

    // ---- the control layer ----

    public void Tap() => Layer.Tap();
    public void KeyPressed() => Layer.Key();
    public void Touched() => Layer.Touched();
    public bool AutoHide(StandContext context) => Layer.AutoHide(context with { KeepVisible = context.KeepVisible || KeepControlsVisible });
}
