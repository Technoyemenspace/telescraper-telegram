import re

WA_REGEX = re.compile(r'https?://(?:chat\.whatsapp\.com/(?:invite/)?[A-Za-z0-9]{20,24}|wa\.me/[0-9]+)')
TARGET_REGEX = re.compile(r'^@[A-Za-z][A-Za-z0-9_]{3,31}$')
DEPTHS = (100, 500, 3000)
CHANNEL_DELAY_SECONDS = 3


def extract(messages, channel, keywords, seen):
    leads, duplicates = [], 0
    for message in messages:
        text = message['text']
        keyword = next((k for k in keywords if k.lower() in text.lower()), None) if keywords else 'all'
        if keyword is None:
            continue
        for url in WA_REGEX.findall(text):
            if url in seen:
                duplicates += 1
                continue
            seen.add(url)
            leads.append(dict(url=url, channel=channel, keyword=keyword, date=message['date'], snippet=text[:80]))
    return leads, duplicates