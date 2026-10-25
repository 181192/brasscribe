using System.Net;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Tab;

namespace Kalli.Scribe.Tests;

/// <summary>A folder of its own for each test, gone after it.</summary>
public abstract class TempFolderTest : IDisposable
{
    protected string Dir { get; } = Directory.CreateTempSubdirectory("scribe-practice-").FullName;

    public void Dispose()
    {
        try { Directory.Delete(Dir, recursive: true); } catch (IOException) { }
        GC.SuppressFinalize(this);
    }
}

/// <summary>Where each song was left in practice (<see cref="PracticePlaces"/>): kept on disk by the song's job, and gone with the song.</summary>
public class PracticePlacesTests : TempFolderTest
{
    private string Folder => Path.Combine(Dir, "places");
    private PracticePlaces Places => new(Folder);

    [Fact]
    public void A_place_is_kept_and_read_back()
    {
        Assert.Null(Places.Read("job-1"));
        Places.Save("job-1", new PracticePlace(12.25, 70, new RepeatBars(8, 9)));
        Places.Save("job-2", new PracticePlace(0.0, 100, null));
        Assert.Equal(new PracticePlace(12.25, 70, new RepeatBars(8, 9)), Places.Read("job-1"));
        Assert.Equal(new PracticePlace(0.0, 100, null), Places.Read("job-2"));
        // The latest is what is kept.
        Places.Save("job-1", new PracticePlace(3.5, 60, new RepeatBars(2, 2)));
        Assert.Equal(new PracticePlace(3.5, 60, new RepeatBars(2, 2)), Places.Read("job-1"));
        Assert.Equal(new[] { PracticeRecordings.FileName("job-1"), PracticeRecordings.FileName("job-2") }.Order(),
            Directory.GetFiles(Folder).Select(Path.GetFileName).Order());
    }

    [Fact]
    public void What_cant_be_read_is_no_place()
    {
        Directory.CreateDirectory(Folder);
        File.WriteAllText(Path.Combine(Folder, PracticeRecordings.FileName("job-1")!), "not a place");
        Assert.Null(Places.Read("job-1"));
        // A repeat that isn't one is left out; the rest is kept.
        File.WriteAllText(Path.Combine(Folder, PracticeRecordings.FileName("job-2")!), "4.0 80 5 2");
        Assert.Equal(new PracticePlace(4.0, 80, null), Places.Read("job-2"));
        Assert.Null(Places.Read(""));
        // A second that is no number is no place.
        foreach (var at in new[] { "NaN", "Infinity" })
        {
            File.WriteAllText(Path.Combine(Folder, PracticeRecordings.FileName("job-3")!), $"{at} 80");
            Assert.Null(Places.Read("job-3"));
        }
    }

    [Fact]
    public void A_place_is_written_and_read_the_same_in_any_language_of_the_system()
    {
        var was = System.Globalization.CultureInfo.CurrentCulture;
        try
        {
            System.Globalization.CultureInfo.CurrentCulture = new System.Globalization.CultureInfo("nb-NO");
            Places.Save("job-1", new PracticePlace(12.25, 70, null));
            Assert.Equal("12.25 70", File.ReadAllText(Path.Combine(Folder, PracticeRecordings.FileName("job-1")!)));
            Assert.Equal(new PracticePlace(12.25, 70, null), Places.Read("job-1"));
        }
        finally
        {
            System.Globalization.CultureInfo.CurrentCulture = was;
        }
    }

    [Fact]
    public void A_song_that_left_takes_its_place_with_it()
    {
        Places.Save("job-1", new PracticePlace(1.0, 90, null));
        Places.Save("job-2", new PracticePlace(2.0, 80, null));
        Places.Prune(["job-2"]);
        Assert.Null(Places.Read("job-1"));
        Assert.Equal(new PracticePlace(2.0, 80, null), Places.Read("job-2"));
    }
}

/// <summary>The recordings kept on disk for practising (<see cref="PracticeRecordings"/>): one to a song, by its job on the computer.</summary>
public class PracticeRecordingsTests : TempFolderTest
{
    private string Kept => Path.Combine(Dir, "kept");
    private PracticeRecordings Store => new(Kept);

    private string Take(int bytes, string name = "take.wav")
    {
        string path = Path.Combine(Dir, name);
        File.WriteAllBytes(path, [.. Enumerable.Range(0, bytes).Select(i => (byte)i)]);
        return path;
    }

