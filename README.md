# Pribambase

**NOTE: downloading repo zip will not work in blender due to missing third party libraries. [Get it from project page](https://lampysprites.itch.io/pribambase)**

Pribambase is a helper tool to easen and speed up lowpoly pixel textured, or 2.5D pixelart workflow. It links Aseprite and Blender editors, and handles a lot of repetitive manual operations which otherwise consitute a large and unexciting portion of the process.

* Paint in Aseprite with instant viewport feedback in Blender. No need to save or export files.
* Display UV map in Aseprite, which updates as you change the model.
* Shortcuts for setting up world grids, pixel materials, and 2D sprites in the scene.
* Sprite animation rig allows to directly control the frame of the animation, play entire animation, or separate tags. Works with common blender animation and NLA. Now support tag repeats and looping (Ase 1.3+).
* Optionally maintain 2.5D spritesheets and animations for Armory game engine, which runs on top of Blender.
* Experimental node setups for separate layers that allow painting several maps in the same document.

## Links

* [How Do I...](https://github.com/lampysprites/pribambase/wiki/How-Do-I...) tutorials and advice.
* [RSS feed](https://lampysprites.itch.io/pribambase/devlog.rss) to track updates without checking this or that app.
* [Itchio community](https://lampysprites.itch.io/pribambase/community) to show off your work or ask for help.

## Source

Source for [aseprite plugin](https://github.com/aseprite/api/blob/main/api/plugin.md) is the `client/` folder. The repo root is the [blender plugin](https://docs.blender.org/manual/en/latest/advanced/scripting/addon_tutorial.html#install-the-add-on). For using source, you'd probably want to symlink them to extension/addon locations.

Third party python packages are bundled as wheel to allow offline installation, but aren't stored in the repo. Download them from PyPI to `thirdparty` folder, or fetch with PIP:

```shell
cd to/project/root

## for your platform
pip download -d thirdparty -r requirements.txt

## for different platforms; the platform tags tags go look up on PyPI
pip download -d thirdparty --platform win32 --only-binary=:all: -r requirements.txt
```

**NOTE: normally Blender includes its own python distribution, which might not match a separately installed version.**

## License

Although GPL license spread from some borrowed code, most of the project is MIT.

## Acknowledgements
- David Capello did a significant part of the work on interprocessing API for Aseprite
- Async handling (async_loop.py) is based on [Blender Cloud Addon](https://cloud.blender.org/services)
