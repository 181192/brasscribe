using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI;
using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;
using Windows.System;
using Windows.UI.Core;

namespace Brasscribe.Play.Controls;

/// <summary>A rendered piece of notation at its place in the whole score.</summary>
public sealed record ScorePage(ImageSource Image, Rect Bounds);

/// <summary>An event of the current bar, exposed to UI Automation as a list item.</summary>
public sealed record ScoreEventItem(string Name, Rect Bounds, bool IsCurrent);

/// <summary>
/// The notation view. It shows alphaTab's rendered pages and draws the overlays planned by
/// <see cref="ScoreOverlay"/> in the score tokens (design/system.md §6): tints (cursor bar, repeated
/// bars, ad lib bars) under the notation, and over it the 3 epx cursor, the loop brackets and label,
/// dashed ad lib bar lines, and a "?" (boxed below 0.4) above each uncertain note, so uncertainty
/// never relies on colour alone. The focused note gets a 2 epx outline with a 2 epx gap.
/// It is one keyboard focus stop; inside it the score keys of
/// <see cref="ScoreKeyMap"/> move a talking-score cursor, whose announcement is exposed through the
/// automation peer's Value and Text patterns. Tab and Shift+Tab leave the score.
/// </summary>
public sealed partial class ScoreView : UserControl
{
    private readonly ScrollViewer _scroller;
    private readonly Grid _surface;
    private readonly Canvas _underlay;
    private readonly Canvas _cursorUnder;
    private readonly Canvas _cursorOver;
    private readonly Canvas _pages;
    private readonly Canvas _overlay;
    private readonly Canvas _marks;
    private readonly Rectangle _focusBox;
    private ScoreViewModel? _viewModel;
    private ScoreViewAutomationPeer? _peer;

    public ScoreView()
    {
        IsTabStop = true;
        UseSystemFocusVisuals = true;
        TabFocusNavigation = KeyboardNavigationMode.Once;
        _underlay = new Canvas { IsHitTestVisible = false };
        _cursorUnder = new Canvas { IsHitTestVisible = false };
        _pages = new Canvas();
        _overlay = new Canvas { IsHitTestVisible = false };
        _cursorOver = new Canvas { IsHitTestVisible = false };
        _marks = new Canvas { IsHitTestVisible = false };
        _surface = new Grid { Children = { _underlay, _cursorUnder, _pages, _overlay, _cursorOver, _marks } };
        _scroller = new ScrollViewer
        {
            Content = _surface,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            ZoomMode = ZoomMode.Disabled,
            IsTabStop = false,
        };
        Content = _scroller;

        _focusBox = new Rectangle { StrokeThickness = 2, Fill = null, Visibility = Visibility.Collapsed, RadiusX = 2, RadiusY = 2 };
        _marks.Children.Add(_focusBox);

        _scroller.ViewChanged += (_, _) => ViewportChanged?.Invoke(this, Viewport);
        _scroller.SizeChanged += (_, _) => ViewportChanged?.Invoke(this, Viewport);
        ActualThemeChanged += (_, _) =>
        {
            ApplyBrushes();
            SetOverlay(_items);
            SetCursor(_cursor);
        };
        Loaded += (_, _) => ApplyBrushes();
        GotFocus += (_, _) => _peer?.RaiseFocusedTextChanged();
        // The "?" marks can be tapped (a 44 epx target around each) to check that note.
        _surface.Tapped += (_, e) =>
        {
            var p = e.GetPosition(_surface);
            var hit = _items.FirstOrDefault(i => i.Kind is OverlayKind.UncertainMark or OverlayKind.VeryUncertainMark
                                                 && Math.Abs(i.Box.X + i.Box.W / 2 - p.X) <= 22 && Math.Abs(i.Box.Y + i.Box.H / 2 - p.Y) <= 22);
            if (hit is null) return;
            e.Handled = true;
            MarkInvoked?.Invoke(this, hit);
        };
    }

    /// <summary>Localised control type spoken by screen readers ("score", "partitur").</summary>
    public string LocalizedControlType { get; set; } = "score";

    /// <summary>No smooth scrolling when the user reduces motion (WCAG 2.2.2, 2.3.3).</summary>
    public bool ReduceMotion { get; set; }

