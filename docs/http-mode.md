# HTTP mode

`odoo-mcp run` speaks stdio: every MCP client session starts its own
`odoo-mcp` process. That stays the default, and it is what the plugins use.

`odoo-mcp serve` exposes the same tools over Streamable HTTP from **one**
process. It has two modes, picked with `--auth`:

| | `--auth local` | `--auth oauth` (default) |
|---|---|---|
| Who connects | Your own MCP clients on this machine | Remote users, hosted MCP clients |
| Identity | This machine's `profiles.json` | Each user's own Odoo login |
| Authentication | Bearer token in a 0600 file, loopback only | OAuth 2.1, consent against Odoo |
| Solves | Memory: one process for every session | Access without installing anything |

## Local mode: one server for every session on this machine

Each stdio session loads its own Python, MCP SDK, pydantic and httpx, about
50-65 MiB. A workstation with dozens of long-lived sessions ends up with
dozens of identical idle processes. `--auth local` serves all of them from
one process whose memory does not grow with the number of sessions.

```bash
odoo-mcp serve --auth local --port 5010 [--profile prod]
claude mcp add -s user --transport http odoo http://127.0.0.1:5010/mcp \
  --header "Authorization: Bearer $(cat ~/.config/odoo-mcp/local-token)"
```

The first start creates `~/.config/odoo-mcp/local-token` with mode 0600,
next to `profiles.json`, and every request must present it. The server
prints the file path, never the token. `--rotate-token` replaces it; clients
then need the new value.

Keep the server name (`odoo` above) the one your stdio config used, so tool
names and permission rules do not change. `--profile` sets the fallback
profile, like `run --profile`.

Rules this mode enforces:

- It binds `127.0.0.1`, `localhost` or `::1` only, compared as exact
  strings: `0.0.0.0`, `127.1`, `::ffff:127.0.0.1` or `LOCALHOST` refuse to
  start.
- Every request needs the bearer token (401 otherwise). The token file has
  the same 0600 mode as `profiles.json`, so the server reaches exactly who
  stdio reaches: your OS user. Another user on a shared host, a port that
  VS Code, `ssh -R` or Docker forwarded, or a local service tricked into a
  request (SSRF) reaches the port but not the token. The server refuses to
  start if the file is readable by anyone else.
- Only loopback `Host` headers are accepted (DNS rebinding), and **no**
  `Origin`: CLI clients send none, so any request with one comes from a
  browser page — including claude.ai or a dev server on another localhost
  port — and is refused with 403. Browser-based tools such as MCP Inspector
  cannot connect; use `--auth oauth` or `run` for those.
- Tool calls from different sessions really run in parallel. Calls that
  depend on each other must not be sent in the same parallel batch.

To keep it running, see the user unit in [`deploy/`](https://git.vauxoo.com/ai/mcp.odoo/-/tree/main/deploy).

## OAuth mode: a remote connector

Remote MCP clients (Claude on the web, Claude Code, MCP Inspector) connect to
a URL. Users sign in with **their own Odoo credentials**, and every tool call
runs as that Odoo user, under their own access rights.

`profiles.json` is not used in this mode. It belongs to whoever runs the
server, not to the people connecting to it.

### Serving it for real

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
| `--auth` | `oauth` | `oauth` or `local`. See the table at the top. |
| `--profile` / `-p` | default profile | Fallback profile. `--auth local` only. |
| `--rotate-token` | off | Replace the local bearer token before starting. `--auth local` only. |
| `--public-url` | — | The exact URL users paste in. Required with `--auth oauth`. |
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

**Odoo servers behind a private CA cannot connect yet.** Certificates are
verified against this host's default trust store, and a failure is never
downgraded. The user sees why (self-signed, unknown CA, expired, wrong host
name), that nothing was sent, and that the fix is on the operator's side;
the server log names the host. There is no operator setting to trust a
private CA in OAuth mode yet.

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
