import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from main import ScanInput, WebScanInput, authorized
from rules import CHANNEL_DELAY_SECONDS, DEPTHS, WEB_PLATFORMS, canonical_wa, extract, extract_web, parse_ddg, web_queries


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


class WebSearchTests(unittest.TestCase):
    def test_platform_dorks(self):
        self.assertEqual(WEB_PLATFORMS, ('facebook', 'instagram', 'twitter', 'telegram', 'web'))
        queries = web_queries('facebook', ['عقارات اليمن'])
        self.assertEqual(queries, ['site:facebook.com "عقارات اليمن" chat.whatsapp.com'])
        self.assertEqual(web_queries('web', []), ['chat.whatsapp.com'])
        self.assertEqual(web_queries('twitter', ['وظائف']), ['site:x.com "وظائف" chat.whatsapp.com', 'site:twitter.com "وظائف" chat.whatsapp.com'])

    def test_platform_validation(self):
        with self.assertRaises(ValidationError):
            WebScanInput(platform='tiktok')

    def test_parse_ddg(self):
        body = (
            '<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.facebook.com%2Fgroups%2F1">مجموعة عقارات <b>اليمن</b></a>'
            '<a class="result__snippet">انضم: https://chat.whatsapp.com/AAAAAAAAAAAAAAAAAAAAAA</a>'
        )
        results = parse_ddg(body)
        self.assertEqual(results[0]['url'], 'https://www.facebook.com/groups/1')
        self.assertEqual(results[0]['title'], 'مجموعة عقارات اليمن')
        self.assertIn('chat.whatsapp.com', results[0]['snippet'])

    def test_exact_keyword_filter_and_dedup(self):
        url = 'https://chat.whatsapp.com/AAAAAAAAAAAAAAAAAAAAAA'
        invite = 'https://chat.whatsapp.com/invite/AAAAAAAAAAAAAAAAAAAAAA'
        results = [
            dict(title='عقارات اليمن', url='https://facebook.com/1', snippet=url),
            dict(title='عقارات اليمن', url='https://facebook.com/2', snippet=invite),
            dict(title='طبخ', url='https://facebook.com/3', snippet=url),
        ]
        leads, duplicates = extract_web(results, 'facebook', ['عقارات'], set(), '2026-10-17')
        self.assertEqual([l['url'] for l in leads], [url])
        self.assertEqual(duplicates, 1)
        self.assertEqual(leads[0]['channel'], 'facebook')
        self.assertEqual(extract_web(results, 'facebook', ['وظائف'], set(), '2026-10-17'), ([], 0))

    def test_canonical_wa(self):
        self.assertEqual(canonical_wa('https://chat.whatsapp.com/invite/ABCDEFGHIJKLMNOPQRSTUV'), 'https://chat.whatsapp.com/ABCDEFGHIJKLMNOPQRSTUV')


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