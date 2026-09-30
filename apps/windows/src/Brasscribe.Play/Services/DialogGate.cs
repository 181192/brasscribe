using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Services;

/// <summary>
/// WinUI shows one ContentDialog at a time and throws when a second one opens (a pairing link that
/// arrives while Go to bar is open, say). Every dialog opens through here: one asked for while another
/// is open is not shown, and <see cref="ShowAsync"/> answers None.
/// </summary>
internal static class DialogGate
{
    private static ContentDialog? _open;

    public static bool IsOpen => _open is not null;

    /// <summary>The open dialog has closed; a dialog that had to wait can open now.</summary>
    public static event EventHandler? Closed;

    public static async Task<ContentDialogResult> ShowAsync(ContentDialog dialog)
    {
        if (_open is not null) return ContentDialogResult.None;
        _open = dialog;
        try
        {
            return await dialog.ShowAsync();
        }
        finally
        {
            _open = null;
            Closed?.Invoke(null, EventArgs.Empty);
        }
    }
}
