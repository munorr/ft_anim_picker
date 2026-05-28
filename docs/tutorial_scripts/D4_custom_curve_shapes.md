# D4 — Custom Curve Shapes

**Target:** 3–4 min
**One-line hook:** Curve editor — drawing non-rect buttons

---

## Intro

Rectangles and rounded rectangles cover most cases, but sometimes you need a button shaped like an arrow, a star, a foot outline, or a free-form spline. BGEN's **curve editor** lets you draw any shape you want and turn it into a clickable button.

## Adding a curve button

With Edit Mode on, hit **Shift + C** — that's the shortcut for a new curve button. A small placeholder shape appears, and the **curve editor panel** opens.

You can also right-click on the canvas and choose **Add Curve Button** — same result.

## The curve editor

The curve editor is a mini vector editor. You have a small canvas showing the current shape, and tools to modify it:

- **Add point** — click inside the shape to drop a new control point.
- **Delete point** — select a point and hit Delete.
- **Drag points** — click and drag any point to reshape the curve.
- **Bezier handles** — each point has optional handles for smooth curves. Toggle them on to bend the line between two points.

Close the shape to make it fill — open shapes render as lines, closed shapes render filled.

## Preset shapes

Below the editor are a few **preset shapes** you can start from — arrows, circles, diamonds, hexagons. Pick the closest match to what you want, then edit from there. Much faster than drawing from scratch.

## Styling a curve button

Once you're happy with the shape, close the curve editor. The button now has your custom shape — and every normal appearance control still works. Color, label, opacity, rotation, selection highlight, all of it. The curve just replaces the rectangle.

Mode still works too — a curve button can be Select, Script, Toggle, Pose, or Controller. Shape doesn't change what the button does.

## A practical example — a foot button

For a foot IK controller, rectangles feel wrong. Make a curve button that's roughly the **outline of a foot** — heel, arch, toes — assign it to the foot IK bone, and now the button shape matches the body part. Animators see a foot and click a foot. Intuitive.

## A quick tip

Curve buttons stay crisp at any zoom level because the shape is stored as vectors, not pixels. So a detailed custom shape looks just as clean when the canvas is scaled down as when it's zoomed all the way in.

## What's next

That wraps up organization and visual customization. Next series covers the **Library** — saving, loading, sharing, and converting pickers.
