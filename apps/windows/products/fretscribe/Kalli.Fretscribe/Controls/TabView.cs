using System.ComponentModel;
using System.Runtime.InteropServices.WindowsRuntime;
using AlphaTab;
using AlphaTab.Model;
using AlphaTab.Rendering;
using AlphaTab.Rendering.Utils;
using Kalli.Scribe.Playback;
using Kalli.Scribe.Review;
using Kalli.Scribe.Tab;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Shapes;
using Windows.Storage.Streams;

namespace Kalli.Fretscribe.Controls;

/// <summary>
/// The tab page: alphaTab's engraving of the tab's MusicXML, with the marks drawn over it from the tab's data (a "?"
/// above a note Fretscribe is not sure of, a boxed "!" above one with no place) and the cursor at the beat the
/// recording is at. Each mark is a button: it says which note it is, and plays its bar slowly. The page follows the
/// cursor while the song plays. Code only, so it is type-checked without the XAML compiler.
/// </summary>
public sealed partial class TabView : UserControl
{
    /// <summary>The one renderer of the app: alphaTab is not safe to call from two threads.</summary>
    private static readonly LazyScoreRenderer Renderer = new("skia");

    private readonly ScrollViewer _scroll = new() { HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, IsTabStop = false };
    private readonly Canvas _pages = new();
    private readonly Canvas _marks = new();
    private readonly Rectangle _cursor = new() { Width = 3, Visibility = Visibility.Collapsed, IsHitTestVisible = false };
    private readonly Grid _surface = new() { HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top };
    private TabPageViewModel? _vm;
    private ScoreLayout? _layout;
    private readonly Dictionary<string, Image> _images = [];
    private int _rendering;
    private double _laidOutWidth;
    private bool _following;

    public TabView()
    {
        _surface.Children.Add(_pages);
        _surface.Children.Add(_marks);
        _marks.Children.Add(_cursor);
        _scroll.Content = _surface;
        Content = _scroll;
        AutomationProperties.SetLandmarkType(this, Microsoft.UI.Xaml.Automation.Peers.AutomationLandmarkType.Main);
        SizeChanged += (_, e) => { if (Math.Abs(e.NewSize.Width - _laidOutWidth) > 24) _ = RenderAsync(); };
        ActualThemeChanged += (_, _) => _ = RenderAsync();
        Unloaded += (_, _) => Follow(false);
    }

    /// <summary>The page is laid out at the view's width and every page of it is drawn (the screen catalogue waits for it).</summary>
    public bool IsLaidOut => _vm?.Sheet is not null && _layout is not null && _images.Count > 0 && _images.Values.All(i => i.Source is not null);

    /// <summary>The marks as buttons, in the order of the page, for the screen to move focus to (Next ?).</summary>
    public IReadOnlyList<Button> MarkButtons => [.. _marks.Children.OfType<Button>()];

