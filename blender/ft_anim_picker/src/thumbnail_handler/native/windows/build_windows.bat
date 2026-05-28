@echo off
REM ─────────────────────────────────────────────────────────────────
REM Build script for the Windows Thumbnail Handler DLL
REM
REM Prerequisites:
REM   - .NET 6.0 SDK (https://dotnet.microsoft.com/download)
REM
REM Usage:
REM   cd native\windows
REM   build_windows.bat
REM
REM Output:
REM   bin\Release\net6.0-windows\BPickerThumbnailHandler.dll
REM   bin\Release\net6.0-windows\BPickerThumbnailHandler.comhost.dll
REM ─────────────────────────────────────────────────────────────────

echo ══════════════════════════════════════════════════════════
echo   BGEN Picker – Windows Thumbnail Handler Builder
echo ══════════════════════════════════════════════════════════
echo.

where dotnet >nul 2>&1
if errorlevel 1 (
    echo ERROR: .NET SDK not found.
    echo Install from: https://dotnet.microsoft.com/download
    exit /b 1
)

echo Building thumbnail handler DLL...
dotnet build -c Release

if errorlevel 1 (
    echo.
    echo BUILD FAILED.
    exit /b 1
)

echo.
echo Build succeeded!
echo.
echo Output: bin\Release\net6.0-windows\BPickerThumbnailHandler.comhost.dll
echo.
echo To register (run as Administrator):
echo   regsvr32 "%CD%\bin\Release\net6.0-windows\BPickerThumbnailHandler.comhost.dll"
echo.
echo To unregister:
echo   regsvr32 /u "%CD%\bin\Release\net6.0-windows\BPickerThumbnailHandler.comhost.dll"
echo.
echo NOTE: The current Python-only approach (windows_handler.py) provides
echo static icon registration without this DLL.  This native handler adds
echo dynamic per-file thumbnails in Explorer.
