# Odoo 19+ External JSON-2 API

**Source:** <https://www.odoo.com/documentation/19.0/developer/reference/external_api.html>  
**Applies to:** Odoo ≥ 19.0  
**Deprecation deadline:** XML-RPC and JSON-RPC removed in Odoo **22** (fall 2028)

---

## 1. Deprecation Timeline

| Endpoint | Status |
|----------|--------|
| `/xmlrpc` | Deprecated in 19, removed in 22 |
| `/xmlrpc/2` | Deprecated in 19, removed in 22 |
| `/jsonrpc` | Deprecated in 19, removed in 22 |
| `/json/2/<model>/<method>` | **New in 19, the future standard** |
| `@route(type='jsonrpc')` (internal) | NOT deprecated |

---

## 2. New API: `/json/2`

### Request Format

```http
POST /json/2/<model>/<method> HTTP/1.1
Host: mycompany.example.com
Authorization: bearer <API_KEY>
Content-Type: application/json; charset=utf-8
X-Odoo-Database: mycompany        # Optional: only when multi-db
User-Agent: mysoftware/1.0        # Recommended
```

Body is a JSON object with **named parameters only** (no positional args):

```json
{
  "ids": [1, 2, 3],          // for instance methods (omit for @api.model)
  "context": {"lang": "en_US"},
  "domain": [["name", "ilike", "%deco%"]],
  "fields": ["name"],
  "limit": 20
}
```

### Response Format

**Success → HTTP 200**, body = JSON-serialized return value directly:

```json
[{"id": 25, "name": "Deco Addict"}]
```

**Error → HTTP 4xx/5xx**, body = error object:

```json
{
  "name": "werkzeug.exceptions.Unauthorized",
  "message": "Invalid apikey",
  "arguments": ["Invalid apikey", 401],
  "context": {},
  "debug": "Traceback..."
}
```

---

## 3. Authentication: API Key (Bearer Token)

- No more `uid` + `password` per call
- Generate API key: **Settings > Users > User > Account Security > API Keys**
- Key is 160-bit random, shown ONLY once — store securely
- Max duration: 3 months (must rotate)
- Set as: `Authorization: bearer <key>`

### Get current user ID (replaces `authenticate()`)

```python
# POST /json/2/res.users/context_get  (no ids = current user from API key)
```

---

## 4. Python Migration Examples

### Old: XML-RPC

```python
from xmlrpc.client import ServerProxy
common = ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PASSWORD, {})
obj = ServerProxy(f"{URL}/xmlrpc/2/object")
result = obj.execute_kw(DB, uid, PASSWORD, "res.partner", "search_read",
                        [[["is_company", "=", True]]],
                        {"fields": ["name"], "limit": 10})
```

### New: JSON-2

```python
import requests

BASE_URL = "https://mycompany.example.com/json/2"
API_KEY = "..."  # from secure storage
headers = {
    "Authorization": f"bearer {API_KEY}",
    "X-Odoo-Database": "mycompany",      # omit if single-db
    "User-Agent": "my-odoo-client/1.0",
}

result = requests.post(
    f"{BASE_URL}/res.partner/search_read",
    headers=headers,
    json={
        "context": {"lang": "en_US"},
        "domain": [["is_company", "=", True]],
        "fields": ["name"],
        "limit": 10,
    },
).json()
```

### Mapping: Old methods → New endpoints

| Old (`execute_kw`) | New JSON-2 URL |
|--------------------|---------------|
| `search` | `POST /json/2/<model>/search` |
| `read` | `POST /json/2/<model>/read` |
| `search_read` | `POST /json/2/<model>/search_read` |
| `write` | `POST /json/2/<model>/write` |
| `create` | `POST /json/2/<model>/create` |
| `unlink` | `POST /json/2/<model>/unlink` |
| `fields_get` | `POST /json/2/<model>/fields_get` |
| `execute_kw` custom | `POST /json/2/<model>/<method>` |
| `version()` (common) | `GET /web/version` |
| `authenticate()` | Not needed — API key auth |

---

## 5. Key Differences from Old API

| Aspect | XML-RPC / JSON-RPC | JSON-2 |
|--------|-------------------|--------|
| Auth | `uid` + password each call | Bearer API key (header) |
| Args | Positional (`args`, `kw`) | Named (JSON body) |
| Model | In body | In URL path |
| Method | In body | In URL path |
| Transactions | Stateless, 1 per call | Stateless, 1 per call |
| Error format | Exception dict inside 200 | HTTP 4xx/5xx + error JSON |
| db header | Always required | Only for multi-db |

---

## 6. Version Detection (`/web/version`)

```python
import httpx
r = httpx.get(f"{base_url}/web/version")
info = r.json()
# {"version_info": [19, 0, 0, "final", 0, ""], "version": "19.0"}
major = info["version_info"][0]  # 19
```

Use this to decide which client to instantiate.

---

## 7. Impact on Agnostic Odoo Clients

### Typical Architecture

- `XmlRpcClient` → `/xmlrpc/2/common` + `/xmlrpc/2/object`
- `JsonRpcClient` → `/jsonrpc` or `/jsonrpc/2`  
- Protocol selection based on Odoo version

### Required changes for v19+ support

1. **New `Json2Client` abstraction**
   - Uses `httpx.post(f"{base_url}/json/2/{model}/{method}", headers=..., json=body)`
   - No `uid`, no `password` in calls
   - New configuration field: `api_key` (SecretStr) instead of `password`
2. **Config schema**: add `api_key` optional field
3. **AUTO detection**: if `version_info[0] >= 19` → use `Json2Client`
4. **Client Interfaces stay identical** — only the transport layer changes
5. **Tooling / CLI**: Provisioning must support `api_key` options

### Profile config for v19+

```json
{
  "name": "prod",
  "url": "https://mycompany.odoo.com",
  "database": "mycompany",
  "api_key": "6578616d706c65206a736f6e20617069206b6579",
  "protocol": "json2"
}
```

### Backward compatibility strategy

- Keep `XmlRpcClient` and `JsonRpcClient` for Odoo < 19
- Add `Json2Client` for Odoo ≥ 19
- `AUTO` mode detects version and selects the right client
- Both `password` and `api_key` fields in connection configurations (mutually exclusive)
