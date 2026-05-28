/*
 BPicker Thumbnail Handler – Windows Shell Extension (IThumbnailProvider)

 This is a COM component that provides dynamic thumbnails for .bpicker files
 in Windows Explorer.  It reads cache/preview.png from the ZIP archive and
 composites the BGEN logo badge in the bottom-right corner.

 FUTURE USE: This file is source code for a native Windows thumbnail handler.
 To use it:

 1. Build as a .NET class library DLL:
      dotnet build -c Release

 2. Register the COM server (requires admin once):
      regasm /codebase BPickerThumbnailHandler.dll

 3. The Python auto-installer (windows_handler.py) would register the DLL
    instead of the current registry-only approach.

 Build:
   dotnet new classlib -n BPickerThumbnailHandler
   # Replace Class1.cs with this file
   # Add NuGet: System.Drawing.Common, System.IO.Compression
   dotnet build -c Release
*/

using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;


namespace BGenPicker
{
    /// <summary>
    /// COM-visible thumbnail provider for .bpicker files.
    /// Implements IThumbnailProvider and IInitializeWithStream.
    /// </summary>
    [ComVisible(true)]
    [Guid("B6E3F2A1-9D4C-4E8B-A1F7-3C5D8E2B4A90")]
    [ClassInterface(ClassInterfaceType.None)]
    public class BPickerThumbnailHandler : IThumbnailProvider, IInitializeWithStream
    {
        private IStream _stream;
        private static readonly string BadgePath;
        private static readonly string FallbackIconPath;

        static BPickerThumbnailHandler()
        {
            // Look for badge and fallback icon next to the DLL
            string dllDir = Path.GetDirectoryName(
                System.Reflection.Assembly.GetExecutingAssembly().Location
            ) ?? "";
            BadgePath = Path.Combine(dllDir, "bgen_badge.png");
            FallbackIconPath = Path.Combine(dllDir, "bpicker_file_icon.png");
        }

        public void Initialize(IStream pstream, uint grfMode)
        {
            _stream = pstream;
        }

        public void GetThumbnail(uint cx, out IntPtr phbmp, out uint pdwAlpha)
        {
            phbmp = IntPtr.Zero;
            pdwAlpha = 0; // WTSAT_ARGB

            try
            {
                int size = (int)cx;

                // Read the stream into a MemoryStream
                byte[] zipBytes = ReadStream(_stream);
                if (zipBytes == null || zipBytes.Length == 0)
                    return;

                // Extract preview from ZIP
                Bitmap preview = ExtractPreview(zipBytes);

                // Use fallback if no preview
                if (preview == null && File.Exists(FallbackIconPath))
                {
                    preview = new Bitmap(FallbackIconPath);
                }

                if (preview == null)
                    return;

                // Create the composited thumbnail
                using (Bitmap output = new Bitmap(size, size, PixelFormat.Format32bppArgb))
                using (Graphics g = Graphics.FromImage(output))
                {
                    g.SmoothingMode = SmoothingMode.HighQuality;
                    g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                    g.CompositingQuality = CompositingQuality.HighQuality;

                    // Draw rounded-rect clipped preview
                    float cornerRadius = size * 0.08f;
                    using (GraphicsPath clipPath = RoundedRect(
                        new RectangleF(0, 0, size, size), cornerRadius))
                    {
                        g.SetClip(clipPath);
                        g.DrawImage(preview, 0, 0, size, size);
                        g.ResetClip();

                        // Subtle border
                        using (Pen borderPen = new Pen(Color.FromArgb(40, 0, 0, 0), 1.5f))
                        {
                            g.DrawPath(borderPen, clipPath);
                        }
                    }

                    // Badge in bottom-right
                    if (File.Exists(BadgePath))
                    {
                        using (Bitmap badge = new Bitmap(BadgePath))
                        {
                            int badgeSize = (int)(size * 0.22f);
                            int margin = (int)(size * 0.04f);
                            int bx = size - badgeSize - margin;
                            int by = size - badgeSize - margin;

                            // Dark circle background
                            float bgPad = badgeSize * 0.15f;
                            RectangleF bgRect = new RectangleF(
                                bx - bgPad, by - bgPad,
                                badgeSize + bgPad * 2, badgeSize + bgPad * 2
                            );
                            using (SolidBrush bgBrush = new SolidBrush(
                                Color.FromArgb(200, 30, 30, 30)))
                            {
                                g.FillEllipse(bgBrush, bgRect);
                            }

                            g.DrawImage(badge, bx, by, badgeSize, badgeSize);
                        }
                    }

                    // Return the HBITMAP
                    phbmp = output.GetHbitmap(Color.Transparent);
                    pdwAlpha = 2; // WTSAT_ARGB
                }

                preview.Dispose();
            }
            catch
            {
                // Silently fail – Explorer will show default icon
            }
        }