    private static long Length(string path) => new FileInfo(path).Length;

    [Fact]
    public void A_recording_in_hand_is_copied_and_found_again()
    {
        Assert.Null(Store.Find("job-1"));
        string take = Take(1000);
        string kept = Store.Keep("job-1", take);
        Assert.True(kept != take && File.Exists(kept), "the copy is the store's own file");
        Assert.Equal(1000L, Length(kept));
        // The take can go: the song still has its recording.
        File.Delete(take);
        Assert.Equal(kept, Store.Find("job-1"));
        // Kept once: the same recording again is the same file.
        Assert.Equal(kept, Store.Keep("job-1", Take(1000)));
        Assert.Null(Store.Find("job-2"));
    }

    [Fact]
    public void A_recording_being_fetched_is_not_there_until_it_is_whole()
    {
        string part = Store.Arriving("job-1")!;
        File.WriteAllBytes(part, new byte[10]);
        Assert.Null(Store.Find("job-1"));
        string? whole = Store.Arrived("job-1", part);
        Assert.NotNull(whole);
        Assert.Equal(whole, Store.Find("job-1"));
        // One that came empty is dropped.
        string empty = Store.Arriving("job-2")!;
        File.WriteAllBytes(empty, []);
        Assert.Null(Store.Arrived("job-2", empty));
        Assert.Null(Store.Find("job-2"));
        Assert.False(File.Exists(empty));
    }

    [Fact]
    public void A_fetch_given_up_late_never_takes_the_file_of_the_fetch_after_it()
    {
        // Leaving the screen gives the first fetch up; it clears its file only once the next fetch has begun.
        string first = Store.Arriving("job-1")!;
        File.WriteAllBytes(first, new byte[3]);
        string second = Store.Arriving("job-1")!;
        Assert.NotEqual(first, second);
        File.WriteAllBytes(second, new byte[12]);
        PracticeRecordings.Dropped(first);
        Assert.True(File.Exists(second), "the second fetch's file is still there");
        Assert.Equal(12L, Length(Store.Arrived("job-1", second)!));
        Assert.Equal(12L, Length(Store.Find("job-1")!));
        // The first one coming to an end after that changes nothing either.
        Assert.Null(Store.Arrived("job-1", first));
        Assert.Equal(12L, Length(Store.Find("job-1")!));
    }

    [Fact]
    public void A_song_that_is_gone_takes_its_recording_with_it()
    {
        Store.Keep("job-1", Take(10));
        Store.Keep("job-2", Take(20));
        File.WriteAllBytes(Store.Arriving("job-3")!, new byte[5]);
        Store.Prune(["job-2"]);
        Assert.Null(Store.Find("job-1"));
        Assert.NotNull(Store.Find("job-2"));
        Assert.Equal([Path.GetFileName(Store.Find("job-2"))], Directory.GetFiles(Kept).Select(Path.GetFileName));
    }

    [Fact]
    public void A_jobs_id_never_leaves_the_folder()
    {
        string kept = Store.Keep("../../outside", Take(10));
        Assert.Equal(Path.GetFullPath(Kept), Path.GetDirectoryName(Path.GetFullPath(kept)));
        Assert.Equal(Path.GetFullPath(Kept), Path.GetDirectoryName(Path.GetFullPath(Store.Keep("/..", Take(10)))));
        Assert.Equal(Path.GetFullPath(Kept), Path.GetDirectoryName(Path.GetFullPath(Store.Keep(@"..\..\outside", Take(10)))));
        // No id keeps nothing.
        string take = Take(10);
        Assert.Equal(take, Store.Keep("", take));
        Assert.Null(Store.Find(""));
    }

    [Fact]
    public void Ids_that_read_alike_are_still_two_songs()
    {
        string a = Store.Keep("job/1", Take(10));
        string b = Store.Keep("job1", Take(20));
        Assert.NotEqual(a, b);
        Assert.Equal(10L, Length(Store.Find("job/1")!));
        Assert.Equal(20L, Length(Store.Find("job1")!));
        // Also past the length a file name keeps of the id.
        string longId = new('x', 200);
        string c = Store.Keep(longId + "a", Take(30));
        string d = Store.Keep(longId + "b", Take(40));
        Assert.True(c != d && Path.GetFileName(c).Length < 100);
        Assert.Equal(30L, Length(Store.Find(longId + "a")!));
    }

