"""Verify trash routing without deleting any files."""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class TrashTests(unittest.TestCase):
    def load_backend(self, platform, modules):
        spec = importlib.util.spec_from_file_location('trash_test_backend', Path(__file__).resolve().parents[1] / 'picpicker' / 'recycle_bin.py')
        backend = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'platform', platform), patch.dict(sys.modules, modules):
            spec.loader.exec_module(backend)
        return backend

    def test_windows_deletes_to_recycle_bin(self):
        shell = SimpleNamespace(delete_file=Mock())
        backend = self.load_backend('win32', {'winshell': shell})
        backend.delete_file('synthetic.jpg')
        shell.delete_file.assert_called_once_with('synthetic.jpg', no_confirm=True, allow_undo=True)
        self.assertTrue(backend.CAN_RESTORE)

    @staticmethod
    def index_record(original, deleted, version=2):
        """Bytes of a Recycle Bin $I file, in the layout Windows writes."""
        header = struct.pack('<qqq', version, 4, deleted)
        if version == 1:
            return header + original.encode('utf-16-le').ljust(520, b'\0')
        path = (original + '\0').encode('utf-16-le')
        return header + struct.pack('<i', len(path) // 2) + path

    def test_index_record_reads_both_versions(self):
        backend = self.load_backend('linux', {'send2trash': SimpleNamespace(send2trash=Mock())})
        for version in (1, 2):
            with self.subTest(version=version):
                data = self.index_record(r'C:\Photos\IMG_2.png', 1234, version)
                self.assertEqual(backend.read_index_record(data), (r'C:\Photos\IMG_2.png', 1234))

    def test_windows_restore_finds_file_when_extensions_are_hidden(self):
        """Explorer hides known extensions by default, so the item's display name is IMG_2."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            photos, bin_folder = root / 'photos', root / 'bin'
            photos.mkdir(), bin_folder.mkdir()
            target = photos / 'IMG_2.png'
            items = []
            for name, deleted, content in (('$RAAAAAA.png', 100, b'older'), ('$RBBBBBB.png', 200, b'newer'),
                                           ('$RCCCCCC.png', 300, b'other')):
                (bin_folder / name).write_bytes(content)
                original = target if content != b'other' else photos / 'IMG_3.png'
                (bin_folder / ('$I' + name[2:])).write_bytes(self.index_record(str(original), deleted))
                items.append(SimpleNamespace(real_filename=lambda n=name: str(bin_folder / n),
                                             original_filename=lambda: str(photos / 'IMG_2')))
            shell = SimpleNamespace(delete_file=Mock(), recycle_bin=lambda: items)
            backend = self.load_backend('win32', {'winshell': shell})
            backend.restore_file(target)
            self.assertEqual(target.read_bytes(), b'newer')
            self.assertFalse((bin_folder / '$RBBBBBB.png').exists())
            self.assertFalse((bin_folder / '$IBBBBBB.png').exists())
            self.assertTrue((bin_folder / '$RAAAAAA.png').exists())
            self.assertTrue((bin_folder / '$RCCCCCC.png').exists())

    def test_windows_restore_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'IMG_2.png'
            target.write_bytes(b'current')
            (root / '$RAAAAAA.png').write_bytes(b'deleted')
            (root / '$IAAAAAA.png').write_bytes(self.index_record(str(target), 1))
            items = [SimpleNamespace(real_filename=lambda: str(root / '$RAAAAAA.png'))]
            backend = self.load_backend('win32', {'winshell': SimpleNamespace(recycle_bin=lambda: items)})
            with self.assertRaises(FileExistsError):
                backend.restore_file(target)
            self.assertEqual(target.read_bytes(), b'current')
            self.assertTrue((root / '$RAAAAAA.png').exists())

    def test_windows_restore_reports_missing_file(self):
        backend = self.load_backend('win32', {'winshell': SimpleNamespace(recycle_bin=lambda: [])})
        with self.assertRaises(FileNotFoundError):
            backend.restore_file('missing.jpg')

    def test_macos_and_linux_use_trash_without_windows_import(self):
        for platform in ('darwin', 'linux'):
            with self.subTest(platform=platform):
                trash = Mock()
                backend = self.load_backend(platform, {'send2trash': SimpleNamespace(send2trash=trash), 'winshell': None})
                backend.delete_file('synthetic.jpg')
                trash.assert_called_once_with('synthetic.jpg')
                self.assertFalse(backend.CAN_RESTORE)
                with self.assertRaises(NotImplementedError):
                    backend.restore_file('synthetic.jpg')
