# E1 — The Library — Where Your Pickers Live

**Target:** 2–3 min
**One-line hook:** My Library grid, open/create, library folder preference

---

## Intro

Every picker you create is saved as a file in your **Library**. Think of it as your personal collection — every rig you've ever built a picker for, in one place, available in any blend file. In this video we'll cover what the library is, how to navigate it, and how to change where it's stored.

## Getting to the library

Click the **Library** icon at the top of the BGEN window — it's the middle of the three main page icons. You land on **My Library**, which is a grid of picker cards.

Each card shows a **thumbnail**, the picker's **name**, and the date it was last modified. Hover over a card and you'll see extra actions — open, rename, delete, export.

## Opening a picker

Click any card to open that picker in the editor. It becomes **linked to your current scene**, so the next time you open this blend file, BGEN loads this picker automatically.

## Creating a new picker

At the top of the library page there's a **New Picker** button — the same action as the launch dialog's Create New. Click it, give the picker a name, and it gets added to the grid.

## Deleting a picker

Right-click a card and choose **Delete**. BGEN asks for confirmation — this deletes the `.bpicker` file from your library folder, so it's gone. If you want to keep a backup first, export it somewhere else before deleting.

## Changing the library folder

By default, your library lives at `Documents/FT_Anim_Picker/Library/`. You can change that in **Settings → Preferences → Library Path**.

Use a custom path when you want to:
- **Sync with a team** — point the library at a shared Dropbox or Google Drive folder
- **Sync across machines** — same idea, personal cloud sync
- **Keep it on a fast SSD** — library reads are fast regardless, but huge libraries benefit

When you change the library path, BGEN rescans the new folder and shows whatever pickers it finds there.

## The BGEN Library sub-tab

You'll notice a second tab at the top of the library page — **BGEN Library**. That's the marketplace, where you can download pickers other creators have shared. We cover that in Series F.

## What's next

Your library is where every picker lives. Next up — how to **import, export, and convert legacy pickers** when you need to move pickers between machines or upgrade from older versions.
