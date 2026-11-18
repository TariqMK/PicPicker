"""Build and archive only the application, never working-directory data."""
import argparse
import os
import platform
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from picpicker.version import __version__


def stamp_bundle_version(app, version):
    """Write the release version into the .app's Info.plist (PyInstaller leaves 0.0.0)."""
    plist = Path(app) / 'Contents' / 'Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info['CFBundleShortVersionString'] = version
    info['CFBundleVersion'] = version
    plist.write_bytes(plistlib.dumps(info))


def resign_bundle(app):
    """Changing Info.plist breaks the ad-hoc signature, so sign the bundle again and check it."""
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=['windows-x64', 'macos-arm64', 'linux-x64'], required=True)
    args = parser.parse_args()
    if args.platform == 'macos-arm64' and platform.machine().lower() != 'arm64':
        raise RuntimeError('macOS builds must run natively on Apple Silicon')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--onedir', '--windowed', '--name', 'PicPicker',
               '--collect-all', 'pillow_heif', '--collect-all', 'rawpy']
    # File icons for the exe and the .app. Linux executables have none; the window icon is
    # embedded in the package (picpicker/app_icon.py).
    icons = ROOT / 'assets' / 'icon'
    if sys.platform == 'win32':
        command += ['--icon', str(icons / 'picpicker.ico')]
    elif sys.platform == 'darwin':
        command += ['--icon', str(icons / 'picpicker.icns')]
    if sys.platform == 'darwin':
        command += ['--target-architecture', 'arm64', '--osx-bundle-identifier', 'app.picpicker.desktop']
    command += [str(ROOT / 'PicPicker.py')]
    environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / 'build' / 'pyinstaller-cache'))
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    if sys.platform == 'darwin' and not list((ROOT / 'dist' / 'PicPicker.app' / 'Contents' /
                                              'Resources').glob('*.icns')):
        raise RuntimeError('The macOS app bundle has no icon (.icns)')
    if sys.platform == 'darwin':
        app = ROOT / 'dist' / 'PicPicker.app'
        stamp_bundle_version(app, __version__)
        resign_bundle(app)
    # A frozen smoke-test does not create a window or read/write personal data.
    executable = ROOT / 'dist' / 'PicPicker' / ('PicPicker.exe' if sys.platform == 'win32' else 'PicPicker')
    subprocess.run([str(executable), '--version'], check=True, timeout=60)
    output = ROOT / 'release-assets'
    output.mkdir(exist_ok=True)
    name = str(output / f'PicPicker-v{__version__}-{args.platform}')
    if sys.platform == 'darwin':
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(ROOT / 'dist' / 'PicPicker.app'), name + '.zip'], check=True)
    elif sys.platform == 'win32':
        shutil.make_archive(name, 'zip', root_dir=ROOT / 'dist', base_dir='PicPicker')
    else:
        shutil.make_archive(name, 'gztar', root_dir=ROOT / 'dist', base_dir='PicPicker')


if __name__ == '__main__':
    main()
