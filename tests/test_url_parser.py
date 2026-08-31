import unittest
from app.utils.url_parser import extract_public_id, is_valid_linkedin_url, normalize_url


class TestUrlParser(unittest.TestCase):
    def test_extract_public_id_standard(self):
        self.assertEqual(extract_public_id("https://www.linkedin.com/in/williamhgates"), "williamhgates")
        self.assertEqual(extract_public_id("https://www.linkedin.com/in/williamhgates/"), "williamhgates")
        self.assertEqual(extract_public_id("https://linkedin.com/in/williamhgates?trk=123"), "williamhgates")

    def test_extract_public_id_regional(self):
        self.assertEqual(extract_public_id("https://in.linkedin.com/in/jatinbhatt"), "jatinbhatt")
        self.assertEqual(extract_public_id("https://uk.linkedin.com/in/john-doe-123/"), "john-doe-123")
        self.assertEqual(extract_public_id("https://ca.linkedin.com/in/jane_smith"), "jane_smith")

    def test_invalid_urls(self):
        self.assertIsNone(extract_public_id("https://google.com"))
        self.assertIsNone(extract_public_id("https://linkedin.com/feed/"))
        self.assertIsNone(extract_public_id(""))
        self.assertFalse(is_valid_linkedin_url("invalid_url"))

    def test_normalize_url(self):
        self.assertEqual(normalize_url("https://in.linkedin.com/in/jatinbhatt/"), "https://www.linkedin.com/in/jatinbhatt")


if __name__ == "__main__":
    unittest.main()
