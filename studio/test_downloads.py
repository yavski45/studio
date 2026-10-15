from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from .downloads import save_remote_file, validate_download_url


class DownloadValidationTests(SimpleTestCase):
    def test_unknown_hosts_and_http_rejected_before_network(self):
        for url in ['http://cdn.murf.ai/file.mp4', 'https://evil.test/file.mp4', 'https://murf.ai.evil.test/file.mp4', 'https://user:pass@cdn.murf.ai/file.mp4', 'https://cdn.murf.ai:8080/file.mp4']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_download_url(url)

    @patch('studio.downloads.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))])
    def test_private_ip_rejected(self, dns):
        with self.assertRaises(ValueError):
            validate_download_url('https://cdn.murf.ai/file.mp4')

    @patch('studio.downloads.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))])
    def test_provider_host_accepted(self, dns):
        validate_download_url('https://cdn.murf.ai/file.mp4')

    @patch('studio.downloads.validate_download_url')
    @patch('studio.downloads.requests.Session')
    @patch('studio.downloads.TemporaryFile')
    @patch('studio.downloads.time.monotonic', return_value=0)
    def test_output_above_four_gib_is_streamed_without_size_rejection(self, clock, temporary, session, validate):
        class LargeChunk(bytes):
            def __len__(self):
                return 5 * 1024 ** 3
        response = session.return_value.__enter__.return_value.get.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [LargeChunk(b'x')]
        field = MagicMock()
        field.__bool__.return_value = False
        field.field.name = 'video'
        save_remote_file('https://cdn.murf.ai/file.mp4', field, 'result.mp4')
        temporary.return_value.__enter__.return_value.write.assert_called_once()
        field.save.assert_called_once()
        field.instance.save.assert_called_once_with(update_fields=['video'])