    /// <summary>Pixels kept free at the bottom so the player bar never covers the focused note (WCAG 2.4.11).</summary>
    public double BottomObscuredHeight { get; set; } = 96;

    /// <summary>
    /// Screen rectangle (physical pixels) of a rectangle on the score surface, given this control's own
    /// screen bounds from its automation peer. Accounts for scrolling and display scale.
    /// </summary>
    internal Rect SurfaceToScreen(Rect local, Rect ownScreenBounds)
    {
        double scale = XamlRoot?.RasterizationScale ?? 1.0;
        var origin = _scroller.TransformToVisual(this).TransformPoint(new Point(0, 0));
        double x = ownScreenBounds.X + (origin.X + local.X - _scroller.HorizontalOffset) * scale;
        double y = ownScreenBounds.Y + (origin.Y + local.Y - _scroller.VerticalOffset) * scale;
        return new Rect(x, y, local.Width * scale, local.Height * scale);
    }

    /// <summary>Changes whenever <see cref="CurrentEvents"/> is replaced, so peers can be cached per bar.</summary>
    internal int EventsVersion { get; private set; }

    public IReadOnlyList<ScoreEventItem> CurrentEvents { get; private set; } = [];

    public event EventHandler? LeaveRequested;

    /// <summary>A "?" mark was tapped.</summary>
    public event EventHandler<OverlayItem>? MarkInvoked;
    public event EventHandler? GoToBarRequested;

    public ScoreViewModel? ViewModel
    {
        get => _viewModel;
        set
        {
            if (_viewModel is not null) _viewModel.CursorMoved -= OnCursorMoved;
            _viewModel = value;
            if (_viewModel is not null) _viewModel.CursorMoved += OnCursorMoved;
        }
    }

    public Rect? FocusRect { get; private set; }

    private readonly Dictionary<string, (Rect Bounds, Image? Image)> _slots = [];

    /// <summary>Raised when the visible part of the score surface changes (scrolling, resizing, zoom).</summary>
    public event EventHandler<Rect>? ViewportChanged;

    /// <summary>The visible rectangle in score-surface coordinates.</summary>
    public Rect Viewport => new(_scroller.HorizontalOffset, _scroller.VerticalOffset,
        Math.Max(0, _scroller.ViewportWidth), Math.Max(0, _scroller.ViewportHeight));

    /// <summary>Places empty pages for a new layout; images arrive later through <see cref="SetPageImage"/>.</summary>
    public void SetPageSlots(IEnumerable<(string Id, Rect Bounds)> slots, double totalWidth, double totalHeight)
    {
        _pages.Children.Clear();
        _slots.Clear();
        foreach (var (id, bounds) in slots) _slots[id] = (bounds, null);
        _surface.Width = totalWidth;
        _surface.Height = totalHeight;
        ViewportChanged?.Invoke(this, Viewport);
    }

    /// <summary>Ids of pages that intersect the viewport, grown by <paramref name="margin"/> viewports above and below.</summary>
    public IEnumerable<string> PagesNear(Rect viewport, double margin = 1.0)
    {
        double grow = viewport.Height * margin;
        var area = new Rect(viewport.X - viewport.Width * margin, Math.Max(0, viewport.Y - grow),
            viewport.Width * (1 + 2 * margin), viewport.Height + 2 * grow);
        foreach (var (id, slot) in _slots)
        {
            var r = slot.Bounds;
            if (r.X < area.X + area.Width && r.X + r.Width > area.X && r.Y < area.Y + area.Height && r.Y + r.Height > area.Y)
                yield return id;
        }
    }

    public bool HasPageImage(string id) => _slots.TryGetValue(id, out var s) && s.Image is not null;

    public void SetPageImage(string id, ImageSource source)
    {
        if (!_slots.TryGetValue(id, out var slot)) return;
        var img = new Image { Source = source, Width = slot.Bounds.Width, Height = slot.Bounds.Height, Stretch = Stretch.Fill };
        AutomationProperties.SetAccessibilityView(img, AccessibilityView.Raw);
        Canvas.SetLeft(img, slot.Bounds.X);
        Canvas.SetTop(img, slot.Bounds.Y);
        _pages.Children.Add(img);
        _slots[id] = (slot.Bounds, img);
    }

