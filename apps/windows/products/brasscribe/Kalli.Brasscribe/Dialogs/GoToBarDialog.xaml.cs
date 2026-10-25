using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Dialogs;

public sealed partial class GoToBarDialog : ContentDialog
{
    public GoToBarDialog(int current, int barCount)
    {
        InitializeComponent();
        BarBox.Maximum = barCount;
        BarBox.Value = current;
        Opened += (_, _) => BarBox.Focus(FocusState.Programmatic);
    }

    public int? Bar => double.IsNaN(BarBox.Value) ? null : (int)Math.Round(BarBox.Value);
}
