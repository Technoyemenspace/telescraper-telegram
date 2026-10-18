import unittest
from types import SimpleNamespace
from history import history_page, HISTORY_BATCH_SIZE


class FakeClient:
    def __init__(self, count):
        self.messages = [SimpleNamespace(id=i) for i in range(1, count + 1)]

    async def get_messages(self, channel, limit):
        return self.messages[-limit:][::-1]

    async def iter_messages(self, channel, *, limit, reverse, min_id, max_id):
        assert reverse
        selected = [m for m in self.messages if min_id < m.id < max_id]
        for message in selected[:limit]:
            yield message


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_30000_messages_oldest_to_newest_without_total_cap(self):
        client = FakeClient(30000)
        cursor, snapshot, collected = 0, None, []
        while True:
            page, next_id, snapshot = await history_page(client, '@channel', cursor, snapshot)
            self.assertLessEqual(len(page), HISTORY_BATCH_SIZE)
            collected.extend(m.id for m in page)
            if next_id is None:
                break
            self.assertGreater(next_id, cursor)
            cursor = next_id
        self.assertEqual(collected, list(range(1, 30001)))

    async def test_resume_preserves_snapshot_and_handles_deleted_ids(self):
        client = FakeClient(1002)
        first, cursor, snapshot = await history_page(client, '@channel')
        client.messages = [m for m in client.messages if m.id != 501]
        client.messages.append(SimpleNamespace(id=1003))
        second, cursor, snapshot = await history_page(client, '@channel', cursor, snapshot)
        last, cursor, _ = await history_page(client, '@channel', cursor, snapshot)
        self.assertEqual([m.id for m in first + second + last], [i for i in range(1, 1003) if i != 501])
        self.assertIsNone(cursor)

    async def test_empty_channel_finishes(self):
        self.assertEqual(await history_page(FakeClient(0), '@channel'), ([], None, 0))