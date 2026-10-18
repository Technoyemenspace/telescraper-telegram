"""Bounded oldest-first pages; cursors are message IDs, not total limits."""
HISTORY_BATCH_SIZE = 500


async def history_page(client, channel, after_id=0, snapshot_id=None):
    if snapshot_id is None:
        latest = await client.get_messages(channel, limit=1)
        snapshot_id = latest[0].id if latest else 0
    if snapshot_id == 0:
        return [], None, snapshot_id
    messages = []
    async for message in client.iter_messages(
        channel, limit=HISTORY_BATCH_SIZE, reverse=True,
        min_id=after_id, max_id=snapshot_id + 1,
    ):
        messages.append(message)
    next_id = messages[-1].id if len(messages) == HISTORY_BATCH_SIZE and messages[-1].id < snapshot_id else None
    return messages, next_id, snapshot_id