import html
import re
import urllib.parse

WA_REGEX = re.compile(r'https?://(?:chat\.whatsapp\.com/(?:invite/)?[A-Za-z0-9]{20,24}|wa\.me/[0-9]+)')
TARGET_REGEX = re.compile(r'^@[A-Za-z][A-Za-z0-9_]{3,31}$')
DEPTHS = (100, 500, 3000)
CHANNEL_DELAY_SECONDS = 3

# Public web/social search: no account login to any platform is required.
WEB_PLATFORMS = ('facebook', 'instagram', 'twitter', 'telegram', 'web')
SITE_DORKS = {
    'facebook': ('facebook.com',),
    'instagram': ('instagram.com',),
    'twitter': ('x.com', 'twitter.com'),
    'telegram': ('t.me',),
    'web': None,
}
WEB_DELAY_SECONDS = 1.5
MAX_WEB_QUERIES = 10


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


def canonical_wa(url):
    """Normalize chat.whatsapp.com/invite/CODE to the canonical invite URL so duplicates collapse."""
    return re.sub(r'chat\.whatsapp\.com/invite/', 'chat.whatsapp.com/', url)


def web_queries(platform, keywords):
    """Google-Dorking style queries for one platform. Blank keywords search any WhatsApp link."""
    sites = SITE_DORKS[platform]
    kws = [k for k in keywords if k.strip()] or ['']
    queries = []
    for kw in kws:
        base = f'"{kw}" chat.whatsapp.com' if kw else 'chat.whatsapp.com'
        if sites:
            queries.extend(f'site:{site} {base}' for site in sites)
        else:
            queries.append(base)
    return queries[:MAX_WEB_QUERIES]


def parse_ddg(body):
    """Parse DuckDuckGo HTML results into title/url/snippet records."""
    results = []
    for match in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        href = html.unescape(match.group(1))
        if 'uddg=' in href:
            href = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
        title = html.unescape(re.sub(r'<[^>]+>', '', match.group(2))).strip()
        results.append({'title': title, 'url': href, 'snippet': ''})
    snippets = [
        html.unescape(re.sub(r'<[^>]+>', '', snippet)).strip()
        for snippet in re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', body, re.S)
    ]
    for record, snippet in zip(results, snippets):
        record['snippet'] = snippet
    return results


def parse_ddg_lite(body):
    """Parse the DuckDuckGo Lite HTML results (single-quoted class attributes)."""
    results = []
    anchors = re.findall(r"<a[^>]*class='result-link'[^>]*>(.*?)</a>", body, re.S)
    hrefs = [html.unescape(m) for m in re.findall(r"<a[^>]*class='result-link'[^>]*>", body)]
    snippets = [
        html.unescape(re.sub(r'<[^>]+>', '', s)).strip()
        for s in re.findall(r"<td class='result-snippet'>(.*?)</td>", body, re.S)
    ]
    for i, title in enumerate(anchors):
        href_match = re.search(r'href="([^"]+)"', hrefs[i]) if i < len(hrefs) else None
        href = html.unescape(href_match.group(1)) if href_match else ''
        if 'uddg=' in href:
            href = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
        results.append({
            'title': html.unescape(re.sub(r'<[^>]+>', '', title)).strip(),
            'url': href,
            'snippet': snippets[i] if i < len(snippets) else '',
        })
    return results


def parse_bing(body):
    """Parse Bing HTML results into title/url/snippet records."""
    results = []
    for block in re.findall(r'<li class="b_algo".*?</li>', body, re.S):
        match = re.search(r'<h2><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not match:
            continue
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        results.append({
            'title': html.unescape(re.sub(r'<[^>]+>', '', match.group(2))).strip(),
            'url': html.unescape(match.group(1)),
            'snippet': html.unescape(re.sub(r'<[^>]+>', '', snippet_match.group(1))).strip() if snippet_match else '',
        })
    return results


def extract_web(results, platform, keywords, seen, date):
    """Keep WhatsApp links only when the result title/snippet contains the target keyword exactly."""
    leads, duplicates = [], 0
    for record in results:
        blob = f"{record['title']} {record['snippet']} {record['url']}".lower()
        keyword = next((k for k in keywords if k.lower() in blob), None) if keywords else 'all'
        if keyword is None:
            continue
        text = f"{record['snippet']} {record['title']} {record['url']}"
        for raw in WA_REGEX.findall(text):
            url = canonical_wa(raw)
            if url in seen:
                duplicates += 1
                continue
            seen.add(url)
            leads.append(dict(url=url, channel=platform, keyword=keyword, date=date, snippet=record['snippet'][:80] or record['title'][:80]))
    return leads, duplicates
