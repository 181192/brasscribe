import Foundation

/// The licence step of setup (design/server-app.md §3.2): the band writer's terms are accepted here, before it downloads.
public enum LicenceStep {
    /// The model page: the licence and its makers' conditions of use, in full.
    public static var termsPage: URL { ModelComponent.bandWriter.page }

    /// Continue saves the typed key, or goes on with the saved one. Either way the band writer downloads next,
    /// so the box under its terms must be ticked first.
    public static func canContinue(key: String, keySaved: Bool, saving: Bool, termsAccepted: Bool) -> Bool {
        termsAccepted && !saving && (!key.isEmpty || keySaved)
    }
}
