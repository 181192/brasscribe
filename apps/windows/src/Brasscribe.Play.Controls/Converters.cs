using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;

namespace Brasscribe.Play.Controls;

/// <summary>int view-model properties to NumberBox's double Value and back.</summary>
public sealed partial class IntToDoubleConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, string language) =>
        value is int i ? (double)i : 0.0;

    public object ConvertBack(object value, Type targetType, object parameter, string language) =>
        value is double d && !double.IsNaN(d) ? (int)Math.Round(d) : 0;
}

/// <summary>
/// The custom icon glyphs of the design tokens (BcIconPath*: metronome, count-in, only this, next
/// uncertain) are path-data strings; PathIcon.Data needs a Geometry.
/// Use: Data="{Binding Source={StaticResource BcIconPathMetronome}, Converter={StaticResource PathData}}".
/// </summary>
public sealed partial class PathDataConverter : IValueConverter
{
    public object? Convert(object value, Type targetType, object parameter, string language) =>
        value is string data ? XamlBindingHelper.ConvertValue(typeof(Geometry), data) : null;

    public object ConvertBack(object value, Type targetType, object parameter, string language) =>
        throw new NotSupportedException();
}

/// <summary>bool to Visibility with the meaning flipped (x:Bind binds bool to Visibility directly otherwise).</summary>
public sealed partial class NotConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, string language) =>
        value is true ? Microsoft.UI.Xaml.Visibility.Collapsed : Microsoft.UI.Xaml.Visibility.Visible;

    public object ConvertBack(object value, Type targetType, object parameter, string language) =>
        throw new NotSupportedException();
}

/// <summary>Small functions for x:Bind that need WinUI types.</summary>
public static class Bind
{
    /// <summary>Semibold for the current row (the current step, the active part).</summary>
    public static Windows.UI.Text.FontWeight Weight(bool strong) => new() { Weight = (ushort)(strong ? 600 : 400) };
}
