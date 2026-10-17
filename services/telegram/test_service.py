import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from main import ScanInput, authorized
from rules import CHANNEL_DELAY_SECONDS, DEPTHS, extract


class RulesTests(unittest.TestCase):
    def test_depths(self):
        self.assertEqual(DEPTHS, (100, 500, 3000))
        with self.assertRaises(ValidationError):
            ScanInput(channel='@yemen_jobs', depth=101)

    def test_delay(self):
        self.assertGreaterEqual(CHANNEL_DELAY_SECONDS, 2)
        self.assertLessEqual(CHANNEL_DELAY_SECONDS, 4)

    def test_keyword_and_duplicates(self):
        url = 'https://chat.whatsapp.com/AAAAAAAAAAAAAAAAAAAAAA'
        messages = [dict(text='وظائف ' + url, date='2026-10-17')] * 2
        leads, duplicates = extract(messages, '@yemen_jobs', ['وظائف'], set())
        self.assertEqual([l['url'] for l in leads], [url])
        self.assertEqual(duplicates, 1)
        self.assertEqual(extract(messages, '@yemen_jobs', ['عقارات'], set()), ([], 0))

    def test_empty_keywords_match_all(self):
        leads, _ = extract([dict(text='https://wa.me/967712345678', date='2026-10-17')], '@yemen_jobs', [], set())
        self.assertEqual(leads[0]['keyword'], 'all')


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key_cannot_read_session(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(key='a' * 32)))
        with self.assertRaises(HTTPException) as error:
            await authorized(request, '')
        self.assertEqual(error.exception.status_code, 401)

    async def test_correct_key_accepted(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(key='a' * 32)))
        self.assertIsNone(await authorized(request, 'a' * 32))


if __name__ == '__main__':
    unittest.main()