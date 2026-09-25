using Brasscribe.Play.Core.Scores;
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

/// <summary>An uncertain notehead: drawn with a ring beside it (open ring = uncertain, filled = very uncertain).</summary>
public sealed record NoteMark(Rect NoteHead, Certainty Level);

/// <summary>An event of the current bar, exposed to UI Automation as a list item.</summary>
public sealed record ScoreEventItem(string Name, Rect Bounds, bool IsCurrent);

/// <summary>
/// The notation view. It shows alphaTab's rendered pages and draws the overlays the tokens specify:
/// playback cursor (3 px line plus bar tint), the focused note (2 px outline with a 2 px gap), loop
/// band with edge markers, ad lib band, and rings beside uncertain noteheads so uncertainty never
/// relies on colour alone. It is one keyboard focus stop; inside it the score keys of
/// <see cref="ScoreKeyMap"/> move a talking-score cursor, whose announcement is exposed through the
/// automation peer's Value and Text patterns. Tab and Shift+Tab leave the score.
/// </summary>
public sealed partial class ScoreView : UserControl
{
    private readonly ScrollViewer _scroller;
    private readonly Grid _surface;
    private readonly Canvas _pages;
    private readonly Canvas _overlay;
    private readonly Rectangle _cursorLine;
    private readonly Rectangle _cursorBar;
    private readonly Rectangle _focusBox;
    private ScoreViewModel? _viewModel;
    private ScoreViewAutomationPeer? _peer;

    public ScoreView()
    {
        IsTabStop = true;
        UseSystemFocusVisuals = true;
        TabFocusNavigation = KeyboardNavigationMode.Once;
        _pages = new Canvas();
        _overlay = new Canvas { IsHitTestVisible = false };
        _surface = new Grid { Children = { _pages, _overlay } };
        _scroller = new ScrollViewer
        {
            Content = _surface,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            ZoomMode = ZoomMode.Disabled,
            IsTabStop = false,
        };
        Content = _scroller;

        _cursorBar = new Rectangle { Opacity = 0.2, Visibility = Visibility.Collapsed };
        _cursorLine = new Rectangle { Width = 3, Visibility = Visibility.Collapsed };
        _focusBox = new Rectangle { StrokeThickness = 2, Fill = null, Visibility = Visibility.Collapsed, RadiusX = 2, RadiusY = 2 };
        _overlay.Children.Add(_cursorBar);
        _overlay.Children.Add(_cursorLine);
        _overlay.Children.Add(_focusBox);

        ActualThemeChanged += (_, _) => ApplyBrushes();
        Loaded += (_, _) => ApplyBrushes();
        GotFocus += (_, _) => _peer?.RaiseFocusedTextChanged();
    }

    /// <summary>Localised control type spoken by screen readers ("score", "partitur").</summary>
    public string LocalizedControlType { get; set; } = "score";

    /// <summary>No smooth scrolling when the user reduces motion (WCAG 2.2.2, 2.3.3).</summary>
    public bool ReduceMotion { get; set; }

    /// <summary>Pixels kept free at the bottom so the player bar never covers the focused note (WCAG 2.4.11).</summary>
    public double BottomObscuredHeight { get; set; } = 96;

    /// <summary>Converts a rectangle in this control's coordinates to screen pixels, for automation bounds.</summary>
    public Func<Rect, Rect>? ToScreen { get; set; }

    public IReadOnlyList<ScoreEventItem> CurrentEvents { get; private set; } = [];

    public event EventHandler? LeaveRequested;
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

    private readonly List<UIElement> _marks = [];

