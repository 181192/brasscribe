# Brasscribe Bandroom for macOS (the menu-bar app that runs the engine).
#   make project   generate BrasscribeBandroom.xcodeproj with XcodeGen
#   make build     build the app (Debug) into build/DerivedData
#   make test      BandroomKit unit tests
#   make strings   rebuild App/Localizable.xcstrings from the last build (en + nb)
#   make run       build, then run against a checkout: CHECKOUT=/path/to/brasscribe make run
export DEVELOPER_DIR ?= /Applications/Xcode.app/Contents/Developer
DERIVED := build/DerivedData
XCB := xcodebuild -project BrasscribeBandroom.xcodeproj -derivedDataPath $(DERIVED)
APP := $(DERIVED)/Build/Products/Debug/Brasscribe Bandroom.app
CHECKOUT ?= $(abspath ../../..)

.PHONY: project build test strings run

project:
	xcodegen generate

build: project
	$(XCB) -scheme BrasscribeBandroom -destination 'platform=macOS' build

test:
	./scripts/test-kit.sh

strings: build
	python3 scripts/make-strings.py $(DERIVED)/Build/Intermediates.noindex

run: build
	BRASSCRIBE_CHECKOUT="$(CHECKOUT)" "$(APP)/Contents/MacOS/Brasscribe Bandroom"
