#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
# Build script for the macOS Quick Look Thumbnail Extension
#
# Prerequisites:
#   - Xcode Command Line Tools (xcode-select --install)
#   - ZIPFoundation Swift package (https://github.com/weichsel/ZIPFoundation)
#
# This script creates a minimal .app bundle containing the Thumbnail
# Extension (.appex).  The resulting app can be shipped with the addon
# and auto-installed by macos_handler.py.
#
# Usage:
#   cd native/macos
#   ./build_macos.sh
#
# Output:
#   build/BGenPickerThumbnail.app
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
APP_NAME="BGenPickerThumbnail"
APP_PATH="${BUILD_DIR}/${APP_NAME}.app"
ICONS_DIR="${SCRIPT_DIR}/../../bgen_picker_icons"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  BGEN Picker – macOS Thumbnail Extension Builder        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check for Xcode
if ! command -v xcodebuild &> /dev/null; then
    echo "ERROR: Xcode Command Line Tools not found."
    echo "Install with: xcode-select --install"
    exit 1
fi

echo "NOTE: Building the Thumbnail Extension requires an Xcode project."
echo ""
echo "To create the Xcode project:"
echo "  1. Open Xcode → File → New → Project"
echo "  2. Choose macOS → App"
echo "  3. Name it '${APP_NAME}'"
echo "  4. Add a new target: File → New → Target → Thumbnail Extension"
echo "  5. Copy ThumbnailProvider.swift into the extension target"
echo "  6. Add ZIPFoundation via Swift Package Manager"
echo "  7. Configure the extension's Info.plist with UTI 'com.bgen.bpicker'"
echo "  8. Add bgen_badge.png and bpicker_file_icon.png to the extension bundle"
echo "  9. Build: xcodebuild -project ${APP_NAME}.xcodeproj -scheme ${APP_NAME} -configuration Release"
echo ""
echo "The current Python-only approach (macos_handler.py) works without this"
echo "native extension.  This is for future enhancement to provide true"
echo "dynamic thumbnails in Finder for ALL .bpicker files (including ones"
echo "not saved from the tool)."
echo ""

# For now, just create the stub .app that registers the UTI
# (This is what macos_handler.py already does at runtime)
echo "Creating UTI registration stub app..."

rm -rf "${APP_PATH}"
mkdir -p "${APP_PATH}/Contents/MacOS"
mkdir -p "${APP_PATH}/Contents/Resources"

# Create stub executable
cat > "${APP_PATH}/Contents/MacOS/${APP_NAME}" << 'STUB'
#!/bin/sh
exit 0
STUB
chmod +x "${APP_PATH}/Contents/MacOS/${APP_NAME}"

# Convert icon to ICNS
if [ -f "${ICONS_DIR}/bpicker_file_icon.png" ]; then
    ICONSET="${BUILD_DIR}/bpicker.iconset"
    mkdir -p "${ICONSET}"

    for size in 16 32 64 128 256 512; do
        sips -z $size $size "${ICONS_DIR}/bpicker_file_icon.png" \
             --out "${ICONSET}/icon_${size}x${size}.png" 2>/dev/null
        size2=$((size * 2))
        if [ $size2 -le 1024 ]; then
            sips -z $size2 $size2 "${ICONS_DIR}/bpicker_file_icon.png" \
                 --out "${ICONSET}/icon_${size}x${size}@2x.png" 2>/dev/null
        fi
    done

    iconutil -c icns "${ICONSET}" -o "${APP_PATH}/Contents/Resources/bpicker.icns" 2>/dev/null || \
        sips -s format icns "${ICONS_DIR}/bpicker_file_icon.png" \
             --out "${APP_PATH}/Contents/Resources/bpicker.icns" 2>/dev/null

    rm -rf "${ICONSET}"
    echo "  ✓ Icon converted to ICNS"
fi

# Write Info.plist
cat > "${APP_PATH}/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.bgen.picker.filetype</string>
    <key>CFBundleName</key>
    <string>BGEN Picker File Type</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>BGenPickerThumbnail</string>
    <key>CFBundleIconFile</key>
    <string>bpicker</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>LSBackgroundOnly</key>
    <true/>
    <key>UTExportedTypeDeclarations</key>
    <array>
        <dict>
            <key>UTTypeIdentifier</key>
            <string>com.bgen.bpicker</string>
            <key>UTTypeDescription</key>
            <string>BGEN Picker File</string>
            <key>UTTypeConformsTo</key>
            <array>
                <string>public.data</string>
                <string>public.composite-content</string>
            </array>
            <key>UTTypeIconFiles</key>
            <array>
                <string>bpicker.icns</string>
            </array>
            <key>UTTypeTagSpecification</key>
            <dict>
                <key>public.filename-extension</key>
                <array>
                    <string>bpicker</string>
                </array>
            </dict>
        </dict>
    </array>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeExtensions</key>
            <array>
                <string>bpicker</string>
            </array>
            <key>CFBundleTypeIconFile</key>
            <string>bpicker</string>
            <key>CFBundleTypeName</key>
            <string>BGEN Picker File</string>
            <key>CFBundleTypeRole</key>
            <string>Viewer</string>
            <key>LSHandlerRank</key>
            <string>Owner</string>
            <key>LSItemContentTypes</key>
            <array>
                <string>com.bgen.bpicker</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
PLIST

echo "  ✓ Info.plist written"
echo ""
echo "Stub app created at: ${APP_PATH}"
echo ""
echo "To register with macOS:"
echo "  /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f '${APP_PATH}'"
