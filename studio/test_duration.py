import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.test import SimpleTestCase

from .duration import video_duration_ms


class DurationTests(SimpleTestCase):
    def setUp(self):
        self.storage = InMemoryStorage()
        self.storage.save('source.mp4', ContentFile(b'local video content'))
        self.source = SimpleNamespace(name='source.mp4', storage=self.storage)

    @patch('studio.duration.subprocess.run')
    def test_duration_from_private_local_file_and_no_network_protocol(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps({
            'format': {'duration': '90.000001'}, 'streams': [{'codec_type': 'video'}]}).encode())
        self.assertEqual(video_duration_ms(self.source), 90001)
        args = run.call_args.args[0]
        self.assertEqual(args[args.index('-protocol_whitelist') + 1], 'file,pipe')
        self.assertFalse(args[-1].startswith('http'))

    @patch('studio.duration.subprocess.run')
    def test_unreadable_missing_or_nonfinite_duration_rejected(self, run):
        for data in [[], {'format': {'duration': 'NaN'}, 'streams': [{'codec_type': 'video'}]},
                     {'format': {'duration': '90'}, 'streams': [{'codec_type': 'audio'}]},
                     {'format': {}, 'streams': [{'codec_type': 'video'}]}]:
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(data).encode())
            with self.assertRaises(ValueError):
                video_duration_ms(self.source)
        run.side_effect = subprocess.TimeoutExpired('ffprobe', 90)
        with self.assertRaises(ValueError):
            video_duration_ms(self.source)
