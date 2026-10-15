from unittest.mock import patch

import httpx
from django.test import SimpleTestCase, override_settings

from .murf_client import murf_client


@override_settings(MURFDUB_ENABLED=True, MURFDUB_API_KEY='test-dub-key')
class MurfContractTests(SimpleTestCase):
    def test_official_sdk_job_id_requests(self):
        calls = []
        def handle(request):
            calls.append(request)
            if request.method == 'POST':
                return httpx.Response(200, json={'job_id': 'job-only', 'dubbing_type': 'AUTOMATED',
                    'file_name': 'demo.mp4', 'priority': 'NORMAL', 'target_locales': ['en_US']})
            return httpx.Response(200, json={'job_id': 'job-only', 'status': 'PROCESSING'})
        transport = httpx.Client(transport=httpx.MockTransport(handle))
        with patch('studio.murf_client.httpx.Client', return_value=transport), murf_client() as client:
            created = client.dubbing.jobs.create(target_locales=['en_US'], file_name='demo.mp4',
                file_url='https://example.test/source', request_options={'max_retries': 0})
            status = client.dubbing.jobs.get_status(job_id=created.job_id)
        self.assertEqual(status.job_id, 'job-only')
        self.assertEqual([r.url.path for r in calls], ['/v1/murfdub/jobs/create', '/v1/murfdub/jobs/job-only/status'])
        self.assertEqual(calls[0].headers['api-key'], 'test-dub-key')
        self.assertNotIn(b'project_id', calls[0].content)
        self.assertIn(b'en_US', calls[0].content)
