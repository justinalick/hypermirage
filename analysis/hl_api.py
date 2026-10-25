"""Hyperliquid public info API client: throttled per IP, retried on 429 and network errors, cached.

The info endpoint limits each IP to a request weight budget per minute (most info requests weigh 20,
so about one request per second is sustainable). Every request here waits at least MIN_GAP seconds
after the previous one and backs off on 429. Answers to userRole / subAccounts are cached in
data/derived/hl_api/cache.json, keyed by the request body: they are today's declared links, the same
for every window, so a second window re-uses them. A request that still fails after the retries is
raised, never stored, so a failure cannot pass as an account with no role.
"""
import json, os, time, urllib.error, urllib.request

URL = "https://api.hyperliquid.xyz/info"
MIN_GAP = float(os.environ.get("HL_MIN_GAP", "1.1"))
CACHE = "data/derived/hl_api/cache.json"
_last = [0.0]


def post(body, tries=8):
    for k in range(tries):
        wait = _last[0] + MIN_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = urllib.request.Request(URL, json.dumps(body).encode(), {"content-type": "application/json"})
            return json.load(urllib.request.urlopen(r, timeout=20))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(min(60, 5 * 2 ** k))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(min(60, 5 * 2 ** k))
    raise RuntimeError(f"info API failed after {tries} tries: {body.get('type')}")


class Cached:
    def __init__(self, path=CACHE):
        self.path = path
        self.d = json.load(open(path)) if os.path.exists(path) else {}
        self.n_new = 0

    def get(self, body):
        key = json.dumps(body, sort_keys=True)
        if key not in self.d:
            self.d[key] = post(body)
            self.n_new += 1
            if self.n_new % 50 == 0:
                self.save()
        return self.d[key]

    def role(self, a):
        return self.get({"type": "userRole", "user": a})

    def subs(self, a):
        return self.get({"type": "subAccounts", "user": a})

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        json.dump(self.d, open(tmp, "w"))
        os.replace(tmp, self.path)


def roles_and_subs(addresses, api=None):
    """{'roles': {addr: userRole}, 'subs': {master: subAccounts}} for the addresses and their masters,
    in the shape the analysis scripts read."""
    api = api or Cached()
    roles = {a: api.role(a) for a in addresses}
    masters = {v["data"]["master"] for v in roles.values() if v.get("role") == "subAccount"}
    masters |= {a for a, v in roles.items() if v.get("role") == "user"}
    subs = {m: api.subs(m) for m in sorted(masters)}
    api.save()
    return {"roles": roles, "subs": subs}
