# C2 — Script Mode — Running Python from a Button

**Target:** 3–4 min
**One-line hook:** Script Manager basics, namespace tokens

---

## Intro

Select Mode handles selection, but sometimes you need a button to actually **do** something — reset a rig to its default pose, toggle a visibility layer, bake an animation. That's what **Script Mode** is for. A Script Mode button runs Python code when clicked.

## Switching to Script Mode

Select a button, turn Edit Mode on, and in the edit panel switch the mode segment from Select to **Script**. The assignment panel disappears and a **Script Manager** button takes its place.

## The Script Manager

Click **Script Manager** and a window pops up with a **code editor** and a mode segment at the top. The mode segment has two options: **Python** and **Toggle**. We're on Python — that's a single script that runs on every click.

Type or paste any Python code into the editor. It runs in Blender's main Python context, so you have full access to `bpy`, your scene, selected objects, everything.

A simple example — this hides the currently selected object:

```python
import bpy
for obj in bpy.context.selected_objects:
    obj.hide_viewport = True
```

Save, close the script manager, exit edit mode, and click the button. Your selection gets hidden.

## Namespace tokens

Here's the BGEN-specific part. If your script needs to reference the rig's armature or namespace, you can use **tokens** that get replaced at runtime:

- **`$NAMESPACE`** — replaced with whatever the current tab's namespace is set to.
- **`$ARMATURE`** — replaced with the active armature for this tab.
- **`$OBJ_NAME`** — replaced with the first name in the button's own assignment list.

So a script like this:

```python
bpy.data.objects["$NAMESPACE:Root"].location = (0, 0, 0)
```

…would work for any rig you point the namespace at. One script, infinite rigs.

## Debugging

If your script errors out, Blender prints the traceback to the system console. On Windows, open **Window → Toggle System Console** before clicking the button, and you'll see exactly which line failed.

## A quick tip

For one-shot utilities, write the script directly in the script manager. For complex logic, write it as a proper function in a `.py` file and just call it from the button — way easier to maintain.

## What's next

We've covered single-shot scripts. Next up is the **Toggle** sub-mode — a two-state button that flips between two scripts. We already released a deep-dive video on toggles, link in the description.
