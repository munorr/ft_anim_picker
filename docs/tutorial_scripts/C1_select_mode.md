# C1 — Select Mode — Selecting Rig Controls

**Target:** 3–4 min
**One-line hook:** Click/Shift/Alt modifiers, namespaces, counterpart selection

---

## Intro

Select Mode is what you'll use 90% of the time. A Select Mode button's only job is to select objects or bones in your scene when you click it — no scripts, no poses, just selection. Let's go through how to set one up, and then the modifier keys that make it powerful.

## Assigning objects to a button

With Edit Mode on, select a button. In the edit panel, switch the mode segment to **Select**. You'll see an **assignment panel** open up, listing what this button targets.

Now go into Blender's viewport and select the bones or objects you want the button to control. Back in the picker, hit the **plus** button on the assignment panel, and those selected items get linked to the picker button.

You can assign one bone per button, or many. Every item in the list becomes part of the selection when the button is clicked.

## Exiting Edit Mode to test

Turn Edit Mode off — **Tab** — and click your button. The assigned bones or objects light up in the viewport. That's Select Mode doing its job.

## The modifier keys

Select Mode respects modifier keys for how the selection is applied:

- **Click** alone — replaces your current selection with this button's targets.
- **Shift + Click** — adds this button's targets to your current selection, so you can click a chain of buttons to build up a big selection.
- **Ctrl + Click** — toggles the selection. If the targets are already selected, they get deselected.

## Namespaces — the multi-character trick

Here's where it gets interesting. Each picker tab has a **namespace dropdown** at the top. If you have two of the same rig in the scene — say, a main hero and his clone — the namespace lets you point this tab at one or the other.

When you set a namespace, BGEN rewrites the button's target paths through that namespace at click time. So one tab can be reused across any rig that follows the same naming convention — just change the namespace, and every button retargets.

## Counterpart selection — Alt + Click

The last trick is **counterpart selection**. Hold **Alt** and click a Select Mode button, and BGEN automatically finds the mirror version of that bone — the `.L` becomes `.R`, `_Left` becomes `_Right`, and so on — and selects that instead.

This means you don't have to build two buttons for every finger. Build the left hand once, and Alt+click each button to select the right hand equivalent.

## A quick tip

If you want a button to be **visible but not clickable** — like a label or a decoration — set its mode to Select but leave the assignment list empty, or toggle **Selectable** off in the edit panel.

## What's next

Select Mode is the foundation. Next video, **Script Mode** — what to do when you need a button to run Python code, not just select things.
