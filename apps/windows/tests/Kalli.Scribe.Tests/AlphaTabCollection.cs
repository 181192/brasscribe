namespace Brasscribe.Play.Core.Tests;

/// <summary>alphaTab keeps shared static state; tests that load or render scores run one at a time.</summary>
[CollectionDefinition(Name, DisableParallelization = true)]
public sealed class AlphaTabCollection
{
    public const string Name = "alphaTab";
}
