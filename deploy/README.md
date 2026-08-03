# Deploying HTTP mode

`odoo-mcp-http.service` is a systemd template unit. It is instantiated per
user, so `odoo-mcp-http@nhomar.service` runs as `nhomar` and keeps its state
under that user's `~/.config/odoo-mcp`.

## Install

```bash
sudo cp deploy/odoo-mcp-http.service /etc/systemd/system/odoo-mcp-http@.service
sudoedit /etc/systemd/system/odoo-mcp-http@.service     # set --public-url
sudo systemctl daemon-reload
sudo systemctl enable --now odoo-mcp-http@$USER
systemctl status odoo-mcp-http@$USER
```

`--public-url` must be the exact URL users will paste into their MCP client.
The server refuses to start if it disagrees with `--path`.

## Put it behind a proxy

Bind loopback and terminate TLS in front. The origin must receive the public
`Host` header — do not rewrite it, or the server answers `421 Misdirected
Request` because the hostname is not in its allow-list.

nginx:

```nginx
location /mcp {
    proxy_pass http://127.0.0.1:5010;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 120s;
}
```

Cloudflare Tunnel:

```yaml
- hostname: odoo-mcp.example.com
  service: http://localhost:5010
  # no httpHostHeader — the original Host must reach the origin
```

**Do not put an interactive access gate in front of this hostname.** A
browser-based OTP or SSO interstitial will intercept the server-to-server
calls hosted MCP clients make and answer them with an HTML login page, and
the connector fails with an opaque error. Authentication is this server's job.

## Verify

```bash
curl -s https://odoo-mcp.example.com/.well-known/oauth-authorization-server | jq .
curl -si -X POST https://odoo-mcp.example.com/mcp | head -5
curl -s https://odoo-mcp.example.com/.well-known/oauth-protected-resource/mcp | jq -r .resource
```

| Symptom | Cause |
|---|---|
| `421 Misdirected Request` | The public hostname is not reaching the origin as `Host`. |
| A redirect to a login page | Something in front of the server is intercepting requests. |
| `resource` differs from the URL users type | `--public-url` is wrong; it must match character for character. |

## Operate

```bash
journalctl -u odoo-mcp-http@$USER -n 80 --no-pager
odoo-mcp http grants
odoo-mcp http revoke <grant-id>
odoo-mcp http purge
```

## Back up

`~/.config/odoo-mcp/http-secret.key` decrypts the credentials in
`http-state.db`. Back them up together or neither: the database alone is
unreadable, which is the point, and losing the key means every connected user
has to sign in again.
