using Brasscribe.Play.Core.Bridge;

namespace Brasscribe.Play.Core.Tests;

public class CoreBridgeTests
{
    [Fact]
    public void Falls_back_to_managed_when_the_native_core_is_missing()
    {
        var bridge = CoreBridge.Create();
        if (bridge.IsNative) return; // a machine with brasscribe_ffi next to the tests
        Assert.Equal("managed", bridge.Version);
        Assert.Null(bridge.ArrangeMusicXml(bridge.ParseComposition("""{"title":"x","voices":[],"meters":[],"keys":[]}""")));
    }
}
