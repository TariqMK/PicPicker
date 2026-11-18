"""The macOS app bundle must carry the release version, not PyInstaller's 0.0.0."""
from pathlib import Path
import plistlib
import tempfile
import unittest

from scripts.build import stamp_bundle_version


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