    [Fact]
    public void What_a_try_left_behind_is_cleared()
    {
        // A fetch that stopped half way: its part is gone when it is given up, and when the songs are gone through.
        string again = Store.Arriving("job-1")!;
        File.WriteAllBytes(again, new byte[7]);
        PracticeRecordings.Dropped(again);
        Assert.False(File.Exists(again));
        File.WriteAllBytes(Store.Arriving("job-1")!, new byte[7]);
        File.WriteAllBytes(Store.Arriving("job-1")!, new byte[7]);
        Store.Keep("job-2", Take(5));
        Store.Prune(["job-1", "job-2"]);
        Assert.Single(Directory.GetFiles(Kept));
        Assert.NotNull(Store.Find("job-2"));
        Assert.True(Store.Room > 0);
    }

    [Fact]
    public void A_recording_that_did_not_come_says_why()
    {
        const long plenty = 1L << 30;
        Assert.Equal(RecordingState.Gone, PracticeRecordings.WhyNot(new EngineException("gone", HttpStatusCode.NotFound), plenty));
        Assert.Equal(RecordingState.TooLarge, PracticeRecordings.WhyNot(new EngineException("too large", HttpStatusCode.RequestEntityTooLarge), plenty));
        Assert.Equal(RecordingState.NoAnswer, PracticeRecordings.WhyNot(new EngineException("broken", HttpStatusCode.InternalServerError), plenty));
        Assert.Equal(RecordingState.NoAnswer, PracticeRecordings.WhyNot(new EngineException("refused"), plenty));
        Assert.Equal(RecordingState.NoAnswer, PracticeRecordings.WhyNot(new HttpRequestException("refused"), plenty));
        // Not asked, because one of the two needs an update: said as that, not as a computer that does not answer.
        Assert.Equal(RecordingState.UpdateApp, PracticeRecordings.WhyNot(new EngineException("x", code: EngineException.UpdateApp), plenty));
        Assert.Equal(RecordingState.UpdateComputer, PracticeRecordings.WhyNot(new EngineException("x", code: EngineException.UpdateBandroom), plenty));
        Assert.Equal(RecordingState.NoAnswer, PracticeRecordings.WhyNot(new IOException("the recording came empty"), plenty));
        // The disk is full, or the file could not be made: it is not the computer that is away.
        Assert.Equal(RecordingState.NoRoom, PracticeRecordings.WhyNot(new IOException("write failed: ENOSPC"), 1000));
        Assert.Equal(RecordingState.NoRoom, PracticeRecordings.WhyNot(new FileNotFoundException("no such directory"), plenty));
        Assert.Equal(RecordingState.NoRoom, PracticeRecordings.WhyNot(new DirectoryNotFoundException("no such directory"), plenty));
        Assert.Equal(RecordingState.NoRoom, PracticeRecordings.WhyNot(new InvalidOperationException("no place to keep the recording"), plenty));
    }

    [Fact]
    public void A_kept_recording_is_sent_again_named_for_the_kind_of_file_it_is()
    {
        string Kind(params int[] head)
        {
            string path = Path.Combine(Dir, "kind");
            File.WriteAllBytes(path, [.. head.Select(b => (byte)b), .. new byte[16]]);
            return PracticeRecordings.ExtensionOf(path);
        }
        string KindOf(string text, int at = 0) => Kind([.. new int[at], .. text.Select(c => (int)c)]);
        Assert.Equal("wav", KindOf("RIFF\0\0\0\0WAVE"));
        Assert.Equal("m4a", KindOf("ftypM4A ", at: 4));
        Assert.Equal("mp3", KindOf("ID3"));
        Assert.Equal("mp3", Kind(0xFF, 0xFB, 0x90));
        Assert.Equal("ogg", KindOf("OggS"));
        Assert.Equal("flac", KindOf("fLaC"));
        Assert.Equal("webm", Kind(0x1A, 0x45, 0xDF, 0xA3));
        // Anything else is taken as it was before there was a name: the computer reads it as a WAV file.
        Assert.Equal("wav", KindOf("hello"));
        Assert.Equal("wav", PracticeRecordings.ExtensionOf(Path.Combine(Dir, "none")));
        // A kept recording is found by the song's job, under the name the store gives it.
        string m4a = Path.Combine(Dir, "take.m4a");
        File.WriteAllBytes(m4a, [0, 0, 0, 0, .. "ftypM4A "u8.ToArray()]);
        Assert.Equal("m4a", PracticeRecordings.ExtensionOf(Store.Keep("job-1", m4a)));
    }
}
