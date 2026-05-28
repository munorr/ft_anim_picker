# C4 — Pose Mode — Capturing & Applying Poses

**Target:** 4–5 min
**One-line hook:** Storing single-frame and animation ranges, replace/merge/add

---

## Intro

Pose Mode turns a picker button into a **pose library**. Click the button, and a stored pose gets applied to your rig. It works for single-frame poses like "T-pose" or "A-pose", and for full animation ranges like "walk cycle" or "wave". In this video we'll cover three levels of pose mode — the basics, driving animation ranges, and mirroring across multiple rigs.

---

## Level 1 — Beginner: Capturing a Single Pose

Let's start simple. Add a new button and set its mode to **Pose**. You'll notice the button automatically resizes taller — Pose buttons show a thumbnail of the pose, so they need a bit more vertical room.

In the edit panel, click **Capture Pose**. BGEN reads the current transform on every bone of your active armature and stores it in the button. It also snaps a thumbnail of the viewport so you can see at a glance what pose this button represents.

Exit Edit Mode, move your rig into a different position, then click your pose button. Every bone snaps back to the stored pose. That's the core of Pose Mode.

A few things to know:
- Pose buttons store bone rotations, locations, and scales — everything you need to reconstruct the pose.
- The pose is stored **relative to the armature's namespace**, so it'll apply correctly to any rig with matching bone names.

---

## Level 2 — Intermediate: Animation Ranges and Apply Modes

A single-frame pose is one thing, but Pose Mode can also store **entire animation clips**.

With Edit Mode on, in the pose button's edit panel, set a **frame range** — start frame and end frame — before hitting Capture Pose. BGEN walks through that range, sampling every keyframe on every bone, and stores the whole clip.

When you click the button, the entire animation gets applied to your rig at the current playhead position. Instant walk cycle drop-in.

### Apply modes

Pose Mode has **three apply modes**, triggered by click modifiers:

- **Click alone** — **Replace mode**. Clears any existing keyframes in the target range and drops in the stored animation.
- **Shift + Click** — **Merge mode**. Keeps your existing keyframes on bones that weren't in the stored pose. Use this when you want to layer a new pose on top without wiping your work.
- **Ctrl + Click** — **Add mode**. Additive blend. The stored pose is added on top of the current pose, so corrective layers and offsets work naturally.

These modifiers make a single pose button useful in completely different ways depending on how you click it.

---

## Level 3 — Advanced: Mirroring and Multi-Rig Workflows

Now the really powerful stuff.

### Mirroring — Alt + Click

Hold **Alt** while clicking a pose button, and BGEN mirrors the pose across the rig's centerline. Left-hand wave becomes right-hand wave — no extra button needed. The mirror logic handles `.L` / `.R` and `_Left` / `_Right` naming conventions automatically.

### Multi-rig support

Because pose data is keyed to an **armature namespace**, a single pose button can be reused across any rig in your scene that follows the same naming convention. Set the tab's namespace to the rig you want to target, click the button, and the pose flows to that rig.

This means your pose library travels with your picker, not your blend file. Build it once, use it on every character.

### A production tip

When building a pose library for a show, organize poses by category using multiple tabs: one for facial, one for body idle poses, one for action poses. Within each tab, use button color to communicate the pose family — red for combat, blue for idle, yellow for transitions. Animators pick the right pose at a glance without reading labels.

---

## That's Pose Mode

From one-click T-pose buttons up to full mirrored animation libraries — that's the whole range. Next up, **Controller Mode** — turning picker buttons into interactive sliders.
