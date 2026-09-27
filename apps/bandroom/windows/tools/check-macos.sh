#!/bin/sh
# Everything of Brasscribe Bandroom for Windows that builds and runs off Windows: the Core tests and a
# C# type-check of the app. The XAML compile, PRI and the app itself need Windows (.github/workflows/windows.yml).
set -eu
cd "$(dirname "$0")/.."
: "${DOTNET_ROOT:=/opt/homebrew/opt/dotnet/libexec}"
export DOTNET_ROOT

dotnet test tests/Brasscribe.Bandroom.Core.Tests
dotnet build tools/CodeBehindCheck -p:Platform=x64 -p:AppxGeneratePriEnabled=false
