# config.example/ — the template for config/

The stack is configured from one directory:

| directory | used by | in git |
|---|---|---|
| `config.local/` | `docker-compose.local.yml` (development) | yes — it holds only the dev database password |
| `config/` | `docker-compose.yml` (production), copied to the server by `app/scripts/deploy.sh` | **no** — git-ignored |
| `config.example/` | nobody; the template for `config/` | yes |

Each holds six files:

| file | read by | |
|---|---|---|
| `options.yaml` | the app (`lib/config.py`) | the deployment layer of the options (YAML): anything in `app/config/options.yaml` can be set here, and a key that is not an option there is refused. |
| `postgres.env` | postgres and the app, through compose's `env_file` | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: postgres creates the database from them, `lib/config.py` hands them to libpq |
| `postgresql.conf` | postgres (`config_file=`) | the whole server configuration |
| `pg_hba.conf` | postgres (`hba_file=`, set in `postgresql.conf`) | client authentication |
| `pgbouncer.ini` | pgbouncer | the connection pooler the app reaches postgres through; `trust` for its clients, so it must stay unreachable from outside (DESIGN.md "Deployment") |
| `Caddyfile` | caddy | production: TLS for `host`. Development: plain http on 8004, `--profile caddy` |

## Setting up config/

```sh
cp -r config.example config
chmod 600 config/options.yaml config/postgres.env
```

Then, in `config/options.yaml`: `host`, `serve_area`, and real `keys` (a random string
each; `scopes` from `search`, `tiles`). In `config/postgres.env`: a new strong
`POSTGRES_PASSWORD`. Every `CHANGEME` must go.
In `config/Caddyfile`: the same host as the site address, and the ACME `email`. Size
`shared_buffers` and friends in `config/postgresql.conf` for the host.

`deploy.sh` refuses to build until all of that is done.

## Two things that are easy to get wrong

- **`POSTGRES_PASSWORD` is applied to the database once**, when postgres initialises an empty
  `pgdata`. Changing it later changes what the app connects with and nothing else; change
  the role as well:
  `docker compose exec postgres psql -U geoservices -c "ALTER ROLE geoservices PASSWORD '...'"`.
- **Caddy cannot read `options.yaml`**, and is not given it — it is the container facing the
  internet, and `options.yaml` holds the API keys. So the host name is in both files, and
  `deploy.sh` checks they agree.

`deploy.sh` only copies these files. The server reads `options.yaml` on `manage.sh
reload`, which recreates the app and nothing else; the others -- `postgres.env`,
`postgresql.conf`, `pg_hba.conf`, `pgbouncer.ini`, `Caddyfile` -- on `manage.sh restart`,
which stops the whole stack and starts it again.
