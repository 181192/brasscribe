using System.Collections.ObjectModel;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Kalli.Scribe.ViewModels;

/// <summary>One page of printed music in hand: its file, and its place as the list says it.</summary>
public sealed partial class PageItem(string path, int pages = 1) : ObservableObject
{
    public string Path { get; } = path;
    /// <summary>How many pages it holds: a PDF's every page counts against the 40, as the computer counts them.</summary>
    public int PageCount { get; } = pages;
    public string Name { get; } = System.IO.Path.GetFileName(path);
    public bool IsPdf => System.IO.Path.GetExtension(Path).Equals(".pdf", StringComparison.OrdinalIgnoreCase);
    /// <summary>A picture (not a PDF): its row shows a small version of it, so pages are told apart by sight.</summary>
    public bool IsPicture => !IsPdf;
    /// <summary>The file, for the row's small picture.</summary>
    public Uri FileUri => new(Path);

    /// <summary>"Page 2".</summary>
    [ObservableProperty] public partial string Place { get; set; } = "";
    /// <summary>Its name, with its page count for a PDF of more than one: "Hymns.pdf · 12 pages".</summary>
    [ObservableProperty] public partial string Detail { get; set; } = "";
    [ObservableProperty] public partial bool IsFirst { get; set; }
    [ObservableProperty] public partial bool IsLast { get; set; }
    [ObservableProperty] public partial string MoveUpName { get; set; } = "";
    [ObservableProperty] public partial string MoveDownName { get; set; } = "";
    [ObservableProperty] public partial string RemoveName { get; set; } = "";
}

/// <summary>
/// Sheet music from a picture: the pages in the order they are read (pictures or PDFs), each moved or removed, and
/// Read the notes, which needs the computer. A file the engine would not read (another kind of picture, over 50 MB),
/// and pages past 40, are left out here and said.
/// </summary>
public sealed partial class PagesViewModel : ObservableObject
{
    private readonly IFileDialogs _dialogs;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly Func<string, int?> _pdfPages;

    /// <summary>The pages in hand, with the file dialog that adds them and the words they are said in.</summary>
    /// <param name="dialogs">Where pages are chosen.</param>
    /// <param name="announcer">What is said to a screen reader.</param>
    /// <param name="strings">The app's words.</param>
    /// <param name="pdfPages">How many pages a PDF has, or null when it cannot be opened (locked with a password): the
    /// system's PDF reader on Windows; by default what the PDF's text says (<see cref="Engine.Pages.PdfPagesInText"/>).</param>
    public PagesViewModel(IFileDialogs dialogs, IAnnouncer announcer, IStrings strings, Func<string, int?>? pdfPages = null)
    {
        _pdfPages = pdfPages ?? Engine.Pages.PdfPagesInText;
        _dialogs = dialogs;
        _announcer = announcer;
        _s = strings;
        Pages.CollectionChanged += (_, _) =>
        {
            Renumber();
            OnPropertyChanged(nameof(PageCount));
            OnPropertyChanged(nameof(HasPages));
            OnPropertyChanged(nameof(ShowsOrderHint));
            ReadCommand.NotifyCanExecuteChanged();
        };
    }

    public ObservableCollection<PageItem> Pages { get; } = [];

    public bool HasPages => Pages.Count > 0;

    /// <summary>The pages in hand, every page of a PDF counted: at most <see cref="Engine.Pages.MaxPages"/>.</summary>
    public int PageCount => Pages.Sum(p => p.PageCount);

    /// <summary>"The pages are read in this order…" once there is an order to change.</summary>
    public bool ShowsOrderHint => Pages.Count > 1;

