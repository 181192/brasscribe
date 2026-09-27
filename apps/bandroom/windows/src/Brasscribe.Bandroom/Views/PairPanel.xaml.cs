using System.Collections.Specialized;
using Brasscribe.Bandroom.Core.Pairing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Brasscribe.Bandroom.Views;

public sealed partial class PairPanel : UserControl
{
    public PairPanel(PairViewModel vm)
    {
        Vm = vm;
        InitializeComponent();
        vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(PairViewModel.QrPayload)) _ = ShowQrAsync(vm.QrPayload);
        };
        vm.PairedFocusRequested += () => DispatcherQueue.TryEnqueue(() => AnotherButton.Focus(FocusState.Programmatic));
        vm.Requests.CollectionChanged += OnRequestsChanged;
        foreach (var r in vm.Requests) AddCard(r);
        if (vm.QrPayload.Length > 0) _ = ShowQrAsync(vm.QrPayload);
    }

    public PairViewModel Vm { get; }

    /// <summary>Done was pressed: the window closes (which closes the code).</summary>
    public event Action? DoneRequested;

    private void OnDone(object sender, RoutedEventArgs e) => DoneRequested?.Invoke();

    public void FocusDone() => DoneButton.Focus(FocusState.Programmatic);

    private async Task ShowQrAsync(string payload)
    {
        if (payload.Length == 0) { QrImage.Source = null; return; }
        var png = QrImage_Png(payload);
        var bmp = new BitmapImage();
        using var stream = new Windows.Storage.Streams.InMemoryRandomAccessStream();
        using (var writer = new Windows.Storage.Streams.DataWriter(stream.GetOutputStreamAt(0)))
        {
            writer.WriteBytes(png);
            await writer.StoreAsync();
            await writer.FlushAsync();
            writer.DetachStream();
        }
        stream.Seek(0);
        await bmp.SetSourceAsync(stream);
        QrImage.Source = bmp;
    }

    private static byte[] QrImage_Png(string payload) => Core.Pairing.QrImage.Png(payload, pixelsPerModule: 8);

    private void OnRequestsChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        if (e.NewItems is not null)
            foreach (AllowRequestViewModel r in e.NewItems) AddCard(r);
        if (e.OldItems is not null)
            foreach (AllowRequestViewModel r in e.OldItems)
                foreach (var card in Requests.Children.OfType<AllowCard>().Where(c => c.Vm == r).ToList())
                    Requests.Children.Remove(card);
        if (e.Action == NotifyCollectionChangedAction.Reset) Requests.Children.Clear();
    }

    private void AddCard(AllowRequestViewModel r)
    {
        var card = new AllowCard(r);
        Requests.Children.Add(card);
        DispatcherQueue.TryEnqueue(card.FocusAllow);
    }
}
