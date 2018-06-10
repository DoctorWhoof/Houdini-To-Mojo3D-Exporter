# Houdini-To-Mojo3D-Exporter
A Python exporter that converts a Simple Houdini Scene to a .mojo3d file.

## Warning!

Very experimental! Many features missing, and generally feels very fragile (not a lot of safety checks). Expect the compiled Monkey2 code loading the generated files to crash a lot. Make sure you have Debug build on, and let me know which problems you run into so that I can improve it.

## Installation
The exporter consists of a single Python script. You can launch it inside Houdini in any way you prefer, but the recommended is copying/pasting the script into a Shelf tool. When you create a new shelf tool, simply go to the "Script" tab and add these lines:
```
execfile("/Path/mojo3d_export.py")
export()
```
Replace "Path" with the path to the script file in your filesystem.

## Houdini nodes supported

Basic attibutes:
- Name.
- Material (multiple materials per object not supported yet).
- Local transform matrix.

Primitive geometry:
 - Box.
 - Sphere (Set primitive type to polygon mesh for accurate export).
 - Tube (exports as Cylinder, but if top radius is zero exports as cone).
 - Torus.
 
 Lights:
 - Point, Spot and Directional lights only
 - Ambient light is supported, but not accurate (Houdini's Ambient light looks terrible!).
 - Environment lights are exported as both SkyTexture and Envtexture.
 - Attenuation export is not accurate yet.
 
 Camera:
 - Near, far and FOV supported
 
 Models:
 - File nodes are supported in two ways:
    - When writing, the written file is loaded in mojo3d without hierarchy ("Model.Load").
    - If loading, any "sibling" nodes with file nodes are ignored, and the model is loaded with hierarchy ("Model.LoadBoned").
 - Materials can be overriden if the "Collapse hierarchy on load" option is On.
  
