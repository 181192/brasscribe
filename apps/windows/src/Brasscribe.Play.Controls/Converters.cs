using Microsoft.UI.Xaml.Data;

namespace Brasscribe.Play.Controls;

/// <summary>int view-model properties to NumberBox's double Value and back.</summary>
public sealed partial class IntToDoubleConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, string language) =>
        value is int i ? (double)i : 0.0;

    public object ConvertBack(object value, Type targetType, object parameter, string language) =>
        value is double d && !double.IsNaN(d) ? (int)Math.Round(d) : 0;
}
