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
    private readonly Func<string, Task<PdfRead>> _readPdf;

    /// <summary>The pages in hand, with the file dialog that adds them and the words they are said in.</summary>
    /// <param name="dialogs">Where pages are chosen.</param>
    /// <param name="announcer">What is said to a screen reader.</param>
    /// <param name="strings">The app's words.</param>
    /// <param name="readPdf">The system's PDF reader (WinPdfPages): how many pages a PDF has, or that it is locked or
    /// damaged. Nothing else is trusted to count; tests put their own reader in its place.</param>
    public PagesViewModel(IFileDialogs dialogs, IAnnouncer announcer, IStrings strings, Func<string, Task<PdfRead>> readPdf)
    {
        _readPdf = readPdf;
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
    private async Task ChooseAsync() => await AddAsync(await _dialogs.PickOpenManyAsync(Engine.Pages.Extensions));

    /// <summary>
    /// Files chosen, dropped or opened, in their order. Each is looked at and, a PDF, counted off the window's thread,
    /// and joins the list as it is ready, so the window stays live with large PDFs. A file that is no page, one too
    /// large, a PDF locked or damaged, and pages past <see cref="Engine.Pages.MaxPages"/> (a PDF's every page counted)
    /// are left out and said.
    /// </summary>
    public async Task AddAsync(IReadOnlyList<string> paths)
    {
        int notPages = 0, tooLarge = 0, locked = 0, damaged = 0, over = 0;
        IsAdding = true;
        try
        {
            foreach (var path in paths)
            {
                if (PageCount >= Engine.Pages.MaxPages) { over++; continue; }
                var (refusal, pdf) = await Task.Run(() => (Engine.Pages.Check(path), Engine.Pages.FormatOf(Head(path)) == "pdf"));
                switch (refusal)
                {
                    case PageRefusal.NotAPage: notPages++; continue;
                    case PageRefusal.TooLarge: tooLarge++; continue;
                }
                // Every page of a PDF counts, as the computer counts them; one the reader cannot open is left out.
                var read = pdf ? await Task.Run(() => _readPdf(path)) : new PdfRead(1);
                if (read.IsLocked) locked++;
                else if (read.IsDamaged) damaged++;
                else if (PageCount + read.Pages > Engine.Pages.MaxPages) over++;
                else Pages.Add(new PageItem(path, read.Pages));
            }
        }
        finally
        {
            IsAdding = false;
        }
        var said = new List<string>();
        if (notPages == 1) said.Add(_s["Pages_LeftOut_One"]);
        if (notPages > 1) said.Add(_s.Format("Pages_LeftOut_Many", notPages));
        if (tooLarge > 0) said.Add(_s["Error_Pages_PageTooLarge"]);
        if (locked > 0) said.Add(_s["Pages_PdfLocked"]);
        if (damaged > 0) said.Add(_s["Pages_PdfDamaged"]);
        if (over > 0) said.Add(_s.Format("Pages_TooMany", Engine.Pages.MaxPages));
        StatusText = said.Count > 0 ? string.Join(" ", said) : null;
        if (StatusText is { } text) _announcer.Announce(text, AnnouncementKind.Important);
    }

    /// <summary>A file's first bytes, which say what it is.</summary>
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

    /// <summary>Pages already looked at and counted (the sample scenes), added as they are.</summary>
    public void Put(string path, int pages) => Pages.Add(new PageItem(path, pages));

    /// <summary>Files are being looked at and counted: Read the notes waits for them.</summary>
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ReadCommand))]
    public partial bool IsAdding { get; set; }

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

    private bool CanRead() => Pages.Count > 0 && ComputerThere && !IsAdding;

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
