# D1 — Multi-Tab Pickers — One File, Many Pages

**Target:** 2–3 min
**One-line hook:** Add tabs, drag to reorder, per-tab namespace

---

## Intro

A big character rig can have hundreds of controls — body, face, fingers, props, accessories. Cramming them all onto one canvas gets messy fast. That's why BGEN supports **tabs** — multiple pages inside the same picker file, each with its own canvas.

## Adding a tab

Look at the tab bar along the top of the canvas. You'll see your current tab — probably called "Tab 1" — and a small **plus** button next to it. Click the plus to add a new tab. Give it a name — "Face", "Body", "Hands" — whatever fits.

The new tab opens with an empty canvas. Every button you add goes on that tab and stays on that tab.

## Switching between tabs

Just click a tab name to switch. Each tab remembers its own pan and zoom position, so if you're zoomed into the face rig on the Face tab, switching to Body and back brings you right back to where you left off.

## Reordering tabs

Drag a tab left or right to reorder. Build your tabs in the order you want animators to see them — usually top-down body workflow, so Body first, then Face, then Props.

## Renaming and deleting

Right-click any tab to rename or delete it. Deleted tabs are gone — but like everything else in BGEN, **Ctrl+Z** undoes it.

## The namespace dropdown

This is the tab's secret weapon. Each tab has a **namespace dropdown** that picks which rig in the scene this tab targets. If you have a main character and a prop character in the same scene, Tab 1 can target the main rig, Tab 2 can target the prop, and every button on each tab resolves to the right armature automatically.

This also means the **same picker file can drive different rigs** just by changing the namespace. Reusable across a whole show.

## A production tip

Build one master picker per rig archetype — humanoid, quadruped, face-only — and reuse them across every character that shares the archetype. Namespaces handle the routing. You don't need a separate picker per character.

## What's next

Tabs keep your work organized. Next video, **canvas customization** — background images, grid, and visual tweaks that make your picker easier to read.
