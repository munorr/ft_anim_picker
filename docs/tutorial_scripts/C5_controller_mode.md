# C5 — Controller Mode — Sliders & Omni-Controllers

**Target:** 3–4 min
**One-line hook:** XY fields, single-axis, live drag, Shift+double-click apply-to-all

---

## Intro

So far every button we've built is click-and-react. **Controller Mode** is different — a controller button is a live, interactive **slider**. Drag it, and a rig property updates in real time. Great for facial controls, corrective shape keys, or any continuous property you'd rather not punch numbers into.

In this video we'll cover three levels — a single-axis slider, an XY field, and batch apply across multiple controllers.

---

## Level 1 — Beginner: A Single-Axis Slider

Add a new button and switch its mode to **Controller**. The edit panel shows a **Controller Target** section where you link the button to a rig property.

Click **Pick Property**, then in Blender right-click any property — a bone's rotation, a shape key value, a custom property, anything — and choose **Copy Data Path**. Paste that path into the picker, and BGEN wires it up.

Set the **axis** to **Single**, and define a **min** and **max** value — say 0 and 1 for a shape key, or -90 and 90 for a bone rotation.

Exit Edit Mode, click and drag the button horizontally. The property updates as you drag. Release, and the value locks in. Perfect, continuous control without touching the N-panel.

---

## Level 2 — Intermediate: XY Fields and Live Feedback

A single slider drives one value. An **XY controller** drives two — horizontal and vertical — at the same time.

Switch the axis mode to **XY** and wire a second property to the Y axis. Now dragging the button in 2D space updates both values simultaneously. This is perfect for facial controls: one button that drives both a smile shape key on X and a frown on Y. Drag up-right for a big smile with squint, down-left for a frown.

The button renders a **crosshair** showing the current value, so you get visual feedback as you drag.

### Typing exact values

If you need to dial in an exact number, **double-click** the controller button. A small input overlay pops up — type the value, hit enter, and the property snaps to that exact number. Much faster than dragging when you know what you want.

---

## Level 3 — Advanced: Batch Apply Across Multiple Controllers

Here's the power move. Select multiple controller buttons — all your facial shape key controllers, for instance — and double-click one to open the input overlay. Normally the typed value applies to just that one button.

Hold **Shift while double-clicking**, and the value applies to **every selected controller at once**. This is how you reset an entire face rig to neutral in one action — select everything, Shift-double-click one, type zero, enter. Done.

### A production workflow

- Build a facial picker where every expression control is a controller button.
- Use color to group them: blue for eye controls, green for mouth, yellow for brow.
- Select all of one color, Shift-double-click, type zero — that family resets to neutral.
- Copy the neutral state as a pose button for one-click reset.

---

## That's Controller Mode

Select Mode picks. Script Mode runs code. Toggle Mode switches. Pose Mode applies. Controller Mode **adjusts**. Together they cover just about anything an animator needs from a picker.

Next up we leave the button modes behind and talk about organizing your work — starting with multi-tab pickers.