        private static Bitmap ExtractPreview(byte[] zipBytes)
        {
            try
            {
                using (MemoryStream ms = new MemoryStream(zipBytes))
                using (ZipArchive archive = new ZipArchive(ms, ZipArchiveMode.Read))
                {
                    ZipArchiveEntry entry = archive.GetEntry("cache/preview.png");
                    if (entry == null)
                        return null;

                    using (Stream entryStream = entry.Open())
                    using (MemoryStream imgMs = new MemoryStream())
                    {
                        entryStream.CopyTo(imgMs);
                        imgMs.Position = 0;
                        return new Bitmap(imgMs);
                    }
                }
            }
            catch
            {
                return null;
            }
        }

        private static byte[] ReadStream(IStream stream)
        {
            // Read COM IStream into byte array
            const int chunkSize = 8192;
            using (MemoryStream ms = new MemoryStream())
            {
                byte[] buffer = new byte[chunkSize];
                while (true)
                {
                    IntPtr bytesReadPtr = Marshal.AllocCoTaskMem(sizeof(int));
                    try
                    {
                        stream.Read(buffer, chunkSize, bytesReadPtr);
                        int bytesRead = Marshal.ReadInt32(bytesReadPtr);
                        if (bytesRead <= 0) break;
                        ms.Write(buffer, 0, bytesRead);
                    }
                    finally
                    {
                        Marshal.FreeCoTaskMem(bytesReadPtr);
                    }
                }
                return ms.ToArray();
            }
        }

        private static GraphicsPath RoundedRect(RectangleF rect, float radius)
        {
            float diameter = radius * 2;
            GraphicsPath path = new GraphicsPath();
            path.AddArc(rect.X, rect.Y, diameter, diameter, 180, 90);
            path.AddArc(rect.Right - diameter, rect.Y, diameter, diameter, 270, 90);
            path.AddArc(rect.Right - diameter, rect.Bottom - diameter, diameter, diameter, 0, 90);
            path.AddArc(rect.X, rect.Bottom - diameter, diameter, diameter, 90, 90);
            path.CloseFigure();
            return path;
        }
    }

    // ─── COM Interfaces ─────────────────────────────────────────────────

    [ComImport]
    [Guid("e357fccd-a995-4576-b01f-234630154e96")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IThumbnailProvider
    {
        void GetThumbnail(uint cx, out IntPtr phbmp, out uint pdwAlpha);
    }

    [ComImport]
    [Guid("b824b49d-22ac-4161-ac8a-9916e8fa3f7f")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IInitializeWithStream
    {
        void Initialize(IStream pstream, uint grfMode);
    }
}


/*
 Registry entries needed (auto-generated by regasm, or add manually):

 HKEY_CLASSES_ROOT\.bpicker\ShellEx\{e357fccd-a995-4576-b01f-234630154e96}
   (Default) = {B6E3F2A1-9D4C-4E8B-A1F7-3C5D8E2B4A90}

 HKEY_CLASSES_ROOT\CLSID\{B6E3F2A1-9D4C-4E8B-A1F7-3C5D8E2B4A90}
   (Default) = BGen Picker Thumbnail Handler
   \InprocServer32
     (Default) = mscoree.dll
     ThreadingModel = Both
     Assembly = BPickerThumbnailHandler, ...
     Class = BGenPicker.BPickerThumbnailHandler
     CodeBase = file:///path/to/BPickerThumbnailHandler.dll
*/
