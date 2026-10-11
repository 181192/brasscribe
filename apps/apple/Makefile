# Brasscribe Play for Apple platforms.
#   make verovio     build Verovio.xcframework (once, ~2 min)
#   make soundfont   download the baseline SF2 into data/soundfonts
#   make bandsound   stage the band SoundFont + mapping into Sounds/ (bundled; also run by make project)
#   make project     generate BrasscribePlay.xcodeproj with XcodeGen
#   make build       build macOS, iOS Simulator and iPad Simulator
#   make test        package tests, macOS app unit tests (no UI), app unit + UI tests on an iOS simulator
#                    (its parts: make package-test, make test-mac-app, make test-iphone)
#   make package-test-fast  package tests without the slow audio-rendering suites
#   make build-for-testing-mac, then make test-mac-unit (repeatable): macOS app unit tests without rebuilding
#   scripts/screenshots.sh record   the Mac screen catalogue, off screen, with its checks and a screenshot of each (README, Testing)
#   make test-mac-ui macOS UI tests: they take over the mouse and keyboard, so run them only in the
#                    macOS VM (scripts/mac-vm.sh test-ui, docs/dev/macos-vm.md) or in CI
#   make install-mac Release build into /Applications/Brasscribe Play.app, launched and checked
#   make ipa         unsigned Release build for iPhone and iPad (build/brasscribe-play-ios-unsigned.ipa)
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
# The screen catalogue (PlayScreensTests) runs through scripts/screenshots.sh record|compare, not with the unit tests.
SKIP_CATALOGUE := -skip-testing:BrasscribePlayTests_macOS/PlayScreensTests

.PHONY: verovio soundfont bandsound project build test test-mac-app test-iphone test-mac-ui package-test size install-mac ipa \
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
	cd Packages/ScreenCatalogue && swift test
	cd ../../capture && swift test

# CI runs the parts apart: package-test and test-mac-app on a pull request, which also builds the iPhone
# simulator app and its tests (build-for-testing-ios); test-iphone every night (.github/workflows/nightly.yml).
test: package-test test-mac-app test-iphone

test-mac-app: project
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' $(SKIP_CATALOGUE) test

test-iphone: project
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-iOS -destination '$(IPHONE_DEST)' $(TEST_ARGS) test

# The macOS UI tests move the real pointer and type real keys. Not part of `make test`: run them
# only in the macOS VM (scripts/mac-vm.sh test-ui) or in CI. TEST_ARGS adds xcodebuild arguments
# (-resultBundlePath, -only-testing:…).
TEST_ARGS ?=
test-mac-ui: project
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-macOS-UITests -destination 'platform=macOS' $(TEST_ARGS) test

# Ad-hoc signatures carry no Team ID, so under the hardened runtime dyld rejects the embedded
# Verovio.framework; the runtime only matters for notarised Developer ID builds.
INSTALLED_APP := /Applications/Brasscribe Play.app
install-mac: project
	$(XCB) -scheme BrasscribePlay-macOS -configuration Release -destination 'platform=macOS' \
	  ENABLE_HARDENED_RUNTIME=NO build
	codesign --verify --deep --strict "$(DERIVED)/Build/Products/Release/BrasscribePlay.app"
	test -s "$(DERIVED)/Build/Products/Release/BrasscribePlay.app/Contents/Resources/Sounds/mapping.json"
	-osascript -e 'quit app "Brasscribe Play"'
	rm -rf "$(INSTALLED_APP)"
	ditto "$(DERIVED)/Build/Products/Release/BrasscribePlay.app" "$(INSTALLED_APP)"
	open "$(INSTALLED_APP)"
	sleep 5; pgrep -xq BrasscribePlay || { echo 'Brasscribe Play exited at launch; see ~/Library/Logs/DiagnosticReports'; exit 1; }

size: project
	$(XCB) -scheme BrasscribePlay-iOS -configuration Release -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
	du -sh "$(DERIVED)/Build/Products/Release-iphoneos/BrasscribePlay.app"

# The file a release attaches for iPhone and iPad: unsigned, for a tester to sign (README, "iPhone and iPad (test build)").
ipa:
	./scripts/make-ipa.sh

# Repeat runs without rebuilding (docs/dev/verify.md): build-for-testing once, then run the unit
# tests from the same DerivedData as often as needed. No UI tests.
#   make build-for-testing-mac   then   make test-mac-unit        macOS app unit tests
#   make build-for-testing-ios   then   make test-ios-unit        app unit tests on the iPhone simulator
build-for-testing-mac: project
	$(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' build-for-testing

test-mac-unit:
	@ls $(DERIVED)/Build/Products/BrasscribePlay-macOS_*.xctestrun >/dev/null 2>&1 || $(MAKE) build-for-testing-mac
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' \
	  -only-testing:BrasscribePlayTests_macOS $(SKIP_CATALOGUE) test-without-building

build-for-testing-ios: project
	$(XCB) -scheme BrasscribePlay-iOS -destination '$(IPHONE_DEST)' build-for-testing

test-ios-unit:
	@ls $(DERIVED)/Build/Products/BrasscribePlay-iOS_*.xctestrun >/dev/null 2>&1 || $(MAKE) build-for-testing-ios
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-iOS -destination '$(IPHONE_DEST)' \
	  -only-testing:BrasscribePlayTests_iOS test-without-building

# Package tests without the slow audio-rendering suites (tier 1). --no-parallel as in package-test:
# PlaybackKitTests crash (SIGTRAP) when Swift Testing runs them in parallel.
package-test-fast:
	cd Packages/BrasscribeKit && swift test --no-parallel --skip '$(APPLE_SLOW)'
	cd Packages/NotationKit && swift test --no-parallel --skip '$(APPLE_SLOW)'
	cd Packages/ScreenCatalogue && swift test
