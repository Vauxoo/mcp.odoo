# HTTP mode — remote connector

`odoo-mcp run` speaks stdio: the client has to run on the same machine, with
this package installed and a profile configured by hand.

`odoo-mcp serve` exposes the same tools over HTTP so a remote MCP client —
Claude on the web, Claude Code, MCP Inspector — can connect to a URL instead.
Users sign in with **their own Odoo credentials**, and every tool call runs as
that Odoo user, under their own access rights.

`profiles.json` is not used in this mode. It belongs to whoever runs the
server, not to the people connecting to it.

## Quick start (local, no authentication)

```bash
pip install 'odoo-mcp-multi[http]'
odoo-mcp serve --no-auth --host 127.0.0.1 --port 5010
```

Then point MCP Inspector at `http://127.0.0.1:5010/mcp`.

`--no-auth` refuses to start on anything but a loopback address. It is for
development, and it prints a warning every time.

## Serving it for real

```bash
odoo-mcp serve \
  --host 127.0.0.1 --port 5010 --path /mcp \
  --public-url https://odoo-mcp.example.com/mcp \
  --odoo-timeout 60 --max-concurrency 32 \
  --allowed-odoo-host odoo.example.com
```

Bind loopback and put a reverse proxy or tunnel in front. `--public-url` is
the string users will paste into their client, and it must be exact —
scheme, host and path. The server derives the OAuth issuer, the protected
resource identifier and its Host allow-list from it, and refuses to start if
`--path` disagrees with it.

### How a user connects

1. Their client requests `/mcp` without a token and gets a `401` pointing at
   the protected resource metadata.
2. It discovers the authorization server, registers itself, and opens a
   browser at `/authorize`.
3. The browser lands on the consent page, which asks for the Odoo URL,
   database, login and an API key or password.
4. Those credentials are verified against that Odoo. Only on success is an
   authorization code issued.
5. The client exchanges the code for tokens, and every later call runs with
   the credentials from step 3.

### Credentials at rest

The credentials are encrypted with a key in `~/.config/odoo-mcp/http-secret.key`
(mode 0600) and stored in `~/.config/odoo-mcp/http-state.db`. The key is a
separate file on purpose: a copied database is not enough to read them.

Disconnecting the connector revokes the grant **and deletes the stored Odoo
credentials**.

Prefer API keys over passwords. An Odoo API key can be revoked on its own from
the user's preferences, without changing their password, and Odoo 19+ requires
one anyway.

## Managing what the server has issued

```bash
odoo-mcp http clients          # registered OAuth clients
odoo-mcp http grants           # active grants and the Odoo accounts behind them
odoo-mcp http revoke <grant>   # or --all
odoo-mcp http purge            # delete expired codes and tokens
```

## Options

| Option | Default | Purpose |
|---|---|---|
| `--host` / `--port` | `127.0.0.1` / `5010` | Where to bind. |
| `--path` | `/mcp` | Path the MCP endpoint is served on. |
| `--public-url` | — | The exact URL users paste in. Required unless `--no-auth`. |
| `--no-auth` | off | Disable OAuth. Loopback only. |
| `--json-response` / `--sse-response` | JSON | Response encoding. |
| `--stateless` / `--stateful` | stateless | See the note below before changing this. |
| `--state-db` | `~/.config/odoo-mcp/http-state.db` | Authorization state. |
| `--secret-key-file` | `~/.config/odoo-mcp/http-secret.key` | Credential encryption key. |
| `--access-token-ttl` | `3600` | Access token lifetime, seconds. |
| `--refresh-token-ttl` | `2592000` | Refresh token lifetime, seconds. |
| `--odoo-timeout` | `60` | Per-call RPC timeout, seconds. |
| `--max-concurrency` | `32` | Concurrent Odoo calls. |
| `--allowed-odoo-host` | none | Restrict which hosts the consent form may contact. Repeatable. |

## Things worth knowing

**Do not put an interactive gate in front of it.** A browser-based access
proxy — an OTP or SSO interstitial — will intercept the server-to-server
calls hosted MCP clients make and answer them with an HTML login page. The
authentication belongs to this server. Put the tunnel in front, not the gate.

**Keep `--stateless`.** With server-side sessions, the MCP session task is
created during the first request, and every later tool call inherits that
request's identity — so a stolen session id would run with the credentials of
whoever opened the session.

**Set `--allowed-odoo-host` if the server can reach a private network.** The
consent form is unauthenticated by necessity and dials whatever URL it is
given, which makes it a way to probe the network the server sits on.

**All tools are exposed**, including `write`, `unlink` and `execute_kw`.
Odoo's own access rights bound what any of them can do, because every call
runs as the end user, but the reach is theirs, not a restricted subset.

## Checking a deployment

```bash
curl -s https://odoo-mcp.example.com/.well-known/oauth-authorization-server | jq .
curl -si -X POST https://odoo-mcp.example.com/mcp | head -5
curl -s https://odoo-mcp.example.com/.well-known/oauth-protected-resource/mcp | jq -r .resource
```

- The second must be `401` with a `WWW-Authenticate` header. A `421` means the
  public hostname is not reaching the server as its `Host`.
- The third must print your connector URL exactly as users type it.
- If the first returns a redirect to a login page, something in front of the
  server is intercepting requests — see the note above.
