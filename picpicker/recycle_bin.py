"""Native trash operations; programmatic restore is Windows-only."""
import os
from pathlib import Path
import struct
import sys

CAN_RESTORE = sys.platform == 'win32'

if CAN_RESTORE:
    import winshell
else:
    from send2trash import send2trash


def delete_file(path):
    if CAN_RESTORE:
        winshell.delete_file(str(path), no_confirm=True, allow_undo=True)
    else:
        send2trash(str(path))


def read_index_record(data):
    """Return (original path, deletion time) from the bytes of a Recycle Bin $I file.

    Version 1 (Vista to 8.1) holds a fixed 260-character path; version 2 (Windows 10 and later)
    holds its length first. Both hold the deletion time as a FILETIME at offset 16.
    """
    version, _size, deleted = struct.unpack_from('<qqq', data, 0)
    if version == 1:
        raw = data[24:24 + 520]
    else:
        count = struct.unpack_from('<i', data, 24)[0]
        raw = data[28:28 + count * 2]
    return raw.decode('utf-16-le').split('\0', 1)[0], deleted


def _same_path(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def restore_file(path):
    """Move the newest Recycle Bin copy of `path` back to where it was deleted from.

    winshell.undelete() can't be used: it builds the original path from the item's display
    name, which has no extension when Explorer hides known extensions (Windows' default),
    so it never finds the file. The $I record beside each item holds the real path.
    """
    if not CAN_RESTORE:
        raise NotImplementedError('Restore this file manually from your system Trash.')
    target = Path(path)
    newest = None
    for item in winshell.recycle_bin():
        stored = Path(item.real_filename())
        record = stored.with_name('$I' + stored.name[2:])
        try:
            original, deleted = read_index_record(record.read_bytes())
        except (OSError, struct.error, UnicodeDecodeError):
            continue
        if _same_path(original, target) and (newest is None or deleted > newest[0]):
            newest = (deleted, stored, record)
    if newest is None:
        raise FileNotFoundError(f'{target} not found in the Recycle Bin')
    if target.exists():
        raise FileExistsError(f'{target} already exists')
    _deleted, stored, record = newest
    os.replace(stored, target)
    record.unlink(missing_ok=True)
