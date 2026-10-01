import Testing
@testable import OnDeviceKit

/// How long a band draft the free memory allows: the models' fixed share first, then about 1 MB a second.
@Test func theBudgetLeavesRoomForTheModelsFirst() {
    #expect(OnDeviceBudget.maxSeconds(available: 0) == 0)
    #expect(OnDeviceBudget.maxSeconds(available: OnDeviceBudget.fixedBytes) == 0)
    #expect(OnDeviceBudget.maxSeconds(available: OnDeviceBudget.fixedBytes - 1) == 0)
    // 650 MB left once the models are in: ten minutes and fifty seconds
    #expect(OnDeviceBudget.maxSeconds(available: 1_000_000_000) == 650)
}

@Test func aFiveMinuteBandFitsAPhoneWithAGigabyteFree() {
    #expect(OnDeviceBudget.fits(seconds: 300, available: 1_000_000_000))
    #expect(!OnDeviceBudget.fits(seconds: 300, available: 600_000_000))
    #expect(OnDeviceBudget.fits(seconds: 250, available: 600_000_000))
}

@Test func thisMachineReportsSomeFreeMemory() {
    #expect(OnDeviceBudget.available > OnDeviceBudget.fixedBytes)
}
