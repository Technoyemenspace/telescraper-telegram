"""Single-account service. All Telegram operations require a private shared key.

Run one process/replica: SQLite sessions and Telegram connections are not shared.
Only a trusted authenticated dashboard server may call this API.
"""
import asyncio
import contextlib
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import datetime

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from telethon import TelegramClient, errors
from telethon.tl.types import MessageEntityTextUrl

from rules import (
    CHANNEL_DELAY_SECONDS,
    DEPTHS,
    TARGET_REGEX,
    WEB_DELAY_SECONDS,
    extract,
    extract_web,
    parse_bing,
    parse_ddg,
    web_queries,
)


@asynccontextmanager
async def lifespan(app):
    api_id = os.environ.get('TELEGRAM_API_ID')
    api_hash = os.environ.get('TELEGRAM_API_HASH')
    key = os.environ.get('TELEGRAM_SERVICE_KEY', '')
    if not api_id or not api_hash or len(key) < 32:
        raise RuntimeError('Configure Telegram API credentials and a service key of at least 32 characters.')
    directory = Path(os.environ.get('SESSION_DIR', '/var/data/telegram'))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    client = TelegramClient(str(directory / 'account'), int(api_id), api_hash, flood_sleep_threshold=0)
    await client.connect()
    app.state.client = client
    app.state.key = key
    app.state.lock = asyncio.Lock()
    app.state.qr = None
    app.state.qr_task = None
    app.state.status = 'active' if await client.is_user_authorized() else 'idle'
    try:
        yield
    finally:
        task = app.state.qr_task
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await client.disconnect()


