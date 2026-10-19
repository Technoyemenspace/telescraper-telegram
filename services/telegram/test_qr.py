import asyncio
import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
from main import create_qr, ensure_connected, session


class QrTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnected_client_reconnects_before_generating_qr(self):
        qr = SimpleNamespace(url='tg://login?token=test', expires=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30), wait=AsyncMock())
        client = SimpleNamespace(is_connected=Mock(return_value=False), connect=AsyncMock(), is_user_authorized=AsyncMock(return_value=False), qr_login=AsyncMock(return_value=qr))
        state = SimpleNamespace(client=client, lock=asyncio.Lock(), qr=None, qr_task=None, status='idle')
        client.qr_login.side_effect = lambda: qr if client.connect.await_count == 1 else None
        result = await create_qr(SimpleNamespace(app=SimpleNamespace(state=state)))
        client.connect.assert_awaited_once()
        self.assertEqual(result['status'], 'waiting')
        self.assertEqual(result['url'], qr.url)
        state.qr_task.cancel()
        try:
            await state.qr_task
        except asyncio.CancelledError:
            pass

    async def test_connected_client_is_not_reconnected(self):
        client = SimpleNamespace(is_connected=Mock(return_value=True), connect=AsyncMock())
        await ensure_connected(SimpleNamespace(client=client))
        client.connect.assert_not_awaited()

    async def test_failed_reconnection_returns_recoverable_error(self):
        client = SimpleNamespace(is_connected=Mock(return_value=False), connect=AsyncMock(side_effect=ConnectionError()))
        with self.assertRaises(HTTPException) as error:
            await ensure_connected(SimpleNamespace(client=client))
        self.assertEqual(error.exception.status_code, 503)

    async def test_session_reports_expired_qr(self):
        state = SimpleNamespace(status='waiting', qr=SimpleNamespace(expires=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)))
        result = await session(SimpleNamespace(app=SimpleNamespace(state=state)))
        self.assertEqual(result['status'], 'expired')