# G1 — A Full Character Picker from Scratch

**Target:** 5 min
**One-line hook:** Capstone: build a real body picker end-to-end

---

## Intro

We've covered every feature in isolation. In this capstone, we'll build a **full working body picker for a character rig from scratch** — using everything we've learned in one workflow. Three levels, each a little more involved.

---

## Level 1 — The Minimum Viable Picker

Let's start as simple as possible. Open a rig, create a new picker, and name it after the character.

1. **Add a background reference**. Screenshot your rig in T-pose, drop it into the Background Image field of the canvas settings, dial opacity to 30%.
2. **Lay out the main IK controls**. `Shift + A` to drop buttons over the hands, feet, hip, chest, and head. Assign each one to the matching control bone using Select Mode. Six, maybe seven buttons.
3. **Exit Edit Mode** and test. Click each button — the bones highlight. That's a working picker already.

Two to three minutes of work, and you have something an animator can use.

---

## Level 2 — A Production-Grade Body Picker

Now let's build it properly. Back into Edit Mode.

### Add every control

Beyond the IK controls, add buttons for:
- **FK arm chain** — shoulder, elbow, wrist, per side
- **FK leg chain** — thigh, knee, ankle, per side
- **Spine** — hip, spine1, spine2, chest, neck, head
- **Clavicles** — left and right

Build the **left side only**. Then select the whole left side and **Ctrl + Shift + V** — mirror-paste gives you the right side automatically, with all the assignments retargeted.

### Style for readability

- **Color by function** — IK buttons cool blue, FK warm orange, spine red, extras gray.
- **Label sparingly** — animators don't need "Left Shoulder FK" when the position already tells them that. Short labels or none at all.
- **Align everything** — Ctrl+arrows and Ctrl+Shift+arrows until the columns and rows are clean.

### Add an IK/FK toggle

Drop a new button near each arm and set it to **Script → Toggle**. State 1 is IK (visible IK buttons, invisible FK), State 2 is FK (vice versa). This is the exact workflow from our Toggle Buttons deep-dive video.

### Add a "select all" utility

One more button — Select Mode, assign every control bone on the rig to it. Animators click it to get a full rig selection in one shot.

### Test

Exit Edit Mode. Walk through every button — every control selects cleanly, IK/FK toggles visually swap which controls are active, select-all grabs everything. This is now a picker you could ship.

---

## Level 3 — Multi-Tab, Multi-Rig, Production-Ready

Now let's level up one more time.

### Split into tabs

Rename the current tab **Body**. Add two more tabs: **Face** and **Hands**.

**Face tab:**
- Background image of the head close-up, 30% opacity
- Controller Mode buttons for the major shape keys — smile, frown, brow, eyes
- Pose Mode buttons for common expressions — happy, sad, angry, surprised — captured from the rig

**Hands tab:**
- Background of the hands splayed
- Buttons per finger joint, mirror-pasted from left to right
- Pose Mode buttons for common hand poses — fist, point, open, peace sign

### Namespace for multi-rig reuse

On each tab, set the namespace to the current rig. If you drop this picker into a scene with a second character with the same rig architecture, you can duplicate the tabs and change the namespace on each duplicate — one picker, both rigs.

### Polish

- Add a **Selectable: Off** label at the top of each tab — a button with no assignment, just text like "BODY" or "FACE", as a visual section header.
- Set per-tab background images so each tab feels distinct.
- Export the finished picker from **File → Export Picker**, and send it to your animation team.

### Share it

If your picker is good, consider publishing it to the Marketplace. Other animators using the same rig will buy it, and you'll have built a passive income source from a single weekend of work.

---

## That's a full picker

You now know everything BGEN can do. Final video — **tips, gotchas, and power-user shortcuts** — is the last one in the series.
