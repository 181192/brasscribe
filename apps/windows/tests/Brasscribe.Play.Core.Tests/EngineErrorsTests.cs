using System.Net;
using System.Xml.Linq;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Services;

namespace Brasscribe.Play.Core.Tests;

/// <summary>Engine and core failures in the player's words: never the engine's English in the nb UI.</summary>
public class EngineErrorsTests
{
    private static IStrings Strings(string lang) => new ReswStrings(ReswStrings.Parse(XDocument.Load(
        Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play", "Strings", lang, "Resources.resw"))));

    private static EngineException Refused(string code) =>
        new("The engine answered 422. {\"detail\": \"percussion can't be written down\", \"code\": \"" + code + "\"}",
            HttpStatusCode.UnprocessableEntity, code: code);

    [Fact]
    public void The_422_body_code_is_read_when_there_is_one()
    {
        Assert.Equal("percussion_solo", EngineException.CodeOf("{\"detail\": \"x\", \"code\": \"percussion_solo\"}"));
        Assert.Null(EngineException.CodeOf("{\"detail\": [{\"loc\": [\"body\"], \"msg\": \"x\"}]}"));
        Assert.Null(EngineException.CodeOf("Internal Server Error"));
        Assert.Null(EngineException.CodeOf("[1, 2]"));
    }

    [Theory]
    [InlineData("quartet_needs_group", "Output_QuartetNeedsGroup")]
    [InlineData("percussion_solo", "Error_PercussionSolo")]
    [InlineData("seat_no_tune", "Error_SeatNoTune")]
    [InlineData("reads_not_offered", "Error_ReadsNotOffered")]
    [InlineData("invalid_options", "Error_Options")]
    [InlineData("something_new", "Error_Options")]
    public void Engine_codes_have_their_own_words(string code, string key) => Assert.Equal(key, EngineErrors.Key(Refused(code)));

    [Fact]
    public void Failures_without_a_code_go_by_status()
    {
        Assert.Equal("Error_Unreachable", EngineErrors.Key(new EngineException("could not be reached")));
        Assert.Equal("Error_Timeout", EngineErrors.Key(new EngineException("timed out", code: EngineException.Timeout)));
        Assert.Equal("Transcribe_Failed", EngineErrors.Key(new EngineException("Traceback ...", code: EngineException.JobFailed)));
        Assert.Equal("Error_NeedsPairing", EngineErrors.Key(new EngineException("x", HttpStatusCode.Unauthorized)));
        Assert.Equal("Error_NotFound", EngineErrors.Key(new EngineException("x", HttpStatusCode.NotFound)));
        Assert.Equal("Error_Options", EngineErrors.Key(new EngineException("x", HttpStatusCode.UnprocessableEntity)));
        Assert.Equal("Error_Engine", EngineErrors.Key(new EngineException("x", HttpStatusCode.InternalServerError)));
    }

    [Fact]
    public void Core_refusals_are_matched_on_the_core_message()
    {
        Assert.Equal("Error_PercussionSolo", EngineErrors.CoreKey(
            "invalid input: percussion can't be written down from a solo take yet: record the band; a recording with drums gets a percussion part"));
        Assert.Equal("Error_SeatNoTune", EngineErrors.CoreKey("invalid input: the E♭ Bass does not carry the tune"));
        Assert.Equal("Error_SeatNoTune", EngineErrors.CoreKey("the quartet keeps the tune on its 1st Cornet; lead=seat is for the band lineups"));
        Assert.Equal("Error_Arrange", EngineErrors.CoreKey("invalid input: composition has no key"));
    }

    [Fact]
    public void Every_message_exists_in_both_languages_and_nb_has_no_english()
    {
        var en = Strings("en-US");
        var nb = Strings("nb-NO");
        var keys = new[] { "quartet_needs_group", "percussion_solo", "seat_no_tune", "reads_not_offered", "invalid_options" }
            .Select(c => EngineErrors.Key(Refused(c)))
            .Concat(["Error_Unreachable", "Error_Timeout", "Error_NeedsPairing", "Error_NotFound", "Error_Engine", "Error_TooLarge", "Error_Arrange"]);
        foreach (var key in keys)
        {
            Assert.NotEqual(key, en[key]);
            Assert.NotEqual(key, nb[key]);
            Assert.NotEqual(en[key], nb[key]);
        }
        var said = EngineErrors.Message(Refused("percussion_solo"), nb);
        Assert.StartsWith("Brasscribe kan ikke skrive ned slagverk", said);
        Assert.DoesNotContain("percussion", said);
    }
}
