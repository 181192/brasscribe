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

    /// <summary>The open dialog, once it has opened (its Opened event): the screen catalogue waits for it.</summary>
    public static ContentDialog? Opened { get; private set; }

    /// <summary>The open dialog has closed; a dialog that had to wait can open now.</summary>
    public static event EventHandler? Closed;

    public static async Task<ContentDialogResult> ShowAsync(ContentDialog dialog)
    {
        if (_open is not null) return ContentDialogResult.None;
        _open = dialog;
        void OnOpened(ContentDialog sender, ContentDialogOpenedEventArgs args) => Opened = sender;
        dialog.Opened += OnOpened;
        try
        {
            return await dialog.ShowAsync();
        }
        finally
        {
            dialog.Opened -= OnOpened;
            Opened = null;
            _open = null;
            Closed?.Invoke(null, EventArgs.Empty);
        }
    }
}
