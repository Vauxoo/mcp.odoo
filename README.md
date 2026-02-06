# odoo-mcp-multi

MCP Server para conectar Claude/Cursor a múltiples instancias de Odoo via XML-RPC.

## Características

- **Gestión multi-perfil**: Almacena credenciales de múltiples entornos (prod, staging, dev)
- **Almacenamiento seguro**: Credenciales en `~/.config/odoo-mcp/` con permisos 600
- **7 herramientas MCP**: `search_read`, `write`, `create`, `execute_kw`, `list_models`, `list_fields`, `get_version`
- **CLI completo**: Gestión de perfiles y servidor MCP

## Instalación

```bash
# Usando pip
pip install .

# Usando uv
uv pip install .

# Modo desarrollo
pip install -e .
```

Después de instalar, el comando `odoo-mcp` estará disponible en tu PATH.

---

## Inicio Rápido

```bash
# 1. Agregar un perfil
odoo-mcp add-profile

# 2. Verificar conexión
odoo-mcp test -p prod

# 3. Iniciar servidor MCP
odoo-mcp run -p prod
```

---

## Comandos CLI

### `odoo-mcp add-profile`

Wizard interactivo para agregar credenciales de una instancia Odoo.

```bash
odoo-mcp add-profile
```

**Opciones:**
| Opción | Descripción |
|--------|-------------|
| `--name TEXT` | Identificador del perfil (ej: `prod`, `staging`) |
| `--url TEXT` | URL de la instancia (ej: `https://odoo.example.com`) |
| `--database TEXT` | Nombre de la base de datos |
| `--user TEXT` | Usuario de Odoo |
| `--password TEXT` | Contraseña (se oculta al escribir) |
| `--default` | Establecer como perfil por defecto |
| `--test / --no-test` | Probar conexión antes de guardar (default: `--test`) |

**Ejemplo no interactivo:**
```bash
odoo-mcp add-profile \
  --name prod \
  --url https://erp.miempresa.com \
  --database produccion \
  --user admin \
  --password secreto \
  --default
```

---

### `odoo-mcp list-profiles`

Muestra todos los perfiles configurados.

```bash
odoo-mcp list-profiles
```

**Opciones:**
| Opción | Descripción |
|--------|-------------|
| `--json` | Salida en formato JSON |

**Ejemplo de salida:**
```
Configured Profiles:
------------------------------------------------------------
  prod (default)
    URL:      https://erp.miempresa.com
    Database: produccion
    User:     admin

  staging
    URL:      https://staging.miempresa.com
    Database: staging_db
    User:     admin
```

---

### `odoo-mcp edit-profile`

Modifica un perfil existente. Solo los campos especificados serán actualizados.

```bash
odoo-mcp edit-profile NOMBRE [OPCIONES]
```

**Argumentos:**
| Argumento | Descripción |
|-----------|-------------|
| `NAME` | Nombre del perfil a editar (requerido) |

**Opciones:**
| Opción | Descripción |
|--------|-------------|
| `--url TEXT` | Nueva URL |
| `--database TEXT` | Nuevo nombre de base de datos |
| `--user TEXT` | Nuevo usuario |
| `--password` | Solicita nueva contraseña interactivamente |
| `--test` | Probar conexión después de editar |

**Ejemplos:**
```bash
# Cambiar solo la URL
odoo-mcp edit-profile prod --url https://nueva-url.com

# Cambiar usuario y contraseña
odoo-mcp edit-profile staging --user nuevo_admin --password

# Cambiar base de datos con prueba de conexión
odoo-mcp edit-profile dev --database nueva_db --test
```

---

### `odoo-mcp remove-profile`

Elimina un perfil por nombre.

```bash
odoo-mcp remove-profile NOMBRE
```

**Opciones:**
| Opción | Descripción |
|--------|-------------|
| `-f, --force` | Omitir confirmación |

**Ejemplo:**
```bash
odoo-mcp remove-profile staging -f
```

---

### `odoo-mcp set-default`

Establece el perfil por defecto.

```bash
odoo-mcp set-default NOMBRE
```

**Ejemplo:**
```bash
odoo-mcp set-default prod
```

---

### `odoo-mcp test`

Prueba la conexión a una instancia Odoo.

