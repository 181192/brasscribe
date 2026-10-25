#!/bin/sh
# Everything of Brasscribe Play for Windows that builds and runs off Windows:
# core tests, the Windows audio library, the WinUI controls library, a C# type-check of the app (also as the screen
# catalogue's test host) and the tests of the catalogues' picture checks.
# The XAML compile, PRI generation and the app itself need Windows (see .github/workflows/windows.yml).
set -eu
cd "$(dirname "$0")/.."
: "${DOTNET_ROOT:=/opt/homebrew/opt/dotnet/libexec}"
export DOTNET_ROOT

dotnet test tests/Kalli.Scribe.Tests
dotnet build services/Kalli.Scribe.Audio.Windows
# MakePri.exe is a Windows tool; PRI generation is skipped off Windows.
dotnet build features/Kalli.Scribe.Controls -p:Platform=x64 -p:AppxGeneratePriEnabled=false
dotnet build tools/CodeBehindCheck -p:Platform=x64 -p:AppxGeneratePriEnabled=false
dotnet build tools/CodeBehindCheck -p:Platform=x64 -p:AppxGeneratePriEnabled=false -p:ScribeCatalogue=true
dotnet test tools/ScreenCheck.Tests
dotnet build tools/ScreenCheck
