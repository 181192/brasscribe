using Brasscribe.Play.Core.TalkingScore;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Automation.Text;
using Windows.Foundation;

namespace Brasscribe.Play.Controls;

/// <summary>
/// UI Automation for the score (Narrator, NVDA, Magnifier):
/// <list type="bullet">
/// <item>List control type with one list-item child per event of the current bar, each with its bounding rectangle so Magnifier follows the focused note;</item>
/// <item>Value pattern: the current talking-score announcement, changed and raised as a notification on every move;</item>
/// <item>Text pattern: the whole part as talking-score text, one line per event, with the current event as the selection, so a screen reader can also read and review it as a document.</item>
/// </list>
/// The strings come from the core announcer; this peer never builds them.
/// </summary>
public sealed partial class ScoreViewAutomationPeer : FrameworkElementAutomationPeer, IValueProvider, ITextProvider
{
    private readonly ScoreView _owner;
    private string _lastValue = "";

    public ScoreViewAutomationPeer(ScoreView owner) : base(owner) => _owner = owner;

    protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.List;
    protected override string GetLocalizedControlTypeCore() => _owner.LocalizedControlType;
    protected override string GetClassNameCore() => nameof(ScoreView);
    protected override bool IsKeyboardFocusableCore() => true;

    protected override object GetPatternCore(PatternInterface patternInterface) => patternInterface switch
    {
        PatternInterface.Value or PatternInterface.Text => this,
        _ => base.GetPatternCore(patternInterface),
    };

    private int _childrenVersion = -1;
    private List<AutomationPeer> _children = [];

    /// <summary>One list item per event of the current bar that has a place on screen; cached per bar so runtime ids stay stable.</summary>
    protected override IList<AutomationPeer> GetChildrenCore()
    {
        if (_childrenVersion != _owner.EventsVersion)
        {
            var shown = _owner.CurrentEvents.Where(e => e.Bounds.Width > 0 && e.Bounds.Height > 0).ToList();
            _children = shown
                .Select((e, i) => (AutomationPeer)new ScoreEventAutomationPeer(this, e, i + 1, shown.Count))
                .ToList();
            _childrenVersion = _owner.EventsVersion;
        }
        return _children;
    }

    // ---- Value pattern ----

    public bool IsReadOnly => true;
    public string Value => _owner.ViewModel?.Announcement ?? "";
    public void SetValue(string value) => throw new InvalidOperationException("The score value is read-only");

    // ---- Text pattern ----

    internal string DocumentText => _owner.ViewModel is { } vm ? string.Join('\n', vm.TalkingLines) + "\n" : "";

    public ITextRangeProvider DocumentRange => new ScoreTextRange(this, new TextRangeModel(DocumentText, 0, int.MaxValue));

    public SupportedTextSelection SupportedTextSelection => SupportedTextSelection.Single;

    public ITextRangeProvider[] GetSelection()
    {
        string text = DocumentText;
        int line = _owner.ViewModel?.CurrentLineIndex ?? 0;
        var (s, e) = TextRangeModel.LineSpan(text, Math.Max(0, line));
        return [new ScoreTextRange(this, new TextRangeModel(text, s, e))];
    }

    public ITextRangeProvider[] GetVisibleRanges() => [DocumentRange];

    public ITextRangeProvider RangeFromChild(IRawElementProviderSimple childElement) => GetSelection()[0];

    public ITextRangeProvider RangeFromPoint(Point screenLocation) => GetSelection()[0];

    internal IRawElementProviderSimple Provider => ProviderFromPeer(this);

    internal Rect ScreenBounds(Rect local) => _owner.SurfaceToScreen(local, GetBoundingRectangle());

    internal Rect FocusBounds => _owner.FocusRect is { } r ? ScreenBounds(r) : GetBoundingRectangle();

    internal void ScrollTo() => _owner.Focus(Microsoft.UI.Xaml.FocusState.Programmatic);

    /// <summary>Called when the talking-score cursor moves: value change, selection change and a notification.</summary>
    internal void RaiseCursorMoved(string text)
    {
        RaisePropertyChangedEvent(ValuePatternIdentifiers.ValueProperty, _lastValue, text);
        _lastValue = text;
        RaiseAutomationEvent(AutomationEvents.TextPatternOnTextSelectionChanged);
        RaiseNotificationEvent(AutomationNotificationKind.ActionCompleted, AutomationNotificationProcessing.MostRecent, text, "ScoreCursor");
    }

