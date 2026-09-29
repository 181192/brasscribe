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
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml.Hosting;
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
    private readonly Canvas _selectUnder;
    private ScoreViewModel? _viewModel;
    private ScoreViewAutomationPeer? _peer;
    private readonly Grid _frame;
    private readonly Border _mirrorHost;

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
        _selectUnder = new Canvas { IsHitTestVisible = false };
        _surface = new Grid { Children = { _underlay, _cursorUnder, _selectUnder, _pages, _overlay, _cursorOver, _marks } };
        _scroller = new ScrollViewer
        {
            Content = _surface,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            ZoomMode = ZoomMode.Disabled,
            IsTabStop = false,
        };
        // The music stand's right-hand page is a live copy of the surface (see ShowStandWindow).
        _mirrorHost = new Border { IsHitTestVisible = false, Visibility = Visibility.Collapsed };
        AutomationProperties.SetAccessibilityView(_mirrorHost, AccessibilityView.Raw);
        _frame = new Grid
        {
            ColumnDefinitions = { new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) }, new ColumnDefinition { Width = new GridLength(0) } },
            Children = { _scroller, _mirrorHost },
        };
        Grid.SetColumn(_mirrorHost, 1);
        Content = _frame;
        _frame.ManipulationStarted += (_, e) => _swipeStart = e.Position.X;
        _frame.ManipulationCompleted += OnSurfaceManipulationCompleted;
        // In the stand a tap anywhere on the music (either page, or the gutter) only shows or hides the
        // controls: it never moves the cursor or checks a note.
        _frame.Tapped += (_, e) =>
        {
            if (!IsStand) return;
            e.Handled = true;
            StandTapped?.Invoke(this, EventArgs.Empty);
        };
        AddHandler(PointerWheelChangedEvent, new PointerEventHandler(OnStandWheel), handledEventsToo: true);

        _scroller.ViewChanged += (_, _) => ViewportChanged?.Invoke(this, Viewport);
        _scroller.SizeChanged += (_, _) => ViewportChanged?.Invoke(this, Viewport);
        ActualThemeChanged += (_, _) =>
        {
            ApplyBrushes();
            SetOverlay(_items);
            SetCursor(_cursor);
            SetFocusRect(FocusRect, CurrentEvents, _lastStaff);
        };
        Loaded += (_, _) => ApplyBrushes();
        GotFocus += (_, _) => _peer?.RaiseFocusedTextChanged();
        // The "?" marks can be tapped (a 44 epx target around each) to check that note.
        _surface.Tapped += (_, e) =>
        {
            if (IsStand) return; // the frame handles it
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

    private void Draw(IReadOnlyList<OverlayItem> items, Canvas under, Canvas over, bool clearOver = true)
    {
        under.Children.Clear();
        if (clearOver) over.Children.Clear();
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
                case OverlayKind.GroupBracket:
                    Add(over, new Line { X1 = 0, Y1 = 0, X2 = b.W, Y2 = 0, Stroke = Brush("BcStaffBrush"), StrokeThickness = 1.5, StrokeDashArray = [3, 2] }, b.X, b.Y);
                    Add(over, new Line { X1 = 0, Y1 = 0, X2 = 0, Y2 = b.H, Stroke = Brush("BcStaffBrush"), StrokeThickness = 1.5 }, b.X, b.Y);
                    Add(over, new Line { X1 = 0, Y1 = 0, X2 = 0, Y2 = b.H, Stroke = Brush("BcStaffBrush"), StrokeThickness = 1.5 }, b.X + b.W, b.Y);
                    break;
                case OverlayKind.SelectionTint: Add(under, Fill(b, "BcSelectionTintBrush")); break;
                case OverlayKind.SelectionCaret:
                    Add(over, new Polygon
                    {
                        Points = [new Point(b.W / 2, 0), new Point(b.W, b.H), new Point(0, b.H)],
                        Fill = Brush("BcSelectionEdgeBrush"),
                    }, b.X, b.Y);
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

    private IReadOnlyList<OverlayItem> _selection = [];
    private Rect? _lastStaff;

    /// <summary>
    /// Shows the note under the talking-score cursor and scrolls it into view above the player bar: a
    /// selection-tint column over the staff and a caret below it (usability review 3, P2-A). It is not
    /// a box, which would read as the boxed "?" for very uncertain notes.
    /// </summary>
    public void SetFocusRect(Rect? rect, IReadOnlyList<ScoreEventItem> currentEvents, Rect? staff = null)
    {
        if (!ReferenceEquals(CurrentEvents, currentEvents)) EventsVersion++;
        CurrentEvents = currentEvents;
        FocusRect = rect;
        _lastStaff = staff;
        _selection = rect is { } r
            ? ScoreOverlay.Selection(new Box(r.X, r.Y, r.Width, r.Height), staff is { } st ? new Box(st.X, st.Y, st.Width, st.Height) : new Box(r.X, r.Y, r.Width, r.Height))
            : [];
        _selectUnder.Children.Clear();
        foreach (var c in _marks.Children.OfType<Polygon>().ToList()) _marks.Children.Remove(c);
        Draw(_selection, _selectUnder, _marks, clearOver: false);
        if (rect is { } visible) EnsureVisible(visible);
        _peer?.RaiseChildrenChanged();
    }

    private void EnsureVisible(Rect r)
    {
        if (IsStand) return; // the stand moves by whole pages (MusicStandViewModel)
        double viewTop = _scroller.VerticalOffset, viewLeft = _scroller.HorizontalOffset;
        double viewH = Math.Max(0, _scroller.ViewportHeight - BottomObscuredHeight), viewW = _scroller.ViewportWidth;
        double? y = r.Top < viewTop ? r.Top - 24 : r.Bottom > viewTop + viewH ? r.Bottom - viewH + 24 : null;
        double? x = r.Left < viewLeft ? r.Left - 24 : r.Right > viewLeft + viewW ? r.Right - viewW + 24 : null;
        if (x is not null || y is not null)
            _scroller.ChangeView(x ?? viewLeft, y ?? viewTop, null, disableAnimation: ReduceMotion);
    }

    public double ZoomFactor { get; set; } = 1.0;

    // ---- the music stand ----

    private bool _isStand;
    private bool _spread;
    private double _swipeStart;
    private SpriteVisual? _mirror;
    private CompositionVisualSurface? _mirrorSurface;

    /// <summary>A tap on the music while in the stand (it shows or hides the controls).</summary>
    public event EventHandler? StandTapped;

    /// <summary>Tab or Shift+Tab (true) from the score in the stand: the view shows the layer and moves focus into it.</summary>
    public event EventHandler<bool>? StandTabbed;

    /// <summary>Any key in the stand (the layer shows).</summary>
    public event EventHandler? StandKey;

    /// <summary>The right-hand page could not be shown; the stand falls back to a single page.</summary>
    public event EventHandler? SpreadFailed;

    /// <summary>
    /// The music stand: no scrolling (the stand has pages), no note cursor following, taps and swipes go
    /// to the stand, and the mouse wheel turns pages.
    /// </summary>
    public bool IsStand
    {
        get => _isStand;
        set
        {
            _isStand = value;
            var mode = value ? ScrollMode.Disabled : ScrollMode.Enabled;
            _scroller.VerticalScrollMode = mode;
            _scroller.HorizontalScrollMode = mode;
            _scroller.VerticalScrollBarVisibility = value ? ScrollBarVisibility.Hidden : ScrollBarVisibility.Auto;
            _scroller.HorizontalScrollBarVisibility = value ? ScrollBarVisibility.Hidden : ScrollBarVisibility.Auto;
            _frame.ManipulationMode = value ? ManipulationModes.TranslateX | ManipulationModes.TranslateRailsX : ManipulationModes.System;
            // Hit-testable everywhere in the stand, so the right page and the gutter take taps and swipes too.
            _frame.Background = value ? new SolidColorBrush(Colors.Transparent) : null;
            _mirrorHost.Background = value ? new SolidColorBrush(Colors.Transparent) : null;
            _mirrorHost.IsHitTestVisible = value;
            if (!value) IsSpread = false;
        }
    }

    public const double StandGutter = 24;

    /// <summary>Two pages side by side: the left column scrolls, the right one mirrors the next page.</summary>
    public bool IsSpread
    {
        get => _spread;
        set
        {
            _spread = value;
            _frame.ColumnSpacing = value ? StandGutter : 0;
            _frame.ColumnDefinitions[1].Width = value ? new GridLength(1, GridUnitType.Star) : new GridLength(0);
            _mirrorHost.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
            if (!value) ClearMirror();
        }
    }

    /// <summary>The width one page of the stand is laid out at.</summary>
    public double StandColumnWidth(bool spread) => spread ? Math.Max(200, (ActualWidth - StandGutter) / 2) : Math.Max(200, ActualWidth);

    /// <summary>
    /// Shows the stand's window: the left (or only) page from <paramref name="top"/>, and in a spread the
    /// right page from <paramref name="rightTop"/>. A 200 ms fade marks the turn unless motion is reduced.
    /// </summary>
    public void ShowStandWindow(double top, double? rightTop, bool fade)
    {
        top = Math.Max(0, top);
        _scroller.ChangeView(0, top, null, disableAnimation: true);
        if (_spread && rightTop is { } right) ShowMirror(right);
        else ClearMirror();
        if (fade && !ReduceMotion) Fade();
        // Ask for the pages of both columns now; the scroll itself lands a frame later.
        var width = Math.Max(0, _scroller.ViewportWidth);
        var height = Math.Max(0, _scroller.ViewportHeight);
        ViewportChanged?.Invoke(this, new Rect(0, top, width, height));
        if (_spread && rightTop is { } r) ViewportChanged?.Invoke(this, new Rect(0, r, width, height));
    }

    private void ShowMirror(double top)
    {
        try
        {
            var compositor = ElementCompositionPreview.GetElementVisual(this).Compositor;
            var size = new System.Numerics.Vector2((float)Math.Max(1, _scroller.ViewportWidth), (float)Math.Max(1, _scroller.ViewportHeight));
            _mirrorSurface ??= compositor.CreateVisualSurface();
            _mirrorSurface.SourceVisual = ElementCompositionPreview.GetElementVisual(_surface);
            _mirrorSurface.SourceOffset = new System.Numerics.Vector2(0, (float)top);
            _mirrorSurface.SourceSize = size;
            if (_mirror is null)
            {
                var brush = compositor.CreateSurfaceBrush(_mirrorSurface);
                brush.Stretch = CompositionStretch.None;
                brush.HorizontalAlignmentRatio = 0;
                brush.VerticalAlignmentRatio = 0;
                _mirror = compositor.CreateSpriteVisual();
                _mirror.Brush = brush;
                ElementCompositionPreview.SetElementChildVisual(_mirrorHost, _mirror);
            }
            _mirror.Size = size;
        }
        catch (Exception e) when (e is InvalidOperationException or ArgumentException or System.Runtime.InteropServices.COMException)
        {
            // The copy is a convenience; without it the stand still pages, one page at a time.
            System.Diagnostics.Trace.TraceWarning($"Music stand right page unavailable: {e.Message}");
            IsSpread = false;
            SpreadFailed?.Invoke(this, EventArgs.Empty);
        }
    }

    private void ClearMirror()
    {
        if (_mirror is null) return;
        ElementCompositionPreview.SetElementChildVisual(_mirrorHost, null);
        _mirror.Dispose();
        _mirror = null;
        _mirrorSurface?.Dispose();
        _mirrorSurface = null;
    }

    private void Fade()
    {
        var visual = ElementCompositionPreview.GetElementVisual(_frame);
        var fade = visual.Compositor.CreateScalarKeyFrameAnimation();
        fade.InsertKeyFrame(0f, 0.2f);
        fade.InsertKeyFrame(1f, 1f);
        fade.Duration = TimeSpan.FromMilliseconds(200);
        visual.StartAnimation("Opacity", fade);
    }

    /// <summary>A horizontal swipe that starts at least 24 epx from the edges turns a page (the edges belong to the system).</summary>
    private void OnSurfaceManipulationCompleted(object sender, ManipulationCompletedRoutedEventArgs e)
    {
        if (!IsStand || _viewModel is null) return;
        double startX = _swipeStart;
        int direction = Brasscribe.Play.Core.Stand.StandGesture.Swipe(startX, ActualWidth, e.Cumulative.Translation.X, e.Cumulative.Translation.Y);
        if (direction == 0) return;
        e.Handled = true;
        if (direction > 0) _viewModel.Stand.NextPage();
        else _viewModel.Stand.PreviousPage();
    }

    /// <summary>The mouse wheel turns pages in the stand.</summary>
    private void OnStandWheel(object sender, PointerRoutedEventArgs e)
    {
        if (!IsStand || _viewModel is null) return;
        int delta = e.GetCurrentPoint(this).Properties.MouseWheelDelta;
        if (delta == 0) return;
        e.Handled = true;
        if (delta < 0) _viewModel.Stand.NextPage();
        else _viewModel.Stand.PreviousPage();
    }


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
            if (IsStand)
            {
                // Tab shows the stand's controls and moves into them; there is no trap (WCAG 2.1.2).
                e.Handled = true;
                StandTabbed?.Invoke(this, Modifiers().HasFlag(KeyModifiers.Shift));
                return;
            }
            base.OnKeyDown(e); // Tab always leaves the score (WCAG 2.1.2)
            return;
        }
        var mods = Modifiers();
        var key = MapKey(e.Key);
        // Space shows the stand's controls; a pedal's page keys turn the page and leave them as they are.
        if (IsStand && Brasscribe.Play.Core.Stand.StandLayer.ShowsLayer(key)) StandKey?.Invoke(this, EventArgs.Empty);
        if (key is null)
        {
            base.OnKeyDown(e);
            return;
        }
        var command = ScoreKeyMap.Map(key.Value, mods, _viewModel.SingleKeyShortcuts, IsStand);
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

    public static KeyModifiers Modifiers()
    {
        static bool Down(VirtualKey k) => InputKeyboardSource.GetKeyStateForCurrentThread(k).HasFlag(CoreVirtualKeyStates.Down);
        var m = KeyModifiers.None;
        if (Down(VirtualKey.Control)) m |= KeyModifiers.Ctrl;
        if (Down(VirtualKey.Shift)) m |= KeyModifiers.Shift;
        if (Down(VirtualKey.Menu)) m |= KeyModifiers.Alt;
        return m;
    }

    /// <summary>
    /// The score's keys from a VirtualKey. F11 is left out on purpose: it is the page's accelerator, so it
    /// works wherever focus is.
    /// </summary>
    public static ScoreKey? MapKey(VirtualKey key) => key switch
    {
        VirtualKey.F => ScoreKey.F,
        VirtualKey.PageUp => ScoreKey.PageUp,
        VirtualKey.PageDown => ScoreKey.PageDown,
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
        SetFocusRect(FocusRect, CurrentEvents, _lastStaff);
    }

    /// <summary>A Bc* brush for this control's own theme (Appearance may differ from the system's).</summary>
    private Brush Brush(string key) => ThemedResources.Brush(this, key);

    private static readonly Windows.UI.ViewManagement.AccessibilitySettings Accessibility = new();

    /// <summary>A Windows contrast theme is on: overlays are outlines only.</summary>
    public static bool IsHighContrast() => Accessibility.HighContrast;
}
