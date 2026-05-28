# D3 — Mirroring & Counterpart Objects

**Target:** 3 min
**One-line hook:** How L/R mirroring resolves counterparts

---

## Intro

Most character rigs are symmetric — a left arm and a right arm, a left leg and a right leg, left and right fingers. Building every button twice is tedious. BGEN has a **counterpart system** that handles mirroring automatically. In this video we'll cover how to set it up and use it.

## The naming convention

Counterparts rely on a **consistent naming convention** on your rig. BGEN recognizes these automatically:
- `.L` ↔ `.R` (Blender's default)
- `_Left` ↔ `_Right`
- `_l` ↔ `_r`

If your rig uses one of these, you're already set. If not, you can define custom counterpart pairs manually per button — we'll cover that in a second.

## Mirror-paste — the fast way to build both sides

The simplest counterpart workflow is **mirror-paste**. Build the left arm picker — all the shoulder, elbow, wrist, and finger buttons. Select them all, **Ctrl + C** to copy, and **Ctrl + Shift + V** to mirror-paste.

BGEN drops copies of every button on the opposite side of the canvas centerline and **automatically rewrites every assignment** — the left-hand buttons become right-hand buttons, the `.L` suffixes become `.R`, and so on. One paste operation, and you have a mirrored rig picker.

## Alt-click counterpart selection

Even without building mirrored buttons, Select Mode supports **Alt + Click**. Hold Alt and click any Select button, and BGEN looks up the counterpart version of each target and selects that instead.

So you can ship a picker with just the left side built, and animators hold Alt to hit the right side. Half the buttons, full coverage.

## Manual counterpart assignment

If your rig doesn't follow a standard naming convention, you can assign counterparts manually. In the edit panel's assignment section, each target has a small **counterpart field** next to it. Type in the exact counterpart object name — `HandL_ctrl` paired with `HandR_ctrl`, say — and the mirror and Alt+click features will use that mapping.

## Pose mirroring

This all extends to Pose Mode. A pose captured on the left side of the rig can be **Alt + clicked** to mirror-apply it to the right side. Wave pose built for the left hand becomes a wave pose for the right hand, automatically.

## A quick tip

Before mirror-pasting a large selection, **sanity-check your rig's naming**. One inconsistent bone — a lowercase `hand_L` instead of `Hand.L` — and the mirror breaks for that specific button. Fixing the rig's naming convention pays off immediately here.

## What's next

Next video — **custom curve shapes**. When a rectangle just doesn't cut it, BGEN has a built-in curve editor for drawing any shape you want.