    internal void RaiseFocusedTextChanged()
    {
        if (Value.Length == 0) return;
        RaisePropertyChangedEvent(ValuePatternIdentifiers.ValueProperty, _lastValue, Value);
        _lastValue = Value;
    }

    internal void RaiseChildrenChanged() => RaiseStructureChangedEvent(AutomationStructureChangeType.ChildrenInvalidated, this);
}

/// <summary>One event of the current bar as a list item; its name is the brief announcement.</summary>
public sealed partial class ScoreEventAutomationPeer(ScoreViewAutomationPeer parent, ScoreEventItem item, int position, int count) : AutomationPeer
{
    protected override string GetNameCore() => item.Name;
    // "3 of 7": list items need their place in the bar's list.
    protected override int GetPositionInSetCore() => position;
    protected override int GetSizeOfSetCore() => count;
    protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.ListItem;
    protected override string GetClassNameCore() => "ScoreEvent";
    protected override bool IsContentElementCore() => true;
    protected override bool IsControlElementCore() => true;
    protected override bool IsKeyboardFocusableCore() => false;
    // Keyboard focus stays on the score (the list); the current event is exposed through Value and Text.
    protected override bool HasKeyboardFocusCore() => false;
    protected override Rect GetBoundingRectangleCore() => parent.ScreenBounds(item.Bounds);
    protected override AutomationPeer GetPeerFromPointCore(Point point) => this;
    protected override bool IsOffscreenCore() => false;
    protected override IList<AutomationPeer> GetChildrenCore() => [];
}

/// <summary>ITextRangeProvider over the talking-score text, backed by <see cref="TextRangeModel"/>.</summary>
internal sealed partial class ScoreTextRange(ScoreViewAutomationPeer owner, TextRangeModel model) : ITextRangeProvider
{
    public TextRangeModel Model { get; } = model;

    private static TextUnitKind Unit(TextUnit u) => (TextUnitKind)(int)u;

    private static int Endpoint(TextRangeModel m, TextPatternRangeEndpoint e) =>
        e == TextPatternRangeEndpoint.Start ? m.Start : m.End;

    public ITextRangeProvider Clone() => new ScoreTextRange(owner, Model.Clone());

    public bool Compare(ITextRangeProvider textRangeProvider) =>
        textRangeProvider is ScoreTextRange o && o.Model.Start == Model.Start && o.Model.End == Model.End;

    public int CompareEndpoints(TextPatternRangeEndpoint endpoint, ITextRangeProvider textRangeProvider, TextPatternRangeEndpoint targetEndpoint)
    {
        var other = ((ScoreTextRange)textRangeProvider).Model;
        return Endpoint(Model, endpoint).CompareTo(Endpoint(other, targetEndpoint));
    }

    public void ExpandToEnclosingUnit(TextUnit unit) => Model.ExpandToEnclosingUnit(Unit(unit));

    public ITextRangeProvider FindAttribute(int attributeId, object value, bool backward) => null!;

    public ITextRangeProvider FindText(string text, bool backward, bool ignoreCase)
    {
        int at = Model.Find(text, backward, ignoreCase);
        return at < 0 ? null! : new ScoreTextRange(owner, new TextRangeModel(Model.Text, at, at + text.Length));
    }

    public object GetAttributeValue(int attributeId) => null!;

    public void GetBoundingRectangles(out double[] returnValue)
    {
        var r = owner.FocusBounds;
        returnValue = [r.X, r.Y, r.Width, r.Height];
    }

    public IRawElementProviderSimple GetEnclosingElement() => owner.Provider;

    public string GetText(int maxLength) => Model.GetText(maxLength);

    public int Move(TextUnit unit, int count) => Model.Move(Unit(unit), count);

    public int MoveEndpointByUnit(TextPatternRangeEndpoint endpoint, TextUnit unit, int count) =>
        Model.MoveEndpointByUnit(endpoint == TextPatternRangeEndpoint.Start, Unit(unit), count);

    public void MoveEndpointByRange(TextPatternRangeEndpoint endpoint, ITextRangeProvider textRangeProvider, TextPatternRangeEndpoint targetEndpoint)
    {
        var other = ((ScoreTextRange)textRangeProvider).Model;
        Model.SetEndpoint(endpoint == TextPatternRangeEndpoint.Start, Endpoint(other, targetEndpoint));
    }

    public void Select() { }
    public void AddToSelection() { }
    public void RemoveFromSelection() { }
    public void ScrollIntoView(bool alignToTop) => owner.ScrollTo();
    public IRawElementProviderSimple[] GetChildren() => [];
}