    /// <summary>Drops images far outside the viewport to bound memory; they are requested again when scrolled back.</summary>
    public IReadOnlyList<string> ReleaseFarPages(Rect viewport, double keep = 4.0)
    {
        var near = PagesNear(viewport, keep).ToHashSet();
        var released = new List<string>();
        foreach (var (id, slot) in _slots.ToList())
        {
            if (slot.Image is null || near.Contains(id)) continue;
            _pages.Children.Remove(slot.Image);
            _slots[id] = (slot.Bounds, null);
            released.Add(id);
        }
        return released;
    }

    public void SetPages(IReadOnlyList<ScorePage> pages, double totalWidth, double totalHeight)
    {
        _pages.Children.Clear();
        foreach (var p in pages)
        {
            var img = new Image { Source = p.Image, Width = p.Bounds.Width, Height = p.Bounds.Height, Stretch = Stretch.Fill };
            AutomationProperties.SetAccessibilityView(img, AccessibilityView.Raw); // the score peer speaks for the notation
            Canvas.SetLeft(img, p.Bounds.X);
            Canvas.SetTop(img, p.Bounds.Y);
            _pages.Children.Add(img);
        }
        _surface.Width = totalWidth;
        _surface.Height = totalHeight;
    }

    private IReadOnlyList<OverlayItem> _items = [];
    private IReadOnlyList<OverlayItem> _cursor = [];

    /// <summary>The overlays of the current layout and loop (see <see cref="ScoreOverlay.Build"/>).</summary>
    public void SetOverlay(IReadOnlyList<OverlayItem> items)
    {
        _items = items;
        Draw(items, _underlay, _overlay);
    }

    /// <summary>Moves the playback cursor (see <see cref="ScoreOverlay.Cursor"/>); in reduced motion the caller moves it per beat, never animated.</summary>
    public void SetCursor(IReadOnlyList<OverlayItem> items)
    {
        _cursor = items;
        Draw(items, _cursorUnder, _cursorOver);
    }

    private void Draw(IReadOnlyList<OverlayItem> items, Canvas under, Canvas over)
    {
        under.Children.Clear();
        over.Children.Clear();
        foreach (var item in items)
        {
            var b = item.Box;
            switch (item.Kind)
            {
                case OverlayKind.CursorTint: Add(under, Fill(b, "BcCursorTintBrush")); break;
                case OverlayKind.LoopTint: Add(under, Fill(b, "BcLoopTintBrush")); break;
                case OverlayKind.AdlibTint: Add(under, Fill(b, "BcAdlibTintBrush")); break;
                case OverlayKind.CursorLine: Add(over, Fill(b, "BcCursorBrush")); break;
                case OverlayKind.LoopEdge: AddBracket(over, b, left: !items.Any(o => o.Kind == OverlayKind.LoopEdge && o.Box.Y == b.Y && o.Box.X < b.X)); break;
                case OverlayKind.Outline:
                    Add(over, new Rectangle { Width = b.W, Height = b.H, Stroke = Brush("BcInkBrush"), StrokeThickness = 1 }, b.X, b.Y);
                    break;
                case OverlayKind.DashedBarLine:
                    Add(over, new Line { X1 = 0, Y1 = 0, X2 = 0, Y2 = b.H, Stroke = Brush("BcStaffBrush"), StrokeThickness = 1, StrokeDashArray = [4, 3] }, b.X, b.Y);
                    break;
                case OverlayKind.LoopLabel:
                    Add(over, new TextBlock { Text = item.Text, FontSize = 12, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, Foreground = Brush("BcLoopEdgeBrush") }, b.X, b.Y);
                    break;
                case OverlayKind.AdlibText:
                    Add(over, new TextBlock { Text = item.Text, FontSize = 17, FontStyle = Windows.UI.Text.FontStyle.Italic, Foreground = Brush("BcInkBrush"),
                        FontFamily = DisplayItalic }, b.X, b.Y);
                    break;
                case OverlayKind.UncertainMark:
                    Add(over, Mark(b, "BcUncertainBrush", boxed: false), b.X, b.Y);
                    break;
                case OverlayKind.VeryUncertainMark:
                    Add(over, Mark(b, "BcVeryUncertainBrush", boxed: true), b.X, b.Y);
                    break;
            }
        }
    }

