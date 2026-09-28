using Brasscribe.Play.Core.Bridge;

namespace Brasscribe.Play.Core.Tests;

public class CoreBridgeTests
{
    [SkippableFact]
    public void Falls_back_to_managed_when_the_native_core_is_missing()
    {
        var bridge = CoreBridge.Create();
        Skip.If(bridge.IsNative, "the native core loaded (brasscribe_ffi next to the tests or at BRASSCRIBE_FFI_PATH); this test checks the managed fallback");
        Assert.Equal("managed", bridge.Version);
        Assert.Null(bridge.ArrangeMusicXml(bridge.ParseComposition("""{"title":"x","voices":[],"meters":[],"keys":[]}""")));
    }
}
