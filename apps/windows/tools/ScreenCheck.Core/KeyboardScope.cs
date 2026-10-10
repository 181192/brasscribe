namespace Brasscribe.ScreenCheck;

/// <summary>An element above a Tab stop: its UI Automation runtime id, and whether it is an open modal dialog.</summary>
public readonly record struct ScopeNode(string Id, bool IsModalDialog);

/// <summary>
/// Where the walk with Tab must reach every control: the whole window, or an open modal dialog when every stop of
/// the walk was inside it (a dialog keeps the focus in itself, so what is behind it is rightly out of reach).
/// Tab caught in one pane of the window is not a reason to look only there: then the window is the scope, and what
/// lies outside the pane is reported as never reached.
/// </summary>
public static class KeyboardScope
{
    /// <param name="chains">For each stop, its ancestors from the top down.</param>
    /// <returns>The modal dialog to look in, or null for the whole window.</returns>
    public static ScopeNode? Choose(IReadOnlyList<IReadOnlyList<ScopeNode>> chains)
    {
        if (chains.Count == 0) return null;
        // The innermost modal dialog above the first stop that is above every other stop as well.
        foreach (var node in chains[0].Reverse())
            if (node.IsModalDialog && chains.All(c => c.Any(n => n.Id == node.Id))) return node;
        return null;
    }
}
