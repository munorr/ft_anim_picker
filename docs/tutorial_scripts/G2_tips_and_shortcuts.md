# G2 — Tips, Gotchas, and Power-User Shortcuts

**Target:** 3–4 min
**One-line hook:** Fade Away, Minimal Mode, hidden keyboard shortcuts

---

## Intro

You've got the full picture of BGEN Picker now. This last video is a grab bag of **power-user features, hidden shortcuts, and gotchas** that aren't critical to starting out but will make you faster and smoother once you know them.

## Fade Away mode

Under **Edit → Fade Away** is a toggle that makes the BGEN window **semi-transparent when your mouse isn't over it**. Hover the picker and it's fully opaque; move away to the viewport and it fades. Great for dense monitor setups where you want the picker accessible but not blocking your rig.

## Minimal mode

**Edit → Minimal Mode** hides the top toolbar and menu bar, leaving just the canvas and tabs. When you're heads-down animating, minimal mode gives you more vertical space. Toggle back off the same way.

## Keyboard shortcut cheat sheet

Here's every shortcut that isn't immediately obvious:

**Edit Mode**
- `Tab` — toggle edit mode
- `Shift + A` — add rectangular button at cursor
- `Shift + C` — add curve button at cursor
- `Delete` / `Backspace` — delete selected buttons
- `Ctrl + C` / `Ctrl + V` — copy / paste
- `Ctrl + Shift + V` — mirror-paste

**Alignment**
- `Ctrl + ←/→/↑/↓` — align to edge
- `Shift + ←/→/↑/↓` — center on axis
- `Ctrl + Shift + ←/→/↑/↓` — distribute evenly

**Canvas**
- `Alt + LMB drag` or `MMB drag` — pan
- `Scroll` — zoom
- `Ctrl + Scroll` — fine zoom

**Button Interaction**
- `Shift + click` — add to selection
- `Ctrl + click` — toggle selection (or Merge for Pose Mode)
- `Alt + click` — counterpart action (select or pose)
- `Double-click` — controller input overlay
- `Shift + double-click` — apply input to all selected controllers

## Gotchas

### Selectable: Off doesn't protect from deletion

Marking a button non-selectable in an animator workflow hides it from clicks — but in Edit Mode, you can still select and delete it. If you're building a picker for someone else, the Selectable flag is just a runtime lock, not a permanent safeguard.

### Legacy JSON is one-way

Importing a legacy `.json` picker converts it to `.bpicker`. But you **can't export back to JSON**. If you need to stay in the old format for some reason, keep your original `.json` somewhere safe before importing.

### Mirror relies on naming

Mirror-paste only works when your rig follows a consistent naming convention — `.L`/`.R`, `_Left`/`_Right`, or `_l`/`_r`. If one bone is named differently from its counterparts, that button won't mirror correctly. A five-minute rig rename pays for itself many times over.

### Script errors go to the system console

On Windows, if a Script Mode button isn't doing anything when clicked, open **Window → Toggle System Console** before clicking. The error prints there. On Mac and Linux, launch Blender from the terminal to see errors inline.

## Power-user workflow — Fade Away + Minimal Mode

My personal go-to setup while animating: **Fade Away on**, **Minimal Mode on**, picker docked to a second monitor or off to the side. The picker is always within a quick mouse swing but never in the way. Your mileage may vary — experiment until the panel disappears from your conscious attention and the rig stays front-and-center.

## That's the series

Every feature, every mode, every shortcut — you've seen it all now. The best next step is to **build a picker for a rig you actually use**. Pick a character, open BGEN, and start placing buttons. Nothing teaches a tool like a real project.

Thanks for watching. If you build something cool, share it on the Marketplace — I'd love to see what the community makes.
