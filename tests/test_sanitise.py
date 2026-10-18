import unittest

from aura.sanitise import sanitise_html


class TestSanitiseHtml(unittest.TestCase):
    def test_keeps_allowed_markup(self):
        out = sanitise_html("<h2>Top</h2><p>A <strong>bold</strong> claim</p><ul><li>x</li></ul>")
        self.assertEqual(out, "<h2>Top</h2><p>A <strong>bold</strong> claim</p><ul><li>x</li></ul>")

    def test_drops_script_and_content(self):
        out = sanitise_html("<p>hi</p><script>alert(1)</script>")
        self.assertEqual(out, "<p>hi</p>")

    def test_strips_event_handlers_and_unknown_tags(self):
        out = sanitise_html('<img src=x onerror="alert(1)"><p onclick="x()">t</p>')
        self.assertNotIn("onerror", out)
        self.assertNotIn("onclick", out)
        self.assertNotIn("<img", out)
        self.assertIn("<p>t</p>", out)

    def test_blocks_javascript_urls(self):
        out = sanitise_html('<a href="javascript:alert(1)">x</a>')
        self.assertNotIn("javascript", out)
        self.assertEqual(out, "<a>x</a>")

    def test_allows_https_links_with_rel(self):
        out = sanitise_html('<a href="https://arxiv.org/abs/1">x</a>')
        self.assertIn('href="https://arxiv.org/abs/1"', out)
        self.assertIn("noopener", out)

    def test_escapes_stray_text(self):
        self.assertEqual(sanitise_html("a < b & c"), "a &lt; b &amp; c")

    def test_empty(self):
        self.assertEqual(sanitise_html(None), "")
        self.assertEqual(sanitise_html(""), "")


if __name__ == "__main__":
    unittest.main()
