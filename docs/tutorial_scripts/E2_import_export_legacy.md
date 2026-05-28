# E2 — Importing, Exporting, and Converting Legacy Pickers

**Target:** 3 min
**One-line hook:** .bpicker archive, legacy JSON, per-tab export

---

## Intro

Your library is local to your machine. Sooner or later you'll want to **send a picker to a colleague**, **receive one from a rigger**, or **pull in an old picker** from before BGEN had a library. In this video we cover every way to move pickers in and out.

## The .bpicker format

BGEN pickers are saved as `.bpicker` files. Under the hood, a `.bpicker` is a **ZIP archive** that contains everything the picker needs — the tab data, button configurations, background images, thumbnails, pose data, all of it. One file, fully self-contained.

This means you can email a `.bpicker` to someone and they'll get a complete working picker with no missing assets.

## Exporting a picker

From **File → Export Picker**, you can save the currently open picker to any location on disk. BGEN writes out a fresh `.bpicker` file — perfect for sending to a teammate or archiving.

You can also **export a single tab** from **File → Export Current Tab**. Useful when your picker has a Body tab and a Face tab and you only need to send the face rig to a facial animator.

## Importing a picker

Two paths for importing:

1. **File → Import Picker** — browse to any `.bpicker` on disk. BGEN asks whether you want to **merge** its tabs into your current picker, or **open it as a new picker** added to your library.
2. **Drag and drop** — drag a `.bpicker` file onto the BGEN window and you get the same merge/open-as-new prompt.

## Converting legacy JSON pickers

If you used FT Anim Picker before the library system, your old pickers were `.json` files. BGEN reads them too.

From **File → Import Picker**, pick a `.json` file. BGEN converts it to the new `.bpicker` format on the fly, preserving all your buttons, tabs, and styling. It gets saved to your library as a new entry.

## Converting legacy scene-embedded data

Some even older pickers stored their data directly inside the blend file, not as a separate `.json`. If you open such a scene, BGEN detects the embedded data and the launch dialog offers a **Convert Legacy** option — one click, and the embedded data gets extracted, saved to your library as a `.bpicker`, and linked to the scene.

You do this once per old blend file. After that, it behaves like any modern BGEN picker.

## A quick tip

Before you send a picker to a colleague, **double-check the background images**. If you reference a local file outside the `.bpicker` archive, it won't travel with the file. In Edit Mode, re-browse the background image so BGEN embeds it properly, then export.

## What's next

Exporting covered. Next up — **scene linking**, the small but important system that lets BGEN remember which picker belongs to which blend file.
