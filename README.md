# parabol-docker

Container image for self-hosting [Parabol](https://github.com/ParabolInc/parabol), built from the official upstream release source. Not an official Parabol project.

This is a **modified version** of Parabol: the changes are the patches in [`patches/`](patches), their dates are in the git history.

```sh
docker pull ghcr.io/42bitgmbh/parabol:latest
```

Tags follow the upstream release (e.g. `v14.0.1`) plus `latest`, for `linux/amd64` and `linux/arm64`.

## Running

[`docker-compose.yml`](docker-compose.yml) is a working example with PostgreSQL and Valkey: `docker compose up -d`, then open http://localhost:3000. Replace the `change-me` values before using it for real.

Parabol needs PostgreSQL with pgvector, Redis/Valkey and its usual environment, see upstream's [`.env.example`](https://github.com/ParabolInc/parabol/blob/master/.env.example). The container refuses to start without `SERVER_SECRET`, `POSTGRES_HOST` and `REDIS_URL`, runs database migrations on start and listens on port 3000 as the `node` user.

Set `STATIC_ASSET_PATH=/static/` to load browser assets from whatever origin the browser used, while `HOST` stays the canonical hostname for links and emails.

## How it works

- `upstream.json` pins the upstream tag, commit and archive SHA-256.
- `scripts/prepare-source.py` downloads and verifies that archive, applies `patches/` and adds `overlay/` (Dockerfile, build script, entrypoint).
- `patches/0001` lets the build run without git metadata, `patches/0002` adds `STATIC_ASSET_PATH`.

Build locally:

```sh
python3 scripts/prepare-source.py --output .context
docker build -f .context/docker/selfhost/Dockerfile .context
```

`scripts/test.sh` runs the quick checks (Python 3.11+, Node 24).

## Updates

A daily workflow checks for new stable Parabol releases. When one appears it opens a pull request bumping `upstream.json` and starts a test build on it. Read the release notes, approve and merge: the merge builds and publishes the new image. If the build fails, the patches need updating on that branch.

For this to work, enable **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests**.

## License

Parabol is licensed under the [GNU AGPL-3.0](https://github.com/ParabolInc/parabol/blob/master/LICENSE), and so is the published image as a whole. This repository is its Corresponding Source. The build scripts here are MIT licensed (see [LICENSE](LICENSE)).

If you run this image as a service for others, the AGPL (section 13) requires offering those users the source of this modified version, for example by linking to this repository.
