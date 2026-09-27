using Brasscribe.Bandroom.Core.Pairing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Brasscribe.Bandroom.Views;

public sealed partial class AllowCard : UserControl
{
    public AllowCard(AllowRequestViewModel vm)
    {
        Vm = vm;
        InitializeComponent();
        Mark.Source = new SvgImageSource(new Uri(ActualTheme == ElementTheme.Dark
            ? "ms-appx:///Assets/Brand/mark-on-dark.svg" : "ms-appx:///Assets/Brand/mark.svg"));
        vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(AllowRequestViewModel.IsExpired) && vm.IsExpired)
                DispatcherQueue.TryEnqueue(() => CloseButton.Focus(FocusState.Programmatic));
        };
    }

    public AllowRequestViewModel Vm { get; }

    /// <summary>Allow is the primary; it gets focus when the request appears.</summary>
    public void FocusAllow() => AllowButton.Focus(FocusState.Programmatic);
}
