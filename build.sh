#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
xcrun swiftc -O pointerd.swift -o pointerd \
  -framework Network -framework CoreGraphics -framework ApplicationServices
xcrun swiftc -O viewer.swift -o viewer -framework WebKit -framework Cocoa
print "built: ./pointerd ./viewer"
