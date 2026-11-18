"""The toolbar shortens step by step only as far as it must to fit the window."""
import unittest

from picpicker.ui import compact_level

# Measured on macOS with On This Day on: every label shown needs 1189 px.
# Steps: Random Day as an icon, hide the app name, Open Folder… as an icon.
REQUIRED = 1189
SAVINGS = [104, 71, 106]


class CompactLevelTest(unittest.TestCase):
    def test_wide_window_keeps_every_label(self):
        self.assertEqual(compact_level(REQUIRED, 1200, SAVINGS), 0)
        self.assertEqual(compact_level(REQUIRED, REQUIRED, SAVINGS), 0)

    def test_default_window_with_on_this_day_shortens_random_day_only(self):
        # The 1180 px default window leaves 1148 px; before the fix Random Day was cut off here.
        self.assertEqual(compact_level(REQUIRED, 1148, SAVINGS), 1)

    def test_steps_are_added_in_order_until_it_fits(self):
        self.assertEqual(compact_level(REQUIRED, REQUIRED - 104, SAVINGS), 1)
        self.assertEqual(compact_level(REQUIRED, REQUIRED - 105, SAVINGS), 2)
        self.assertEqual(compact_level(REQUIRED, REQUIRED - 175, SAVINGS), 2)
        self.assertEqual(compact_level(REQUIRED, REQUIRED - 176, SAVINGS), 3)

    def test_minimum_window_fits_with_every_step(self):
        # The 980 px minimum window leaves 948 px.
        level = compact_level(REQUIRED, 948, SAVINGS)
        self.assertEqual(level, 3)
        self.assertLessEqual(REQUIRED - sum(SAVINGS[:level]), 948)

    def test_uses_every_step_when_still_too_narrow(self):
        self.assertEqual(compact_level(REQUIRED, 500, SAVINGS), 3)

    def test_no_steps_available(self):
        self.assertEqual(compact_level(REQUIRED, 900, []), 0)


if __name__ == '__main__':
    unittest.main()
