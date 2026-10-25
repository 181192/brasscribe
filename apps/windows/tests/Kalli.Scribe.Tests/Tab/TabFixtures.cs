using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;

namespace Kalli.Scribe.Tests;

/// <summary>The recorded tabs in apps/fixtures (bass-line, guitar-line, ukulele-line, tab-probes/…), read where they are in the repository.</summary>
internal static class TabFixtures
{
    public static string Text(string name, string file) =>
        File.ReadAllText(TestPaths.RepoFile($"apps/fixtures/{name}/{file}") ?? throw new FileNotFoundException(TestPaths.Missing($"apps/fixtures/{name}/{file}")));

    public static string MusicXml(string name) => Text(name, "tab.musicxml");

    public static TabResult Tab(string name) => TabResult.Parse(Text(name, "tab.json")) ?? throw new InvalidDataException($"{name}/tab.json is not a tab");

    public static (string Xml, TabResult Tab) Both(string name) => (MusicXml(name), Tab(name));
}

/// <summary>Settings kept in a dictionary the test can look into.</summary>
internal sealed class DictionarySettings(Dictionary<string, object?>? values = null) : ISettingsStore
{
    public Dictionary<string, object?> Values { get; } = values ?? [];
    public T Get<T>(string key, T fallback) => Values.TryGetValue(key, out var v) && v is T t ? t : fallback;
    public void Set<T>(string key, T value) => Values[key] = value;
}