    /// <summary>The display face's italic (for "ad lib." when the score does not engrave it).</summary>
    private static FontFamily DisplayItalic => Application.Current.Resources.TryGetValue("BcDisplayItalicFontFamily", out var f) && f is FontFamily ff
        ? ff : new FontFamily("Georgia");

    private FrameworkElement Mark(Box b, string brush, bool boxed)
    {
        var text = new TextBlock
        {
            Text = "?",
            FontWeight = Microsoft.UI.Text.FontWeights.Bold,
            FontSize = Math.Max(10, b.H * (boxed ? 0.75 : 0.95)),
            Foreground = Brush(brush),
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            TextAlignment = TextAlignment.Center,
            LineHeight = b.H,
        };
        return new Border
        {
            Width = b.W,
            Height = b.H,
            BorderBrush = boxed ? Brush(brush) : null,
            BorderThickness = new Thickness(boxed ? 1.5 : 0),
            CornerRadius = new CornerRadius(2),
            Child = text,
        };
    }

    private Rectangle Fill(Box b, string brush) => new() { Width = Math.Max(0, b.W), Height = Math.Max(0, b.H), Fill = Brush(brush), Tag = b };

    private void AddBracket(Canvas canvas, Box b, bool left)
    {
        var brush = Brush("BcLoopEdgeBrush");
        Add(canvas, new Rectangle { Width = b.W, Height = b.H, Fill = brush }, b.X, b.Y);
        double footX = left ? b.X : b.X + b.W - 8;
        Add(canvas, new Rectangle { Width = 8, Height = 3, Fill = brush }, footX, b.Y);
        Add(canvas, new Rectangle { Width = 8, Height = 3, Fill = brush }, footX, b.Y + b.H - 3);
    }

    private static void Add(Canvas canvas, Rectangle r)
    {
        if (r.Tag is Box b) Add(canvas, r, b.X, b.Y);
    }

    private static void Add(Canvas canvas, FrameworkElement e, double x, double y)
    {
        AutomationProperties.SetAccessibilityView(e, AccessibilityView.Raw); // the score peer speaks for the notation
        Canvas.SetLeft(e, x);
        Canvas.SetTop(e, y);
        canvas.Children.Add(e);
    }

    /// <summary>Shows the keyboard focus on a note or bar and scrolls it into view above the player bar.</summary>
    public void SetFocusRect(Rect? rect, IReadOnlyList<ScoreEventItem> currentEvents)
    {
        if (!ReferenceEquals(CurrentEvents, currentEvents)) EventsVersion++;
        CurrentEvents = currentEvents;
        FocusRect = rect;
        if (rect is { } r)
        {
            const double gap = 2;
            _focusBox.Width = r.Width + 2 * gap + 4;
            _focusBox.Height = r.Height + 2 * gap + 4;
            Canvas.SetLeft(_focusBox, r.X - gap - 2);
            Canvas.SetTop(_focusBox, r.Y - gap - 2);
            _focusBox.Visibility = Visibility.Visible;
            EnsureVisible(r);
        }
        else _focusBox.Visibility = Visibility.Collapsed;
        _peer?.RaiseChildrenChanged();
    }

    private void EnsureVisible(Rect r)
    {
        double viewTop = _scroller.VerticalOffset, viewLeft = _scroller.HorizontalOffset;
        double viewH = Math.Max(0, _scroller.ViewportHeight - BottomObscuredHeight), viewW = _scroller.ViewportWidth;
        double? y = r.Top < viewTop ? r.Top - 24 : r.Bottom > viewTop + viewH ? r.Bottom - viewH + 24 : null;
        double? x = r.Left < viewLeft ? r.Left - 24 : r.Right > viewLeft + viewW ? r.Right - viewW + 24 : null;
        if (x is not null || y is not null)
            _scroller.ChangeView(x ?? viewLeft, y ?? viewTop, null, disableAnimation: ReduceMotion);
    }

    public double ZoomFactor { get; set; } = 1.0;

