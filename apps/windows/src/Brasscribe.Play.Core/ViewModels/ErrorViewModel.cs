using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>What went wrong, for the error screen.</summary>
public enum ErrorKind { ComputerUnreachable, ScoreFailed }

/// <summary>
/// An error with a way forward (design/system.md §5, Errors with recovery): the title says what
/// happened, the reason why, numbered steps what to do, and the buttons are the way out, the most
/// likely fix first. The recording is never lost, and the screen says so. Commands and codes for the
/// band's tech person sit behind a "Details" disclosure, never in the body.
/// </summary>
public sealed partial class ErrorViewModel(IStrings s) : ObservableObject
{
    [ObservableProperty] public partial ErrorKind Kind { get; set; }
    [ObservableProperty] public partial string Title { get; set; } = "";
    [ObservableProperty] public partial string Reason { get; set; } = "";
    [ObservableProperty] public partial string PrimaryLabel { get; set; } = "";
    [ObservableProperty] public partial string SecondaryLabel { get; set; } = "";
    [ObservableProperty] public partial string DetailsHeading { get; set; } = "";
    [ObservableProperty] public partial string Details { get; set; } = "";

    public ObservableCollection<string> Steps { get; } = [];

    /// <summary>The most likely fix (Try again).</summary>
    public event EventHandler? Retry;

    /// <summary>The other way out (Choose another recording).</summary>
    public event EventHandler? Alternative;

    public void Show(ErrorKind kind, string? technical)
    {
        Kind = kind;
        string k = kind.ToString();
        Title = s[$"Error_{k}_Title"];
        Reason = s[$"Error_{k}_Reason"];
        Steps.Clear();
        foreach (var n in new[] { 1, 2, 3 })
            if (s[$"Error_{k}_Step{n}"] is { Length: > 0 } step && step != $"Error_{k}_Step{n}") Steps.Add(step);
        PrimaryLabel = s["Error_TryAgain"];
        SecondaryLabel = s["Error_ChooseAnother"];
        DetailsHeading = s["Error_DetailsHeading"];
        Details = kind == ErrorKind.ComputerUnreachable
            ? s.Format("Error_ComputerUnreachable_Details", technical ?? "")
            : technical ?? "";
    }

    [RelayCommand]
    private void TryAgain() => Retry?.Invoke(this, EventArgs.Empty);

    [RelayCommand]
    private void ChooseAnother() => Alternative?.Invoke(this, EventArgs.Empty);
}
