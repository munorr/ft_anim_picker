# A3 — The BGEN Picker Interface — A Quick Tour

---

## Intro

Before we start building, let's walk through the interface so you know where everything lives. It's laid out simply once you see it.

## The three main pages

Along the top you'll see three icon buttons. These switch between the three main pages of BGEN Picker.

The first is the **Editor** — this is where you actually build and use your pickers. The second is the **Library**, where all your saved pickers live, plus the marketplace for downloading pickers other people have shared. The third is **Settings**, for your account, preferences, and updates.

Most of your time is spent on the Editor page, so let's focus there.

## The canvas

The big empty area in the middle is the canvas. Think of it as an infinite grid where you place buttons. You can pan by holding **Alt and left-click dragging**, or middle-click dragging. Zoom is on the scroll wheel.

## The HUD

Up in the top-right corner of the canvas is the HUD — the heads-up display. It shows a button count, your selection, and has a **reset view** button for when you've zoomed somewhere weird. You can collapse it if it's in your way.

## The tab bar

Just above the canvas on the left is the tab bar. Every picker file can have multiple tabs — one for the body, one for the face, one for props, whatever you want. Hit the **plus** to add a new tab, and drag tabs to reorder.

Each tab has its own namespace dropdown. This is how the picker knows which rig in your scene to target — important when you have multiple characters.

## The top menus

Along the very top are three dropdown menus: **File** for saving and exporting, **Edit** for toggling edit mode and display options, and **Info** for documentation and updates.

## Edit mode

The most important toggle in the whole app is **Edit Mode**. You can hit **Tab** to toggle it, or use the Edit menu. When edit mode is on, the edit panel slides in from the right — that's where you style your buttons — and transform guides appear around any button you select. When edit mode is off, buttons do their job: select rigs, run scripts, apply poses.

## That's the tour

That's the whole interface. Three pages, a canvas with a HUD, tabs, and an edit panel that comes in and out. In the next video, we'll actually create our first picker.
