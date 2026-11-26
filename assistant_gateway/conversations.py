"""Gateway-only client for user-owned Django history; no credentials in saved data."""
from http.cookies import SimpleCookie
import httpx


class ConversationError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class ConversationClient:
    def __init__(self, base_url: str, service_token: str):
        self.base_url = base_url.rstrip('/')
        self.service_token = service_token

    async def _post(self, path: str, cookie: str, data: dict) -> dict:
        headers = {'Cookie': cookie, 'X-Assistant-History-Token': self.service_token}
        parsed = SimpleCookie()
        parsed.load(cookie)
        if 'csrftoken' in parsed:
            headers['X-CSRFToken'] = parsed['csrftoken'].value
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.base_url + '/api/demo/secure/assistant/internal/' + path,
                    json=data, headers=headers)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ConversationError(502, 'Conversation storage is unavailable.') from exc
        if response.status_code != 200:
            messages = body.get('error', [])
            message = messages[0].get('message') if messages else 'Conversation request failed.'
            raise ConversationError(response.status_code, str(message))
        return body['result']

    async def begin(self, cookie, conversation_id, run_id, request_id, question):
        return await self._post('turns', cookie, {
            'conversation_id': conversation_id, 'run_id': run_id,
            'request_id': request_id, 'question': question,
        })

    async def tool(self, cookie, run_id, call_id, name, phase, arguments=None, result=None):
        return await self._post(f'turns/{run_id}/tools', cookie, {
            'call_id': call_id, 'name': name, 'phase': phase,
            'arguments': arguments or {}, 'result': result,
        })

    async def finish(self, cookie, run_id, text, status):
        return await self._post(f'turns/{run_id}/finish', cookie,
            {'assistant_text': text[:12000], 'status': status})