    protected override AutomationPeer OnCreateAutomationPeer() => _peer = new ScoreViewAutomationPeer(this);

    protected override void OnKeyDown(KeyRoutedEventArgs e)
    {
        if (_viewModel is null)
        {
            base.OnKeyDown(e);
            return;
        }
        if (e.Key == VirtualKey.Tab)
        {
            base.OnKeyDown(e); // Tab always leaves the score (WCAG 2.1.2)
            return;
        }
        var mods = Modifiers();
        var key = Map(e.Key);
        if (key is null)
        {
            base.OnKeyDown(e);
            return;
        }
        var command = ScoreKeyMap.Map(key.Value, mods, _viewModel.SingleKeyShortcuts);
        if (command is null)
        {
            base.OnKeyDown(e);
            return;
        }
        switch (command)
        {
            case ScoreCommand.LeaveScore:
                LeaveRequested?.Invoke(this, EventArgs.Empty);
                break;
            case ScoreCommand.GoToBar:
                GoToBarRequested?.Invoke(this, EventArgs.Empty);
                break;
            default:
                _viewModel.Execute(command.Value);
                break;
        }
        e.Handled = true;
    }

    private void OnCursorMoved(object? sender, string text)
    {
        _peer?.RaiseCursorMoved(text);
    }

    private static KeyModifiers Modifiers()
    {
        static bool Down(VirtualKey k) => InputKeyboardSource.GetKeyStateForCurrentThread(k).HasFlag(CoreVirtualKeyStates.Down);
        var m = KeyModifiers.None;
        if (Down(VirtualKey.Control)) m |= KeyModifiers.Ctrl;
        if (Down(VirtualKey.Shift)) m |= KeyModifiers.Shift;
        if (Down(VirtualKey.Menu)) m |= KeyModifiers.Alt;
        return m;
    }

    private static ScoreKey? Map(VirtualKey key) => key switch
    {
        VirtualKey.Left => ScoreKey.Left,
        VirtualKey.Right => ScoreKey.Right,
        VirtualKey.Up => ScoreKey.Up,
        VirtualKey.Down => ScoreKey.Down,
        VirtualKey.Home => ScoreKey.Home,
        VirtualKey.End => ScoreKey.End,
        VirtualKey.Space => ScoreKey.Space,
        VirtualKey.Escape => ScoreKey.Escape,
        VirtualKey.U => ScoreKey.U,
        VirtualKey.C => ScoreKey.C,
        VirtualKey.R => ScoreKey.R,
        VirtualKey.P => ScoreKey.P,
        VirtualKey.W => ScoreKey.W,
        VirtualKey.L => ScoreKey.L,
        VirtualKey.M => ScoreKey.M,
        VirtualKey.S => ScoreKey.S,
        VirtualKey.K => ScoreKey.K,
        VirtualKey.T => ScoreKey.T,
        VirtualKey.G => ScoreKey.G,
        VirtualKey.O => ScoreKey.O,
        VirtualKey.Number0 or VirtualKey.NumberPad0 => ScoreKey.D0,
        VirtualKey.Subtract => ScoreKey.Minus,
        VirtualKey.Add => ScoreKey.Plus,
        (VirtualKey)189 => ScoreKey.Minus,        // VK_OEM_MINUS
        (VirtualKey)187 => ScoreKey.Plus,         // VK_OEM_PLUS (the = key)
        (VirtualKey)219 => ScoreKey.OpenBracket,  // VK_OEM_4
        (VirtualKey)221 => ScoreKey.CloseBracket, // VK_OEM_6
        _ => null,
    };

    private void ApplyBrushes()
    {
        _focusBox.Stroke = Brush("BcFocusBrush");
    }

    private Brush Brush(string key) =>
        Resources.TryGetValue(key, out var local) && local is Brush b ? b
        : Application.Current.Resources.TryGetValue(key, out var app) && app is Brush a ? a
        : new SolidColorBrush(Colors.Black);

    private static readonly Windows.UI.ViewManagement.AccessibilitySettings Accessibility = new();

    /// <summary>A Windows contrast theme is on: overlays are outlines only.</summary>
    public static bool IsHighContrast() => Accessibility.HighContrast;
}
