# Pribambase
Pribambase is a helper tool to ease and speed up lowpoly pixel textured, or 2.5D pixel art workflow. It links Aseprite and Blender editors, and handles a lot of repetitive manual operations which otherwise constitute a large and unexciting portion of the process.

* Paint in Aseprite with instant viewport feedback in Blender. No need to save or export files.
* Display UV map in Aseprite, which updates as you change the model.
* Shortcuts for setting up world grids, pixel materials, and 2D sprites in the scene.
* Sprite animation rig allows to directly control the frame of the animation, play entire animation, or separate tags. Works with common blender animation and NLA. Now support tag repeats and looping (Ase 1.3+).
* Optionally maintain 2.5D sprite sheets and animations for Armory game engine, which runs on top of Blender.
* Experimental node setups for separate layers that allow painting several maps in the same document.

## What Happened
Pribambase's creator abandoned the project due to its scope and time requirements. Please do not harass them for this choice. This is here to continue the work made on the plugin and offer a path forward that will both keep this plugin free and available as well as give it the opportunity to mature. 

## Installation
Stable Version:
Looking to add Pribambase to your workflow? download your prefered version here!
* [Pribambase Archive](https://www.illusionofmana.art/Pribambase.html).

Experimental:
* Download the source here as a zip and install it on Blender 3.x as an add-on

## Links
Via Lampysprites (original creator) NOTE: These links may be dead please refer to the next section for further information

* [How Do I...](https://github.com/lampysprites/pribambase/wiki/How-Do-I...) tutorials and advice.
* [RSS feed](https://lampysprites.itch.io/pribambase/devlog.rss) to track updates without checking this or that app.
* [Itchio community](https://lampysprites.itch.io/pribambase/community) to show off your work or ask for help.

Known Working Links:

* [Archived Page](https://www.illusionofmana.art/Pribambase.html) Simple "how to" and download links
* [How To's](https://www.youtube.com/watch?v=70wyQhKyxFw) The original "how to" video on Pribambase setup and use
* [My Experience](https://www.youtube.com/watch?v=6ikqAwPJ8nQ) My breakdown and experience using the program (this may demonstrate bugs no longer existing in the plugin)

## Contact
Please reach out to me via illusionofmana@gmail.com

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

## Acknowledgments
- David Capello did a significant part of the work on inter-processing API for Aseprite
- Async handling (async_loop.py) is based on [Blender Cloud Addon](https://cloud.blender.org/services)
