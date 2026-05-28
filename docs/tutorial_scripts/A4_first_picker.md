# A4 — Creating Your First Picker

---

## Intro

Let's create our first picker. When you open BGEN Picker on a fresh scene, you'll be greeted by the **launch dialog** — three options, and we'll walk through each.

## Option 1 — Create New Picker

The first option, **Create New Picker**, is the one you'll use most. Click it and give your picker a name — usually the name of the character or rig you're building it for. Hit create, and BGEN spins up a new `.bpicker` file in your library folder with a single empty tab ready to go.

This new picker is now **linked to your current Blender scene**. Any time you open this blend file, BGEN will remember which picker belongs to it and load it automatically.

## Option 2 — Open From Library

The second option, **Open From Library**, takes you to your local library. This page shows all the picker files you have created in this directory. Click any one to open it, and that picker becomes linked to the current scene.

You can always switch which picker is linked to a scene — open a different one, and the link updates.

## Option 3 — Convert Legacy Picker

The third option only shows up if your scene has picker data from an older version of the addon. If you've been using FT Anim Picker from before the library system, your pickers used to be embedded directly inside the scene.

Clicking **Convert Legacy** pulls that embedded data out, saves it as a new `.bpicker` in your library, and links it to the current scene. You only do this once per old file — after that, the library takes over.

## Where pickers live

Your library lives in a folder on your computer. By default it's in your Documents folder under `BGEN_Picker/Library`, but you can change that path in **Settings → Preferences** if you want to sync it to Dropbox or a team share.

## What's next

Now that we have a picker open, the canvas is ready for buttons. In the next video, we'll start placing and organizing them.
