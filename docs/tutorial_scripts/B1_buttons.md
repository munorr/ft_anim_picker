# B1 — Working with Picker Buttons

---

## Intro

Quick framing before we dive in: BGEN splits button work into two modes. **Edit Mode** is where you shape the look and layout — adding buttons, placing them, coloring them, resizing them, rotating them. **User Mode** — edit mode off — is where those buttons actually do their job, running selects, scripts, and poses.

Everything in this video is layout and appearance work, so hit **Tab** to turn Edit Mode on before we start.

## Placing and arranging

The fastest way to add a single button is **Shift+A** — it drops one at your cursor. Right-clicking empty canvas opens a menu with **Add Button** plus a few other ways to create buttons.

The big time-saver is **Create Buttons from Selection**. Select a group of rig controls in the viewport first — bones in Blender, controls in Maya — then right-click the canvas. The menu shows the live count of whatever you've got selected. Click it, and you drop into drag-to-place mode. Drag in the direction you want the buttons laid out and you'll see ghost previews along a line — the drag snaps to 0°, 90°, and 180° so rows come out clean, and **Alt** disables the snap if you want a free angle. Hold **Shift** during the drag to arrange them in a grid instead of a line. Release to commit. Every button comes pre-labeled with its control's name and already wired to select that target.

If you only had one thing selected, there's nothing to lay out — the button just drops under your cursor, no drag needed.

The same menu also has **Draw Custom Shape** and **Create Button from Curve** for non-rectangular buttons — we cover those in the custom shapes video.

To move a button, click and drag. Hold **Shift** and click to add more buttons to your selection, or left-click-drag on empty canvas to draw a selection area. **Ctrl+C** and **Ctrl+V** copy and paste like anywhere else, and **Ctrl+Shift+V** is **mirror-paste** — it flips the copied buttons across the canvas centerline. That's the fastest way to build the right side of a symmetric rig after you've done the left.

**Delete** or **Backspace** removes what's selected, and **Ctrl+Z** undoes anything — the picker keeps its own undo stack.

## Styling a button

The button segment of the edit panel and the hover widget contains most of what you need to visualy update the the style of your button:

- **Color** — pick any color, or use one of the 30 quick swatches below. Color semantically — warm tones for FK, cool for IK, red for root, yellow for fingers. Consistency is how animators read a picker without thinking.

- **Label** — to edit button text just double-click the button and type in the label you want. You can format the text further with bold, italic, underline, and a separate text color. Leave it blank for shape-only buttons.

- **Dimensions** — width and height fields, plus a proportional lock for keeping a specific ratio while you scale.

- **Corner radius** — rounds the edges. Sliding to the max creates a pill shape and you can click the button here to individually edit each corner of the button.

- **Rotation** — spins the button from -180 to +180 degrees and you can reset the rotaion by clicking this button.

- **Opacity** — fades a button down. Handy for stacking buttons or overlaying on a background image.

Everything here works on multi-selection too. Select a bunch of buttons, change the color, and all the buttons updates.

## Aligning and distributing

The edit panel has buttons to align a group of selected picker buttons in different directions and to also evenly space out the buttons. Select 2 or more and click.

Everything in that grid also has a **keyboard shortcut** for when you don't want to reach for the mouse:

- **Ctrl + arrow** aligns the group to the edge in the direction of the the arrow — Ctrl+Left pulls everything to the leftmost button's edge, Ctrl+Up to the topmost, and so on.

- **Shift + arrow** centers along that axis.

- **Ctrl + Shift + arrow** distributes evenly, so the gap between each button is identical.


Just below the alignment grid are **z-order** controls for moving buttons behind or in front of others, and **Horizontal / Vertical Mirror** buttons for flipping a selection across its own center — handy when you've got one side of a layout built and want to mirror it in place.

## Transform guides

The edit panel is great for numeric changes, but sometimes you just want to grab a button and squash or spin it. Whenever you have a button selected in Edit Mode, a bounding box with **eight handles** appears — four corners, four edges. You can use these guides to intuiatively place your buttons how you want.

## What's next

That's the full toolkit for building, styling, and laying out buttons. Next up, we dive into **Select Mode** — the first of the button modes, and the one you'll use most.
