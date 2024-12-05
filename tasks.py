import sys
import os
import re
import shutil as sh
from microbuild.microbuild import task,ignore,build

butler_exe = "\"C:\\Program Files\\butler\\butler.exe\""
pip_exe = "\"C:\\Program Files\\Blender Foundation\\Blender 3.6\\3.6\\python\\bin\\python.exe\" -m pip"
project_root = os.path.dirname(__file__)
client_dir = os.path.join(project_root, "client")

# version
version = None

def in_build(sub=""):
    return os.path.join(project_root, "build", sub)

@task()
def version():
    """Assert that the version is set correctly"""
    print("Version (major): 2")
    minor = input("Version (minor): ").strip()
    patch = input("Version (patch): ").strip()
    
    with open(os.path.join(project_root, "__init__.py"), "r") as init_py:
        for line in init_py:
            match = re.match('\s*"version":\s*\(2,\s*(\d+),\s*(\d+)', line)
            if match:
                minr, ptc = match.groups()
                assert minr == minor and ptc == patch
                break
    
    with open(os.path.join(client_dir, "package.json"), "r") as package_json:
        for line in package_json:
            match = re.match('\s*"version":\s*"2\.(\d+)\.(\d+)', line)
            if match:
                minr, ptc = match.groups()
                assert minr == minor and ptc == patch
                break
    
    global version
    version = minor, patch

@task()
def clean():
    """Clean build directory"""
    if os.path.exists(in_build()):
        sh.rmtree(in_build())

@task()
def mkdir():
    """Ensure build directory exists"""
    if not os.path.isdir(in_build()):
        os.mkdir(in_build())

@task(mkdir)
def ase():
    """Zip ase extension"""
    temp_dir = in_build("ase")
    sh.copytree(client_dir, temp_dir, ignore=sh.ignore_patterns("__*"))
    sh.copy(os.path.join(project_root, "README.md") , temp_dir)
    sh.copy(os.path.join(project_root, "COPYING") , temp_dir)
    sh.make_archive(in_build("pribambase_aseprite"), format="zip", root_dir=temp_dir)
    sh.rmtree(temp_dir)

def addon_base(dir_suffix, platform_tag):
    dest_dir = os.path.join(in_build("pribambase_blender_" + dir_suffix))
    thirdparty_dir = os.path.join(dest_dir, "pribambase", "thirdparty")
    requirements = os.path.join(project_root, "requirements.txt")
    if os.path.isdir(dest_dir):
        sh.rmtree(dest_dir)
    sh.copytree(project_root, os.path.join(dest_dir, "pribambase"), ignore=lambda dir, files : [f for f in files if not re.match(".+\.py$|README|COPYING|messaging", f)])
    sh.copytree(os.path.join(project_root, "aseprite"), os.path.join(dest_dir, "pribambase", "aseprite"))
    sh.copytree(os.path.join(project_root, "scripts"), os.path.join(dest_dir, "pribambase", "scripts"))
    sh.copy(in_build("pribambase_aseprite.zip"), os.path.join(dest_dir, "pribambase", "aseprite", "pribambase_aseprite.aseprite-extension"))
    os.system(f"{pip_exe} download -d {thirdparty_dir} --platform {platform_tag} --only-binary=:all: -r {requirements}")

@task(mkdir)
def win64():
    """Bundle addon for windows 64-bit"""
    addon_base("windows", "win_amd64")

@task(mkdir)
def win32():
    """Bundle addon for windows 32-bit"""
    addon_base("windows_32bit", "win32")

@task(mkdir)
def osx():
    """Bundle addon for macs (multiarch)"""
    addon_base("osx", "macosx_10_9_universal2")

@task(mkdir)
def linux86():
    """Bundle addon for linux 64-bit"""
    addon_base("linux_x64", "manylinux2010_x86_64")

@task(mkdir)
def linux64():
    """Bundle addon for linux 32-bit"""
    addon_base("linux_i686", "manylinux2010_i686")

@task(win32, win64, osx, linux86, linux64)
def all_os():
    """Bundle addon for every OS"""
    pass

@task(version)
def upload():
    def butler(source, channel):
        os.system(f"{butler_exe} push {in_build(source)} lampysprites/pribambase:{channel} --userversion 2.{version[0]}.{version[1]}")

    butler("pribambase_aseprite.aseprite-extension", "aseprite")
    butler("pribambase_blender_windows", "blender-windows")
    butler("pribambase_blender_windows_32bit", "blender-windows-32bit")
    butler("pribambase_blender_osx", "blender-osx")
    butler("pribambase_blender_linux_x64", "blender-linux")
    butler("pribambase_blender_linux_i686", "blender-linux-i686")

@task(clean, ase, all_os, upload)
def all():
    pass
    
if __name__ == "__main__":
    build(sys.modules[__name__],sys.argv[1:])