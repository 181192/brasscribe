# Brasscribe Play for Apple platforms.
#   make verovio     build Verovio.xcframework (once, ~2 min)
#   make soundfont   download the baseline SF2 into data/soundfonts
#   make bandsound   stage the band SoundFont + mapping into Sounds/ (bundled; also run by make project)
#   make project     generate BrasscribePlay.xcodeproj with XcodeGen
#   make build       build macOS, iOS Simulator and iPad Simulator
#   make test        package tests, macOS app unit tests (no UI), app unit + UI tests on an iOS simulator
#   make package-test-fast  package tests without the slow audio-rendering suites
#   make build-for-testing-mac, then make test-mac-unit (repeatable): macOS app unit tests without rebuilding
#   make test-mac-ui macOS UI tests: they take over the mouse and keyboard, so run them only when
#                    nobody is using the Mac (or in CI)
export DEVELOPER_DIR ?= /Applications/Xcode.app/Contents/Developer
ROOT := $(abspath ../..)
FIXTURES ?= $(ROOT)/apps/fixtures/old-hundredth
# IPHONE=<name> picks a simulator by name; by default the newest "iPhone NN Pro" on the newest
# iOS runtime (scripts/newest-iphone.sh), selected by id.
IPHONE ?=
IPAD ?= iPad Air 11-inch (M4)
comma := ,
IPHONE_DEST ?= $(if $(IPHONE),platform=iOS Simulator$(comma)name=$(IPHONE),$(shell DEVELOPER_DIR="$(DEVELOPER_DIR)" scripts/newest-iphone.sh))
DERIVED := build/DerivedData
# Swift suites the fast tier skips (swift test --skip takes a regular expression; see docs/dev/verify.md).
APPLE_SLOW ?= ArrangementLevelTests|DynamicsLevelTests|RecordingLevelTests
XCB := xcodebuild -project BrasscribePlay.xcodeproj -derivedDataPath $(DERIVED)

.PHONY: verovio soundfont bandsound project build test test-mac-ui package-test size \
        build-for-testing-mac test-mac-unit build-for-testing-ios test-ios-unit package-test-fast

verovio:
	./scripts/build-verovio.sh

soundfont:
	./scripts/fetch-soundfont.sh

bandsound:
	./scripts/stage-band-sounds.sh

project:
	xcodegen generate

build: project
	$(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' build
	$(XCB) -scheme BrasscribePlay-iOS -destination '$(IPHONE_DEST)' build
	$(XCB) -scheme BrasscribePlay-iOS -destination 'platform=iOS Simulator,name=$(IPAD)' build

package-test:
	cd Packages/BrasscribeKit && swift test
	cd Packages/NotationKit && swift test
	cd ../../capture && swift test

test: project package-test
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' test
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-iOS -destination '$(IPHONE_DEST)' test

# The macOS UI tests move the real pointer and type real keys. Not part of `make test`: run them
# only on a Mac nobody is using, or in CI.
test-mac-ui: project
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-macOS-UITests -destination 'platform=macOS' test

size: project
	$(XCB) -scheme BrasscribePlay-iOS -configuration Release -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
	du -sh "$(DERIVED)/Build/Products/Release-iphoneos/BrasscribePlay.app"

# Repeat runs without rebuilding (docs/dev/verify.md): build-for-testing once, then run the unit
# tests from the same DerivedData as often as needed. No UI tests.
#   make build-for-testing-mac   then   make test-mac-unit        macOS app unit tests
#   make build-for-testing-ios   then   make test-ios-unit        app unit tests on the iPhone simulator
build-for-testing-mac: project
	$(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' build-for-testing

test-mac-unit:
	@test -d $(DERIVED)/Build/Products/Debug || $(MAKE) build-for-testing-mac
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' \
	  -only-testing:BrasscribePlayTests_macOS test-without-building

build-for-testing-ios: project
	$(XCB) -scheme BrasscribePlay-iOS -destination '$(IPHONE_DEST)' build-for-testing

test-ios-unit:
	@test -d $(DERIVED)/Build/Products/Debug-iphonesimulator || $(MAKE) build-for-testing-ios
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-iOS -destination '$(IPHONE_DEST)' \
	  -only-testing:BrasscribePlayTests_iOS test-without-building

# Package tests without the slow audio-rendering suites (tier 1). --no-parallel as in package-test:
# PlaybackKitTests crash (SIGTRAP) when Swift Testing runs them in parallel.
package-test-fast:
	cd Packages/BrasscribeKit && swift test --no-parallel --skip '$(APPLE_SLOW)'
	cd Packages/NotationKit && swift test --no-parallel --skip '$(APPLE_SLOW)'