```bash
odoo-mcp test [-p PERFIL]
```

**Opciones:**
| Opción | Descripción |
|--------|-------------|
| `-p, --profile TEXT` | Perfil a usar (default: perfil por defecto) |

**Ejemplo:**
```bash
odoo-mcp test -p prod
# ✓ Connection successful! Authenticated as UID 2
#   Server version: 16.0
```

---

### `odoo-mcp run`

Inicia el servidor MCP para Claude/Cursor.

```bash
odoo-mcp run [-p PERFIL]
```

**Opciones:**
| Opción | Descripción |
|--------|-------------|
| `-p, --profile TEXT` | Perfil a usar (default: perfil por defecto) |

**Ejemplo:**
```bash
odoo-mcp run -p prod
# Starting MCP server with profile 'prod'...
#   URL: https://erp.miempresa.com
#   Database: produccion
#   User: admin
```

---

## Configuración de Clientes MCP

### Claude Desktop

Edita `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "odoo-mcp",
      "args": ["run", "-p", "prod"]
    }
  }
}
```

### Cursor

Edita `.cursor/mcp.json` en tu proyecto o globalmente:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "odoo-mcp",
      "args": ["run", "-p", "prod"]
    }
  }
}
```

---

## Herramientas MCP Disponibles

Una vez el servidor está corriendo, estas herramientas están disponibles para Claude/Cursor:

### `search_read`

Busca y lee registros de un modelo.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `model` | string | Nombre del modelo (ej: `res.partner`) |
| `domain` | string | Dominio de búsqueda (ej: `[('name', 'ilike', 'John')]`) |
| `fields` | string | Campos separados por coma (ej: `name,email,phone`) |
| `limit` | int | Máximo de registros (default: 100) |
| `offset` | int | Registros a saltar (default: 0) |
| `order` | string | Ordenamiento (ej: `name asc, id desc`) |

---

### `write`

Actualiza registros existentes.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `model` | string | Nombre del modelo |
| `ids` | string | IDs como JSON o separados por coma (ej: `[1,2,3]` o `1,2,3`) |
| `values` | string | Valores como JSON (ej: `{"name": "Nuevo Nombre"}`) |

---

### `create`

Crea un nuevo registro.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `model` | string | Nombre del modelo |
| `values` | string | Valores como JSON (ej: `{"name": "Alice", "email": "alice@example.com"}`) |

---

### `execute_kw`

Ejecuta cualquier método de un modelo Odoo.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `model` | string | Nombre del modelo |
| `method` | string | Nombre del método (ej: `action_confirm`, `send`) |
| `args` | string | Argumentos posicionales como JSON (ej: `[[42]]`) |
| `kwargs` | string | Argumentos keyword como JSON (ej: `{"force_send": true}`) |

---

### `list_models`

Lista los modelos disponibles en la instancia.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `search` | string | Filtro opcional por nombre del modelo |

---

### `list_fields`

Lista los campos de un modelo.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `model` | string | Nombre del modelo |

---

### `get_version`

Obtiene información de versión del servidor Odoo.

*Sin parámetros.*

---

## Ejemplos de Uso en Claude

> "Lista todos los contactos que contengan 'Juan' en el nombre"

```python
search_read(model="res.partner", domain="[('name', 'ilike', 'Juan')]", fields="name,email,phone")
```

> "Crea un nuevo contacto llamado Alice con email alice@example.com"

```python
create(model="res.partner", values='{"name": "Alice", "email": "alice@example.com"}')
```

> "Confirma el pedido de venta con ID 42"

```python
execute_kw(model="sale.order", method="action_confirm", args="[[42]]")
```

> "¿Qué campos tiene el modelo de facturas?"

```python
list_fields(model="account.move")
```

---

## Seguridad

- Las credenciales se almacenan en `~/.config/odoo-mcp/profiles.json`
- Los permisos del archivo se configuran como `600` (solo lectura/escritura del propietario)
- Las contraseñas se manejan con `SecretStr` para evitar logging accidental

---

## Desarrollo

```bash
# Instalar con dependencias de desarrollo
pip install -e ".[dev]"

# Ejecutar linting
ruff check odoo_mcp_multi/

# Formatear código
ruff format odoo_mcp_multi/
```

---

## Licencia

MIT
