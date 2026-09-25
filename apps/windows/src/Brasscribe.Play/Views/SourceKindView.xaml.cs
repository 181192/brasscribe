using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Views;

public sealed partial class SourceKindView : UserControl
{
    public SourceKindView() => InitializeComponent();

    public SourceKindViewModel ViewModel
    {
        get => (SourceKindViewModel)GetValue(ViewModelProperty);
        set => SetValue(ViewModelProperty, value);
    }

    public static readonly DependencyProperty ViewModelProperty =
        DependencyProperty.Register(nameof(ViewModel), typeof(SourceKindViewModel), typeof(SourceKindView), new PropertyMetadata(null));

    public void FocusHeading()
    {
        Options.SelectedIndex = -1;
        Heading.Focus(FocusState.Programmatic);
    }

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs e) =>
        ViewModel.Selected = Options.SelectedItem as SourceKindOption;
}
