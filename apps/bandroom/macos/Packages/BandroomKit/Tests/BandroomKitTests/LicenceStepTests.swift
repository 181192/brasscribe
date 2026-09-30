import Foundation
import Testing
@testable import BandroomKit

/// Nothing downloads the band writer until its terms are accepted.
struct LicenceStepTests {
    @Test func continueWaitsForTheTerms() {
        #expect(!LicenceStep.canContinue(key: "hf_abc", keySaved: false, saving: false, termsAccepted: false))
        #expect(LicenceStep.canContinue(key: "hf_abc", keySaved: false, saving: false, termsAccepted: true))
    }

    @Test func aSavedKeyStillNeedsTheTerms() {
        #expect(!LicenceStep.canContinue(key: "", keySaved: true, saving: false, termsAccepted: false))
        #expect(LicenceStep.canContinue(key: "", keySaved: true, saving: false, termsAccepted: true))
    }

    @Test func noKeyOrASaveUnderWayCantContinue() {
        #expect(!LicenceStep.canContinue(key: "", keySaved: false, saving: false, termsAccepted: true))
        #expect(!LicenceStep.canContinue(key: "hf_abc", keySaved: false, saving: true, termsAccepted: true))
    }

    @Test func theFullTermsAreOnTheModelPage() {
        #expect(LicenceStep.termsPage.absoluteString == "https://huggingface.co/MuScriptor/muscriptor-medium")
    }
}
