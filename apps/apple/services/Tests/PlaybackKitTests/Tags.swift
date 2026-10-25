import Testing

extension Tag {
    /// Renders seconds of audio. The fast tier skips these suites by name (`make package-test-fast`,
    /// APPLE_SLOW in apps/apple/Makefile); swift test has no tag filter.
    @Tag static var slow: Self
}
