using CommunityToolkit.Mvvm.ComponentModel;

namespace Brasscribe.Bandroom.Core.ViewModels;

/// <summary>
/// The Hugging Face access card in Settings, where the key is entered (design/server-app.md §3.2, step 2). Saving it
/// starts the band writer's download, so its terms are shown here and must be accepted first.
/// </summary>
public sealed partial class HuggingFaceKeyViewModel : ObservableObject
{
    private readonly IStrings _s;

    public HuggingFaceKeyViewModel(IStrings strings) => _s = strings;

    /// <summary>What the band writer is and its licence (CC BY-NC 4.0).</summary>
    public string Licence => _s["Setup_2_Body"];

    /// <summary>The makers' condition: the rights to the music, and the responsibility for it.</summary>
    public string Terms => _s["Setup_2_Terms"];

    /// <summary>The checkbox's label, and so its accessible name.</summary>
    public string Agree => _s["Setup_2_Agree"];

    /// <summary>The link to the model page, where the full terms are.</summary>
    public string ReadTerms => _s["Setup_2_Read"];

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(CanSave))]
    private string _key = "";

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(CanSave))]
    private bool _termsAccepted;

    public bool CanSave => TermsAccepted && Key.Trim().Length > 0;
}
