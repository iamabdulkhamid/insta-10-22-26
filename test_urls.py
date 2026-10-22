import unittest
from instagram_urls import get_instagram_url


class InstagramURLTests(unittest.TestCase):
    def test_reel_with_igsh(self):
        self.assertEqual(
            get_instagram_url("Mana link: https://www.instagram.com/reel/ABC_123/?igsh=foo"),
            "https://www.instagram.com/reel/ABC_123/",
        )

    def test_post_trailing_punctuation(self):
        self.assertEqual(
            get_instagram_url("https://instagram.com/p/AbC987/!"),
            "https://www.instagram.com/p/AbC987/",
        )

    def test_reject_noninstagram(self):
        self.assertIsNone(get_instagram_url("https://www.instagram.com.evil.example/reel/AbC/"))

    def test_reject_profile(self):
        self.assertIsNone(get_instagram_url("https://www.instagram.com/example_user/"))

    def test_reject_invalid_shortcode(self):
        self.assertIsNone(get_instagram_url("https://instagram.com/reel/A%2FB/"))

    def test_reels_alias(self):
        self.assertEqual(
            get_instagram_url("https://m.instagram.com/reels/Reel001/"),
            "https://www.instagram.com/reel/Reel001/",
        )


if __name__ == "__main__":
    unittest.main()
