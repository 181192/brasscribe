BIN := bin/brasscribe-capture
export DEVELOPER_DIR ?= /Applications/Xcode.app/Contents/Developer

# The Info.plist (NSAudioCaptureUsageDescription) is embedded in the executable so the
# privacy prompt can name the tool.
$(BIN): Package.swift Info.plist $(wildcard Sources/*/*.swift)
	swift build -c release --product brasscribe-capture \
	  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker $(CURDIR)/Info.plist
	mkdir -p bin
	cp "$$(swift build -c release --show-bin-path)/brasscribe-capture" $@
	codesign -s - -f $@

test:
	swift test

clean:
	rm -rf bin .build
