BIN := bin/brasscribe-capture

$(BIN): Sources/main.swift Info.plist
	mkdir -p bin
	swiftc -O -o $@ Sources/main.swift -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker Info.plist
	codesign -s - -f $@

clean:
	rm -rf bin
