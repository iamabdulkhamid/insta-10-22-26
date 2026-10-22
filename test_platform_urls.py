import unittest
from platform_urls import allowed_modes, parse_media_url


class PlatformTests(unittest.TestCase):
    def test_instagram_reel(self):
        result = parse_media_url('https://www.instagram.com/reel/ABCdef12/?igsh=foo')
        self.assertEqual((result.platform, result.kind), ('instagram', 'reel'))
        self.assertEqual(result.url, 'https://www.instagram.com/reel/ABCdef12/')
        self.assertEqual(allowed_modes(result), ('video', 'audio'))

    def test_instagram_post(self):
        result = parse_media_url('https://instagram.com/p/ABCdef12/')
        self.assertIn('photos', allowed_modes(result))

    def test_tiktok_regular(self):
        result = parse_media_url('https://www.tiktok.com/@hello.world/video/7301234567890123?is_from_webapp=1')
        self.assertEqual(result.platform, 'tiktok')

    def test_tiktok_short(self):
        result = parse_media_url('https://vm.tiktok.com/ZMabcd12/')
        self.assertEqual(result.platform, 'tiktok')

    def test_youtube_shorts(self):
        result = parse_media_url('https://www.youtube.com/shorts/abcD12-XYZ0?si=x')
        self.assertEqual((result.platform, result.kind), ('youtube', 'shorts'))

    def test_pinterest_pin(self):
        result = parse_media_url('https://www.pinterest.com/pin/1234567890/')
        self.assertEqual(result.platform, 'pinterest')
        self.assertIn('photos', allowed_modes(result))

    def test_pinterest_short(self):
        result = parse_media_url('https://pin.it/ABC123x')
        self.assertEqual(result.platform, 'pinterest')

    def test_reject_nonwhitelist(self):
        for url in ('http://localhost/admin',
                    'https://www.youtube.com.evil.test/shorts/abcD12-XYZ0',
                    'https://www.instagram.com.example.com/reel/ABCdef12/',
                    'https://www.youtube.com/playlist?list=PL001',
                    'https://www.instagram.com/user/'):
            self.assertIsNone(parse_media_url(url), url)

    def test_link_embedded_in_reply(self):
        result = parse_media_url('📎 TikTok\n🔗 https://vm.tiktok.com/ZMabcdef/\n\nTanlang')
        self.assertEqual(result.platform, 'tiktok')


if __name__ == '__main__':
    unittest.main()
