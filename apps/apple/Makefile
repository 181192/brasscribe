# Brasscribe Play for Apple platforms.
#   make verovio     build Verovio.xcframework (once, ~2 min)
#   make soundfont   download the baseline SF2 into data/soundfonts
#   make bandsound   stage the band SoundFont + mapping into Sounds/ (bundled; also run by make project)
#   make project     generate BrasscribePlay.xcodeproj with XcodeGen
#   make build       build macOS, iOS Simulator and iPad Simulator
#   make test        package tests, macOS app unit tests (no UI), app unit + UI tests on an iOS simulator
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
XCB := xcodebuild -project BrasscribePlay.xcodeproj -derivedDataPath $(DERIVED)

.PHONY: verovio soundfont bandsound project build test test-mac-ui package-test size

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
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' test \
		-skip-testing:BrasscribePlayUITests_macOS
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-iOS -destination '$(IPHONE_DEST)' test

# The macOS UI tests move the real pointer and type real keys. Not part of `make test`: run them
# only on a Mac nobody is using, or in CI.
test-mac-ui: project
	BRASSCRIBE_FIXTURES=$(FIXTURES) $(XCB) -scheme BrasscribePlay-macOS -destination 'platform=macOS' test \
		-only-testing:BrasscribePlayUITests_macOS

size: project
	$(XCB) -scheme BrasscribePlay-iOS -configuration Release -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
	du -sh "$(DERIVED)/Build/Products/Release-iphoneos/BrasscribePlay.app"
