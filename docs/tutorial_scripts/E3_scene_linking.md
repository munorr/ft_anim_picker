# E3 — Scene Linking — Tying a Picker to a Blend File

**Target:** 2 min
**One-line hook:** BGENPickerLink, UUID, switching which picker a scene uses

---

## Intro

When you open a blend file, how does BGEN know which picker to load? That's the job of **scene linking**. In this short video we'll cover what the link is, how it's created, and how to switch which picker a scene uses.

## What is the link?

Every `.bpicker` in your library has a unique ID — a **UUID** that doesn't change even if you rename the picker. When you open a picker in a particular blend file, BGEN writes that UUID into the scene's custom properties under the key `BGENPickerLink`.

Next time you open that blend file, BGEN reads the UUID, looks it up in your library, and loads the matching picker automatically.

## Seeing the link

If you're curious, you can inspect it in Blender — **Properties Panel → Scene → Custom Properties**. You'll see `BGENPickerLink` as a custom property with the picker's UUID as its value. You don't need to touch this manually — BGEN manages it — but it's useful to know it's there.

## Switching which picker is linked

Open a different picker from your library, and BGEN overwrites the scene link with the new picker's UUID. So switching is as easy as going to the library and opening a different card.

## Multiple rigs, one blend file

If your blend file has multiple rigs — a crowd scene, a two-character shot — you can still only link **one picker per scene**. But that one picker can have **multiple tabs**, each targeting a different rig via namespace. So in practice, a crowd scene gets a single "Cast" picker with one tab per character.

## Portability

Because the link is just a UUID, sharing works like this:
- You send both the blend file and the `.bpicker` to a teammate
- They import the `.bpicker` into their library
- They open the blend file — BGEN resolves the UUID and loads the picker automatically

If the UUID isn't in their library, BGEN prompts them to import the missing `.bpicker` or pick a different one.

## A quick tip

If you ever see a "picker not found" warning when opening a scene, it just means the linked `.bpicker` isn't in your library. Either import it, or open any picker to overwrite the link.

## What's next

That wraps the Library series. Next up, **the BGEN account and marketplace** — signing in, downloading pickers from other creators, and eventually selling your own.
