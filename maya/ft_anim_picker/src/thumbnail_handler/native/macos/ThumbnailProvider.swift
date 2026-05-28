/*
 BPicker Thumbnail Extension – macOS Quick Look Thumbnail Provider

 This is a QLThumbnailProvider that generates dynamic thumbnails for
 .bpicker files in Finder.  It reads cache/preview.png from the ZIP
 archive and composites the BGEN logo badge in the bottom-right corner.

 FUTURE USE: This file is source code for a native macOS Thumbnail
 Extension.  To use it:

 1. Create an Xcode project with a "Thumbnail Extension" target.
 2. Add this file as the ThumbnailProvider.
 3. Configure the extension's Info.plist with the .bpicker UTI.
 4. Build, sign (ad-hoc or Developer ID), and ship the .appex
    inside a container .app.

 The Python auto-installer (macos_handler.py) would then install and
 register the .app instead of the current stub approach.

 Build with Xcode or:
   swiftc -framework QuickLookThumbnailing -framework Cocoa \
          -framework CoreGraphics ThumbnailProvider.swift \
          -o BPickerThumbnailProvider
*/

import Foundation
import QuickLookThumbnailing
import Cocoa
import ZIPFoundation  // External: https://github.com/weichsel/ZIPFoundation

class ThumbnailProvider: QLThumbnailProvider {

    /// Badge image (BGEN logo) – loaded once from the extension bundle.
    private lazy var badgeImage: NSImage? = {
        guard let url = Bundle.main.url(forResource: "bgen_badge", withExtension: "png") else {
            return nil
        }
        return NSImage(contentsOf: url)
    }()

    /// Fallback icon when no preview.png exists in the archive.
    private lazy var fallbackIcon: NSImage? = {
        guard let url = Bundle.main.url(forResource: "bpicker_file_icon", withExtension: "png") else {
            return nil
        }
        return NSImage(contentsOf: url)
    }()

    override func provideThumbnail(
        for request: QLFileThumbnailRequest,
        _ handler: @escaping (QLThumbnailReply?, Error?) -> Void
    ) {
        let fileURL = request.fileURL
        let maxSize = request.maximumSize
        let scale = request.scale

        // Try to extract preview.png from the .bpicker ZIP archive
        let previewImage = extractPreview(from: fileURL)

        // Use preview or fallback
        guard let baseImage = previewImage ?? fallbackIcon else {
            handler(nil, NSError(domain: "com.bgen.bpicker.thumbnail",
                                 code: 1,
                                 userInfo: [NSLocalizedDescriptionKey: "No preview available"]))
            return
        }

        let reply = QLThumbnailReply(contextSize: maxSize) { context -> Bool in
            let cgContext = context
            let size = maxSize

            // Draw base image scaled to fill
            if let cgImage = baseImage.cgImage(
                forProposedRect: nil, context: nil, hints: nil
            ) {
                let imageRect = CGRect(origin: .zero, size: size)

                // Clip to rounded rect
                let cornerRadius = min(size.width, size.height) * 0.08
                let path = CGPath(roundedRect: imageRect,
                                  cornerWidth: cornerRadius,
                                  cornerHeight: cornerRadius,
                                  transform: nil)
                cgContext.addPath(path)
                cgContext.clip()

                cgContext.draw(cgImage, in: imageRect)

                // Reset clip for badge
                cgContext.resetClip()
            }

            // Draw badge in bottom-right
            if let badge = self.badgeImage,
               let badgeCG = badge.cgImage(
                   forProposedRect: nil, context: nil, hints: nil
               ) {
                let badgeSize = min(size.width, size.height) * 0.22
                let margin = min(size.width, size.height) * 0.04
                let badgeRect = CGRect(
                    x: size.width - badgeSize - margin,
                    y: margin,  // Core Graphics: origin at bottom-left
                    width: badgeSize,
                    height: badgeSize
                )

                // Dark circle background
                let bgPadding = badgeSize * 0.15
                let bgRect = badgeRect.insetBy(dx: -bgPadding, dy: -bgPadding)
                cgContext.setFillColor(
                    CGColor(red: 0.12, green: 0.12, blue: 0.12, alpha: 0.78)
                )
                cgContext.fillEllipse(in: bgRect)

                cgContext.draw(badgeCG, in: badgeRect)
            }

            return true
        }

        handler(reply, nil)
    }

    /// Extract cache/preview.png from a .bpicker ZIP archive.
    private func extractPreview(from fileURL: URL) -> NSImage? {
        // Using ZIPFoundation for ZIP reading
        guard let archive = Archive(url: fileURL, accessMode: .read) else {
            return nil
        }

        guard let entry = archive["cache/preview.png"] else {
            return nil
        }

        var data = Data()
        do {
            _ = try archive.extract(entry) { chunk in
                data.append(chunk)
            }
        } catch {
            return nil
        }

        return NSImage(data: data)
    }
}


/*
 Info.plist keys needed for the Thumbnail Extension target:

 <key>NSExtension</key>
 <dict>
     <key>NSExtensionAttributes</key>
     <dict>
         <key>QLSupportedContentTypes</key>
         <array>
             <string>com.bgen.bpicker</string>
         </array>
         <key>QLThumbnailMinimumDimension</key>
         <integer>64</integer>
     </dict>
     <key>NSExtensionPointIdentifier</key>
     <string>com.apple.quicklook.thumbnail</string>
     <key>NSExtensionPrincipalClass</key>
     <string>$(PRODUCT_MODULE_NAME).ThumbnailProvider</string>
 </dict>
*/
