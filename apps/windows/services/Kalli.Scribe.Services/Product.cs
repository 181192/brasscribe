namespace Kalli.Scribe;

/// <summary>What this app is among the apps on the shared core: the target whose scores it makes and shows.</summary>
public static class Product
{
    /// <summary>The target's id as the engine gives it for a profile (<c>ProfileInfo.Target</c>).</summary>
    public const string Target = "brass";

    /// <summary>The same target as the core's C interface takes it (<c>SC_TARGET_BRASS</c>).</summary>
    public const int CoreTarget = 0;
}