    public void SetNoteMarks(IEnumerable<NoteMark> marks)
    {
        foreach (var m in _marks) _overlay.Children.Remove(m);
        _marks.Clear();
        foreach (var m in marks)
        {
            double d = Math.Max(6, m.NoteHead.Height * 0.6);
            var ring = new Ellipse
            {
                Width = d,
                Height = d,
                StrokeThickness = 1.5,
                Stroke = Brush(m.Level == Certainty.VeryUncertain ? "BcVeryUncertainBrush" : "BcUncertainBrush"),
                Fill = m.Level == Certainty.VeryUncertain ? Brush("BcVeryUncertainBrush") : null,
            };
            Canvas.SetLeft(ring, m.NoteHead.Right + 2);
            Canvas.SetTop(ring, m.NoteHead.Y + (m.NoteHead.Height - d) / 2);
            _overlay.Children.Insert(0, ring);
            _marks.Add(ring);
        }
    }

    private readonly List<UIElement> _bands = [];

    /// <summary>Loop and ad lib bands. In contrast themes the tints are replaced by outlines.</summary>
    public void SetBands(IEnumerable<Rect> loop, IEnumerable<Rect> adLib)
    {
        foreach (var b in _bands) _overlay.Children.Remove(b);
        _bands.Clear();
        bool contrast = IsHighContrast();
        foreach (var r in adLib) AddBand(r, contrast ? null : Brush("BcAdLibTintBrush"), contrast ? Brush("BcInkBrush") : null, dashed: true);
        foreach (var r in loop)
        {
            AddBand(r, contrast ? null : Brush("BcLoopTintBrush"), Brush("BcLoopEdgeBrush"), dashed: false);
            AddEdge(r.Left, r.Top, r.Height);
            AddEdge(r.Right - 4, r.Top, r.Height);
        }
    }

    private void AddBand(Rect r, Brush? fill, Brush? stroke, bool dashed)
    {
        var rect = new Rectangle { Width = r.Width, Height = r.Height, Fill = fill, Stroke = stroke, StrokeThickness = stroke is null ? 0 : 1 };
        if (dashed) rect.StrokeDashArray = [4, 3];
        Canvas.SetLeft(rect, r.X);
        Canvas.SetTop(rect, r.Y);
        _overlay.Children.Insert(0, rect);
        _bands.Add(rect);
    }

    private void AddEdge(double x, double y, double h)
    {
        var edge = new Rectangle { Width = 4, Height = h, Fill = Brush("BcLoopEdgeBrush") };
        Canvas.SetLeft(edge, x);
        Canvas.SetTop(edge, y);
        _overlay.Children.Insert(0, edge);
        _bands.Add(edge);
    }

    /// <summary>Moves the playback cursor; in reduced motion the caller moves it per beat, never animated.</summary>
    public void SetCursor(Rect? beat, Rect? bar)
    {
        if (beat is { } b)
        {
            _cursorLine.Height = b.Height;
            Canvas.SetLeft(_cursorLine, b.X);
            Canvas.SetTop(_cursorLine, b.Y);
            _cursorLine.Visibility = Visibility.Visible;
        }
        else _cursorLine.Visibility = Visibility.Collapsed;

        if (bar is { } r)
        {
            _cursorBar.Width = r.Width;
            _cursorBar.Height = r.Height;
            Canvas.SetLeft(_cursorBar, r.X);
            Canvas.SetTop(_cursorBar, r.Y);
            _cursorBar.Visibility = IsHighContrast() ? Visibility.Collapsed : Visibility.Visible;
        }
        else _cursorBar.Visibility = Visibility.Collapsed;
    }

    /// <summary>Shows the keyboard focus on a note or bar and scrolls it into view above the player bar.</summary>
    public void SetFocusRect(Rect? rect, IReadOnlyList<ScoreEventItem> currentEvents)
    {
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
        _cursorLine.Fill = Brush("BcCursorBrush");
        _cursorBar.Fill = Brush("BcCursorBrush");
        _focusBox.Stroke = Brush("BcFocusBrush");
    }

    private Brush Brush(string key) =>
        Resources.TryGetValue(key, out var local) && local is Brush b ? b
        : Application.Current.Resources.TryGetValue(key, out var app) && app is Brush a ? a
        : new SolidColorBrush(Colors.Black);

    private static readonly Windows.UI.ViewManagement.AccessibilitySettings Accessibility = new();

    private static bool IsHighContrast() => Accessibility.HighContrast;
}