    public TabPageViewModel? ViewModel
    {
        get => _vm;
        set
        {
            if (_vm is not null)
            {
                _vm.PropertyChanged -= OnViewModelChanged;
                _vm.Practice.PropertyChanged -= OnPracticeChanged;
            }
            _vm = value;
            if (_vm is not null)
            {
                _vm.PropertyChanged += OnViewModelChanged;
                _vm.Practice.PropertyChanged += OnPracticeChanged;
            }
            _ = RenderAsync();
        }
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(TabPageViewModel.Sheet) or nameof(TabPageViewModel.Zoom)) _ = RenderAsync();
    }

    private void OnPracticeChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(PracticeModel.Playing)) Follow(_vm?.Practice.Playing == true);
        if (e.PropertyName is nameof(PracticeModel.Jumps) or nameof(PracticeModel.At)) PlaceCursor(scroll: true);
    }

    /// <summary>The cursor moves with the recording on every frame while it plays.</summary>
    private void Follow(bool on)
    {
        if (on == _following) return;
        _following = on;
        if (on) CompositionTarget.Rendering += OnFrame;
        else CompositionTarget.Rendering -= OnFrame;
    }

    private void OnFrame(object? sender, object e)
    {
        _vm?.Tick();
        PlaceCursor(scroll: true);
    }

    /// <summary>The tab's colours: its ink and lines from the app's theme.</summary>
    private UncertaintyPalette Palette()
    {
        bool dark = ActualTheme == ElementTheme.Dark;
        var basis = dark ? UncertaintyPalette.Dark : UncertaintyPalette.Light;
        Rgb? Color(string key) => Theme.Color(key, dark) is { } c ? new Rgb(c.R, c.G, c.B) : null;
        return basis with
        {
            Background = Color("ScribeBgColor") ?? basis.Background,
            Ink = Color("ScribeInkColor") ?? basis.Ink,
            Staff = Color("ScribeLineColor") ?? basis.Staff,
            TextMuted = Color("ScribeTextMutedColor") ?? basis.TextMuted,
        };
    }

    /// <summary>Lays the page out at the view's width and zoom, then draws its pages and the marks over them.</summary>
    private async Task RenderAsync()
    {
        if (_vm?.Sheet is not { } sheet || ActualWidth <= 0) return;
        int run = ++_rendering;
        double width = Math.Max(320, ActualWidth - 24);
        double pixelScale = XamlRoot?.RasterizationScale ?? 1.0;
        var palette = Palette();
        Score score;
        ScoreLayout layout;
        try
        {
            score = await Renderer.ParseAsync(System.Text.Encoding.UTF8.GetBytes(Kalli.Scribe.Tab.TabIndex.ForRenderer(sheet.MusicXml, sheet.Index.Header)));
            layout = await Renderer.LayoutAsync(score, [0], width, _vm.Zoom / 100.0, LayoutMode.Page, theme: palette, pixelScale: pixelScale,
                configure: s =>
                {
                    // Rhythm on the tab staff itself, as stems with the bar's beams; the screen's header says the tuning and tempo.
                    s.Notation.RhythmMode = TabRhythmMode.ShowWithBars;
                    foreach (var element in new[] { NotationElement.TrackNames, NotationElement.GuitarTuning, NotationElement.EffectTempo })
                        s.Notation.Elements.Set(element, false);
                });
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            System.Diagnostics.Trace.TraceWarning($"the tab could not be drawn: {e.Message}");
            _vm.Failed();
            return;
        }
        if (run != _rendering || layout.Generation != Renderer.Generation) return;
        _layout = layout;
        _laidOutWidth = ActualWidth;
        _pages.Children.Clear();
        _images.Clear();
        // alphaTab signs every engraving with "rendered by alphaTab" under the last line: the page ends with the music
        // (alphaTab is credited in About).
        double height = layout.Bounds?.StaffSystems.LastOrDefault()?.VisualBounds is { } last ? Math.Min(layout.Height, last.Y + last.H + 16) : layout.Height;
        _surface.Width = layout.Width;
        _surface.Height = height;
        _pages.Width = _marks.Width = layout.Width;
        _pages.Height = _marks.Height = height;
        _pages.Clip = new RectangleGeometry { Rect = new Windows.Foundation.Rect(0, 0, layout.Width, height) };
        foreach (var page in layout.Pages)
        {
            var image = new Image { Width = page.Width, Height = page.Height, Stretch = Stretch.Fill };
            AutomationProperties.SetAccessibilityView(image, Microsoft.UI.Xaml.Automation.Peers.AccessibilityView.Raw);
            Canvas.SetLeft(image, page.X);
            Canvas.SetTop(image, page.Y);
            _pages.Children.Add(image);
            _images[page.Id] = image;
        }
        DrawMarks(sheet, layout);
        PlaceCursor(scroll: false);
        foreach (var page in layout.Pages) await LoadPageAsync(layout.Generation, page.Id);
    }

    private async Task LoadPageAsync(int generation, string id)
    {
        byte[]? png;
        try { png = await Renderer.RenderPageAsync(generation, id); }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            System.Diagnostics.Trace.TraceWarning($"tab page {id} failed: {e.Message}");
            return;
        }
        if (png is null || generation != Renderer.Generation || !_images.TryGetValue(id, out var image)) return;
        var bitmap = new BitmapImage();
        using var stream = new InMemoryRandomAccessStream();
        await stream.WriteAsync(png.AsBuffer());
        stream.Seek(0);
        await bitmap.SetSourceAsync(stream);
        if (generation == Renderer.Generation) image.Source = bitmap;
    }

    /// <summary>The beats of one bar of the mark staff, by their start in the bar.</summary>
    private static IEnumerable<BeatBounds> Beats(ScoreLayout layout, int bar, int staff) =>
        layout.Bounds?.StaffSystems.SelectMany(s => s.Bars).Where(m => (int)m.Index == bar)
            .SelectMany(m => m.Bars).Where(b => (int)b.Bar.Staff.Index == staff).SelectMany(b => b.Beats) ?? [];

    /// <summary>A "?" or boxed "!" above each marked column, as a button that says which note it is.</summary>
    private void DrawMarks(TabSheet sheet, ScoreLayout layout)
    {
        foreach (var old in _marks.Children.OfType<Button>().ToList()) _marks.Children.Remove(old);
        var items = _vm?.Marks;
        for (int i = 0; i < sheet.Marks.Columns.Count; i++)
        {
            var column = sheet.Marks.Columns[i];
            var beat = Beats(layout, column.Bar, column.Staff).FirstOrDefault(b => (int)b.Beat.PlaybackStart == column.Onset);
            if (beat?.VisualBounds is not { } bounds) continue;
            bool noPlace = column.Kind == MarkKind.NoPlace;
            var text = new TextBlock
            {
                Text = noPlace ? "!" : "?",
                FontWeight = Microsoft.UI.Text.FontWeights.Bold,
                FontSize = 15,
                Foreground = Brush(noPlace ? "ScribeInkBrush" : "ScribeUncertainBrush"),
                HorizontalAlignment = HorizontalAlignment.Center,
            };
            var mark = new Button
            {
                Content = noPlace ? new Border { BorderThickness = new Thickness(1.5), BorderBrush = Brush("ScribeInkBrush"), Padding = new Thickness(4, 0, 4, 0), Child = text } : text,
                Padding = new Thickness(4, 0, 4, 0),
                MinWidth = 24,
                MinHeight = 24,
                Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
                BorderThickness = new Thickness(0),
                Tag = column.Bar,
            };
            if (items is not null && i < items.Count) AutomationProperties.SetName(mark, items[i].Label);
            mark.Click += (_, _) => _vm?.PlayBarSlowly(column.Bar);
            Canvas.SetLeft(mark, bounds.X + bounds.W / 2 - 12);
            Canvas.SetTop(mark, Math.Max(0, bounds.Y - 30));
            _marks.Children.Add(mark);
        }
    }

    /// <summary>The cursor at the beat the recording is at; the page scrolls to keep its line in view.</summary>
    private void PlaceCursor(bool scroll)
    {
        if (_vm?.Clock is not { } clock || _layout is not { } layout || _vm.Sheet is not { } sheet) { _cursor.Visibility = Visibility.Collapsed; return; }
        var place = clock.PlaceAt(_vm.Practice.Now());
        var beats = Beats(layout, place.Bar, sheet.Index.MarkStaff).OrderBy(b => b.Beat.PlaybackStart).ToList();
        var beat = beats.LastOrDefault(b => b.Beat.PlaybackStart <= place.Tick) ?? beats.FirstOrDefault();
        if (beat?.VisualBounds is not { } bounds)
        {
            _cursor.Visibility = Visibility.Collapsed;
            return;
        }
        var line = layout.Bounds?.StaffSystems.FirstOrDefault(s => s.Bars.Any(m => (int)m.Index == place.Bar))?.VisualBounds ?? bounds;
        _cursor.Fill = Brush("FsCursorBrush");
        _cursor.Height = line.H;
        Canvas.SetLeft(_cursor, beat.OnNotesX > 0 ? beat.OnNotesX - 1.5 : bounds.X);
        Canvas.SetTop(_cursor, line.Y);
        _cursor.Visibility = Visibility.Visible;
        if (!scroll) return;
        // Two lines' room: the line being played stays in the upper part of the view.
        double top = _scroll.VerticalOffset, bottom = top + _scroll.ViewportHeight;
        if (line.Y < top || line.Y + line.H > bottom - line.H)
            _scroll.ChangeView(null, Math.Max(0, line.Y - 24), null, disableAnimation: true);
    }

    private Brush Brush(string key) => Theme.Brush(key, this);
}

/// <summary>The app's theme resources for the element's own theme (Light, Dark or a contrast theme).</summary>
internal static class Theme
{
    public static Windows.UI.Color? Color(string key, bool dark)
    {
        foreach (var d in Application.Current.Resources.MergedDictionaries.Reverse())
            if (d.ThemeDictionaries.TryGetValue(dark ? "Dark" : "Light", out var t) && t is ResourceDictionary themed && themed.TryGetValue(key, out var v) && v is Windows.UI.Color c)
                return c;
        return null;
    }

    public static Brush Brush(string key, FrameworkElement element) =>
        Kalli.Scribe.Controls.ThemedResources.Brush(element, key);
}
