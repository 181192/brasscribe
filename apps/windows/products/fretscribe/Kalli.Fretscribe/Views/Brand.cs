using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Kalli.Fretscribe.Views;

/// <summary>The mark in the element's own theme: the ink tile on light, the paper tile on dark.</summary>
internal static class Brand
{
    public static void ShowMark(Image image, FrameworkElement theme)
    {
        string file = theme.ActualTheme == ElementTheme.Dark ? "logo-mark-dark.svg" : "logo-mark.svg";
        image.Source = new SvgImageSource(new Uri($"ms-appx:///Assets/Brand/{file}"));
    }
}
