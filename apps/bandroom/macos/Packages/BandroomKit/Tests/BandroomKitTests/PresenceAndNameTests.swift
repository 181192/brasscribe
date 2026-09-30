import CoreGraphics
import Foundation
import Testing
@testable import BandroomKit

@Suite struct ComputerNameTests {
    @Test func serialLikeNamesAreMachineGenerated() {
        for name in ["ABCD1234EF", "C02AB12CD3EF", "DESKTOP-ABC1234", "LAPTOP-ABCD1234"] {
            #expect(ComputerName.looksMachineGenerated(name), "\(name)")
        }
    }

    @Test func namesPeopleChoseAreKept() {
        for name in ["Kari's MacBook", "MacBook Pro", "Studio", "BANDROOM", "iMac-2", "Karis-MBP", "M3PRO", "korps-mac-01"] {
            #expect(!ComputerName.looksMachineGenerated(name), "\(name)")
        }
    }

    @Test func theShownNameDefaultsToTheComputerName() {
        #expect(ComputerName.shown(system: "ABCD1234EF", custom: nil) == "ABCD1234EF")
        #expect(ComputerName.shown(system: "ABCD1234EF", custom: "  ") == "ABCD1234EF")
        #expect(ComputerName.shown(system: "ABCD1234EF", custom: " Øvingslokalet ") == "Øvingslokalet")
    }

    @Test func settingsOffersTheFieldForMachineNamesOrOnceSet() {
        #expect(ComputerName.offersCustomName(system: "ABCD1234EF", custom: nil))
        #expect(!ComputerName.offersCustomName(system: "Kari's MacBook", custom: nil))
        #expect(ComputerName.offersCustomName(system: "Kari's MacBook", custom: "Korpset"))
    }

    @Test func theEngineGetsTheShownName() {
        let paths = BandroomPaths(data: URL(fileURLWithPath: "/tmp/d"), logs: URL(fileURLWithPath: "/tmp/l"))
        let config = EngineConfiguration(source: .checkout(URL(fileURLWithPath: "/tmp/c")), pixi: nil, paths: paths,
                                         computerName: ComputerName.shown(system: "ABCD1234EF", custom: "Korpset"), adminToken: "t")
        #expect(config.environment(base: [:])["BRASSCRIBE_COMPUTER_NAME"] == "Korpset")
        #expect(config.environment(base: ["HF_HUB_CACHE": "/h"])["HF_HUB_CACHE"] == "/h")
    }
}

@Suite struct MenuBarPresenceTests {
    let screen = CGRect(x: 0, y: 0, width: 1512, height: 982)
    let notch = CGRect(x: 662, y: 950, width: 188, height: 32)

    @Test func aVisibleItemIsNotHidden() {
        let r = StatusItemVisibility.Reading(frame: CGRect(x: 1200, y: 958, width: 24, height: 24), occlusionVisible: true,
                                            screens: [screen], notches: [notch])
        #expect(!StatusItemVisibility.isHidden(r))
    }

    @Test func noWindowOrZeroSizeIsHidden() {
        #expect(StatusItemVisibility.isHidden(.init(frame: nil, occlusionVisible: true, screens: [screen])))
        #expect(StatusItemVisibility.isHidden(.init(frame: .zero, occlusionVisible: true, screens: [screen])))
    }

    @Test func occludedIsHidden() {
        #expect(StatusItemVisibility.isHidden(.init(frame: CGRect(x: 1200, y: 958, width: 24, height: 24), occlusionVisible: false,
                                                    screens: [screen])))
    }

    @Test func offscreenIsHidden() {
        #expect(StatusItemVisibility.isHidden(.init(frame: CGRect(x: -40, y: 958, width: 24, height: 24), occlusionVisible: true,
                                                    screens: [screen])))
    }

    @Test func underTheNotchIsHidden() {
        #expect(StatusItemVisibility.isHidden(.init(frame: CGRect(x: 700, y: 958, width: 24, height: 24), occlusionVisible: true,
                                                    screens: [screen], notches: [notch])))
    }

    @Test func reopenShowsSetupUntilItIsDoneThenTheWindow() {
        #expect(ReopenPolicy.target(setupComplete: false) == .setup)
        #expect(ReopenPolicy.target(setupComplete: true) == .main)
    }

    @MainActor @Test func windowRequestsWaitForTheOpener() {
        let opener = WindowOpener()
        var opened: [String] = []
        opener("main")
        opener("main")
        #expect(!opener.isReady)
        opener.attach { opened.append($0) }
        #expect(opened == ["main"])
        opener("pair")
        #expect(opened == ["main", "pair"])
    }
}