    /// <summary>Whether the computer is there to read them (the connection's state); Read the notes waits for it.</summary>
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ReadCommand))]
    public partial bool ComputerThere { get; set; }

    /// <summary>What happened to the last pages added, moved or removed.</summary>
    [ObservableProperty] public partial string? StatusText { get; set; }

    /// <summary>Raised by Read the notes, with the pages in order.</summary>
    public event EventHandler<IReadOnlyList<string>>? ReadRequested;

    [RelayCommand]
    private async Task AddAsync() => Add(await _dialogs.PickOpenManyAsync(Engine.Pages.Extensions));

    /// <summary>Files chosen, dropped or opened, in their order.</summary>
    public void Add(IReadOnlyList<string> paths)
    {
        int notPages = 0, tooLarge = 0, locked = 0, over = 0;
        foreach (var path in paths)
        {
            if (PageCount >= Engine.Pages.MaxPages) { over++; continue; }
            switch (Engine.Pages.Check(path))
            {
                case PageRefusal.NotAPage: notPages++; break;
                case PageRefusal.TooLarge: tooLarge++; break;
                default:
                    // Every page of a PDF counts, as the computer counts them; one that cannot be opened is left out.
                    int? count = Path.GetExtension(path).Equals(".pdf", StringComparison.OrdinalIgnoreCase) || Engine.Pages.FormatOf(Head(path)) == "pdf"
                        ? _pdfPages(path) : 1;
                    if (count is not { } n) locked++;
                    else if (PageCount + n > Engine.Pages.MaxPages) over++;
                    else Pages.Add(new PageItem(path, n));
                    break;
            }
        }
        var said = new List<string>();
        if (notPages == 1) said.Add(_s["Pages_LeftOut_One"]);
        if (notPages > 1) said.Add(_s.Format("Pages_LeftOut_Many", notPages));
        if (tooLarge > 0) said.Add(_s["Error_Pages_PageTooLarge"]);
        if (locked > 0) said.Add(_s["Pages_PdfLocked"]);
        if (over > 0) said.Add(_s.Format("Pages_TooMany", Engine.Pages.MaxPages));
        StatusText = said.Count > 0 ? string.Join(" ", said) : null;
        if (StatusText is { } text) _announcer.Announce(text, AnnouncementKind.Important);
    }

    private static byte[] Head(string path)
    {
        try
        {
            using var file = File.OpenRead(path);
            var head = new byte[12];
            return head[..file.ReadAtLeast(head, head.Length, throwOnEndOfStream: false)];
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return []; }
    }

    [RelayCommand]
    private void MoveUp(PageItem page) => Move(page, -1);

    [RelayCommand]
    private void MoveDown(PageItem page) => Move(page, 1);

    private void Move(PageItem page, int by)
    {
        int i = Pages.IndexOf(page), j = i + by;
        if (i < 0 || j < 0 || j >= Pages.Count) return;
        Pages.Move(i, j);
        Say(_s.Format("Pages_Moved", i + 1, j + 1));
    }

    [RelayCommand]
    private void Remove(PageItem page)
    {
        int i = Pages.IndexOf(page);
        if (i < 0) return;
        Pages.RemoveAt(i);
        Say(_s.Format("Pages_Removed", i + 1));
    }

    /// <summary>The pages were read into a score: they are let go.</summary>
    public void Clear()
    {
        Pages.Clear();
        StatusText = null;
    }

    [RelayCommand(CanExecute = nameof(CanRead))]
    private void Read() => ReadRequested?.Invoke(this, Pages.Select(p => p.Path).ToList());

    private bool CanRead() => Pages.Count > 0 && ComputerThere;

    private void Say(string text)
    {
        StatusText = text;
        _announcer.Announce(text, AnnouncementKind.Important);
    }

    private void Renumber()
    {
        for (int i = 0; i < Pages.Count; i++)
        {
            var p = Pages[i];
            p.Place = _s.Format("Pages_Page", i + 1);
            p.Detail = p.PageCount > 1 ? _s.Format("Pages_NameWithCount", p.Name, p.PageCount) : p.Name;
            p.IsFirst = i == 0;
            p.IsLast = i == Pages.Count - 1;
            p.MoveUpName = _s.Format("Pages_MoveUp", i + 1);
            p.MoveDownName = _s.Format("Pages_MoveDown", i + 1);
            p.RemoveName = _s.Format("Pages_Remove", i + 1);
        }
    }
}
