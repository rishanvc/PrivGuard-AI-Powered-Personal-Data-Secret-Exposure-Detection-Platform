"""Filename and relative-path safety (NFR-012). Runs WITHOUT Django."""

import unittest

from privguard_engine.intake import UnsafePath, display_name, safe_relative_path


class DisplayNameTests(unittest.TestCase):
    def test_directories_are_stripped_and_absolute_paths_never_kept(self):
        self.assertEqual(display_name("C:\\Users\\alice\\secret.txt"), "secret.txt")
        self.assertEqual(display_name("../../etc/passwd"), "passwd")
        self.assertEqual(display_name("/home/alice/notes.md"), "notes.md")

    def test_bidi_override_spoofing_is_removed(self):
        spoofed = "invoice\u202efdp.exe"  # displays as "invoiceexe.pdf"
        self.assertEqual(display_name(spoofed), "invoicefdp.exe")  # the real .exe is now visible

    def test_control_characters_are_removed(self):
        self.assertEqual(display_name("report\x00\x07\x1b.pdf"), "report.pdf")

    def test_zero_width_non_joiner_is_preserved(self):
        # Persian needs U+200C to render this word correctly.
        persian = "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645.txt"
        self.assertEqual(display_name(persian), persian)

    def test_empty_or_dot_names_become_unnamed(self):
        for raw in ("", ".", "..", "\u202e", "folder/"):
            with self.subTest(raw=raw):
                self.assertEqual(display_name(raw), "unnamed")

    def test_long_names_are_truncated_keeping_the_extension(self):
        name = display_name("a" * 300 + ".pdf")
        self.assertEqual(len(name), 255)
        self.assertTrue(name.endswith(".pdf"))


class SafeRelativePathTests(unittest.TestCase):
    def test_normal_paths_are_normalised(self):
        cases = {
            "src/config/.env": "src/config/.env",
            "src\\app\\main.py": "src/app/main.py",
            "./docs//readme.md": "docs/readme.md",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(safe_relative_path(raw), expected)

    def test_unsafe_paths_are_rejected(self):
        cases = [
            "../secret.txt",            # traversal
            "a/../../b.txt",            # traversal mid-path
            "/etc/passwd",              # absolute
            "//server/share/x.txt",     # UNC
            "C:/Windows/system.ini",    # drive letter
            "c:secret.txt",             # drive-relative (Windows)
            "a/\x00/b.txt",             # NUL byte
            ".\u202e./secret.txt",      # becomes ".." once the bidi control is removed
            "a/\u202e/b.txt",           # component that is only an invisible character
            "",                         # empty
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(UnsafePath):
                    safe_relative_path(raw)

    def test_depth_and_length_limits(self):
        with self.assertRaises(UnsafePath):
            safe_relative_path("/".join(["d"] * 65) + "/f.txt")
        with self.assertRaises(UnsafePath):
            safe_relative_path("x" * 300 + "/f.txt")


if __name__ == "__main__":
    unittest.main()
