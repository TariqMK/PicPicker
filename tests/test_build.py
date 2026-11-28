"""The macOS app bundle must carry the release version, not PyInstaller's 0.0.0."""
from pathlib import Path
import plistlib
import tempfile
import unittest

from scripts.build import pyinstaller_command, stamp_bundle_version


class PyInstallerCommandTests(unittest.TestCase):
    def test_every_build_bundles_pillows_tk_finder(self):
        """Linux builds crashed at start-up without it (PIL imports it from C code)."""
        for system in ('win32', 'darwin', 'linux'):
            with self.subTest(system=system):
                command = pyinstaller_command(system)
                index = command.index('--hidden-import')
                self.assertEqual(command[index + 1], 'PIL._tkinter_finder')


class BundleVersionTests(unittest.TestCase):
    def test_info_plist_gets_the_release_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            plist = Path(temporary) / 'PicPicker.app' / 'Contents' / 'Info.plist'
            plist.parent.mkdir(parents=True)
            original = {'CFBundleName': 'PicPicker', 'CFBundleIdentifier': 'app.picpicker.desktop',
                        'CFBundleShortVersionString': '0.0.0'}
            plist.write_bytes(plistlib.dumps(original))
            stamp_bundle_version(plist.parent.parent, '3.1.2')
            stamped = plistlib.loads(plist.read_bytes())
            self.assertEqual(stamped['CFBundleShortVersionString'], '3.1.2')
            self.assertEqual(stamped['CFBundleVersion'], '3.1.2')
            self.assertEqual(stamped['CFBundleIdentifier'], 'app.picpicker.desktop')


if __name__ == '__main__':
    unittest.main()