app = FastAPI(title='TeleScraper Telegram Service', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


async def authorized(request: Request, x_service_key: str = Header(default='')):
    if not hmac.compare_digest(x_service_key.encode(), request.app.state.key.encode()):
        raise HTTPException(401, 'Unauthorized')


@app.get('/health')
async def health():
    return {'ok': True}


async def wait_for_qr(state):
    try:
        await state.qr.wait()
        state.status = 'active'
    except errors.SessionPasswordNeededError:
        state.status = 'password_required'
    except asyncio.TimeoutError:
        state.status = 'expired'
    except asyncio.CancelledError:
        raise
    except Exception:
        state.status = 'failed'


@app.post('/session/qr', dependencies=[Depends(authorized)])
async def create_qr(request: Request):
    state = request.app.state
    async with state.lock:
        if await state.client.is_user_authorized():
            state.status = 'active'
            return {'status': 'active'}
        if state.qr_task and not state.qr_task.done():
            state.qr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.qr_task
        state.qr = await state.client.qr_login()
        state.status = 'waiting'
        state.qr_task = asyncio.create_task(wait_for_qr(state))
        return {'status': state.status, 'url': state.qr.url, 'expires': state.qr.expires.isoformat()}


@app.get('/session', dependencies=[Depends(authorized)])
async def session(request: Request):
    return {'status': request.app.state.status}


class PasswordInput(BaseModel):
    password: str = Field(min_length=1, max_length=256)


@app.post('/session/password', dependencies=[Depends(authorized)])
async def password(data: PasswordInput, request: Request):
    state = request.app.state
    async with state.lock:
        if state.status != 'password_required':
            raise HTTPException(409, 'No password challenge is pending')
        try:
            await state.client.sign_in(password=data.password)
        except errors.PasswordHashInvalidError:
            raise HTTPException(400, 'Incorrect Telegram verification password') from None
        except errors.FloodWaitError as exc:
            raise HTTPException(429, detail={'code': 'flood_wait', 'seconds': exc.seconds}) from None
        state.status = 'active'
        return {'status': 'active'}


@app.delete('/session', dependencies=[Depends(authorized)])
async def logout(request: Request):
    state = request.app.state
    async with state.lock:
        if state.qr_task and not state.qr_task.done():
            state.qr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.qr_task
        await state.client.log_out()
        await state.client.connect()
        state.qr = None
        state.status = 'idle'
        return {'status': 'idle'}


class ScanInput(BaseModel):
    channel: str = Field(min_length=5, max_length=33)
    depth: Literal[100, 500, 3000] = 100
    keywords: list[str] = Field(default_factory=list, max_length=100)
    seen: list[str] = Field(default_factory=list, max_length=10000)

    @field_validator('channel')
    @classmethod
    def validate_channel(cls, value):
        if not TARGET_REGEX.fullmatch(value):
            raise ValueError('Invalid channel handle')
        return value

    @field_validator('keywords', 'seen')
    @classmethod
    def validate_strings(cls, values):
        if any(not v.strip() or len(v) > 512 for v in values):
            raise ValueError('Invalid filter or URL')
        return values


@app.post('/scan', dependencies=[Depends(authorized)])
async def scan(data: ScanInput, request: Request):
    state = request.app.state
    async with state.lock:
        if not await state.client.is_user_authorized():
            state.status = 'idle'
            raise HTTPException(409, 'Connect Telegram first')
        # Serialized operations and a real delay protect the single Telegram account.
        await asyncio.sleep(CHANNEL_DELAY_SECONDS)
        messages = []
        try:
            async with asyncio.timeout(60):
                async for message in state.client.iter_messages(data.channel, limit=data.depth):
                    text = message.raw_text or ''
                    embedded = [e.url for e in message.entities or [] if isinstance(e, MessageEntityTextUrl)]
                    text = '\n'.join([text, *embedded])
                    messages.append({'text': text, 'date': message.date.isoformat()[:10] if message.date else ''})
        except errors.FloodWaitError as exc:
            # Let the caller wait exactly as Telegram requests; never bypass this delay.
            raise HTTPException(429, detail={'code': 'flood_wait', 'seconds': exc.seconds}) from None
        except (errors.ChannelPrivateError, errors.ChatAdminRequiredError):
            raise HTTPException(403, 'Private channel: membership or admin invite required') from None
        except (ValueError, errors.UsernameInvalidError, errors.UsernameNotOccupiedError):
            raise HTTPException(400, 'Channel not found') from None
        except (asyncio.TimeoutError, OSError):
            raise HTTPException(504, 'Telegram connection timed out') from None
        leads, duplicates = extract(messages, data.channel, data.keywords, set(data.seen))
        return {'leads': leads, 'duplicates': duplicates, 'messages': len(messages)}


class WebScanInput(BaseModel):
    platform: Literal['facebook', 'instagram', 'twitter', 'telegram', 'web']
    depth: Literal[100, 500, 3000] = 100
    keywords: list[str] = Field(default_factory=list, max_length=20)
    seen: list[str] = Field(default_factory=list, max_length=10000)

    @field_validator('keywords', 'seen')
    @classmethod
    def validate_strings(cls, values):
        if any(not v.strip() or len(v) > 512 for v in values):
            raise ValueError('Invalid filter or URL')
        return values


SEARCH_TARGETS = (
    ('post', 'https://html.duckduckgo.com/html/', parse_ddg),
    ('get', 'https://html.duckduckgo.com/html/', parse_ddg),
    ('get', 'https://lite.duckduckgo.com/lite/', parse_ddg),
    ('get', 'https://www.bing.com/search', parse_bing),
)


async def run_search_query(client, query):
    """Try search endpoints in order; return the first non-empty parsed result set."""
    for method, url, parser in SEARCH_TARGETS:
        try:
            if method == 'post':
                response = await client.post(url, data={'q': query})
            else:
                response = await client.get(url, params={'q': query})
            if response.status_code == 200:
                results = parser(response.text)
                if results:
                    return results
        except (httpx.HTTPError, asyncio.TimeoutError):
            continue
    return []


@app.post('/webscan', dependencies=[Depends(authorized)])
async def webscan(data: WebScanInput, request: Request):
    """Public web/social dork search. No platform login required; only indexed WhatsApp links."""
    seen = set(data.seen)
    leads, duplicates, queries_done = [], 0, 0
    today = datetime.date.today().isoformat()
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ar,en;q=0.8',
    }
    async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as client:
        for query in web_queries(data.platform, data.keywords):
            if len(leads) >= data.depth:
                break
            try:
                async with asyncio.timeout(25):
                    results = await run_search_query(client, query)
            except asyncio.TimeoutError:
                continue
            if results:
                queries_done += 1
                found, dupes = extract_web(results, data.platform, data.keywords, seen, today)
                leads.extend(found)
                duplicates += dupes
            await asyncio.sleep(WEB_DELAY_SECONDS)
    return {'leads': leads[:data.depth], 'duplicates': duplicates, 'queries': queries_done}