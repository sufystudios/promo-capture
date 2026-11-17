#!/bin/sh
# Builds macwinrec (needs Xcode command line tools; macOS 15+ to run).
# The first recording asks for Screen Recording permission for your terminal app.
set -e
cd "$(dirname "$0")"
swiftc -O macwinrec.swift -o macwinrec
echo "built $(pwd)/macwinrec"
