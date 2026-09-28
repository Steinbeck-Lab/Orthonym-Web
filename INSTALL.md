# Installing and running Orthonym

Everything operational lives here: how to run it, how to deploy it, how to test it, and what the
engine dependency actually requires. The [README](README.md) is the short version.

> **Before anything else.** This repository does not contain the naming engine. The backend
> installs it from the `main` branch of
> [Steinbeck-Lab/Orthonym](https://github.com/Steinbeck-Lab/Orthonym) — see
> [The Orthonym engine dependency](#the-orthonym-engine-dependency).
>
> Deploying to a server? [Deploying it publicly](#deploying-it-publicly) is a step-by-step
> runbook for an Ubuntu VM behind Caddy, and it starts from that same clone.

## Contents

- [Run with Docker (recommended)](#run-with-docker-recommended)
- [Deploying it publicly](#deploying-it-publicly)
- [Run locally without Docker](#run-locally-without-docker)
- [Tests](#tests)
- [The batch/job API](#the-batchjob-api)
- [The Orthonym engine dependency](#the-orthonym-engine-dependency)
- [Stopping](#stopping)

---

## Run with Docker (recommended)

```bash
docker compose up -d --build
```

Five containers come up: `redis`, `backend`, `worker-fast`, `worker-batch`, `frontend`.

- Frontend: http://localhost:8080
- Backend: http://127.0.0.1:8000 (docs at `/docs`) — loopback only, on purpose; see the comment
  block in `docker-compose.yml`, where the port binding and `TRUST_PROXY_HEADERS` are a pair and
  neither is safe alone.

**Wait for a worker before testing.** The workers each boot a JVM and then record that they have one.
Until at least one has, naming is refused:

```bash
curl -s http://127.0.0.1:8000/api/health

## Deploying it publicly

A concrete runbook for a **4-core / 16 GB Ubuntu VM with Docker already installed**, behind
**Caddy** for HTTPS. Substitute your own hostname for `orthonym.example.org` throughout.

Everything below assumes the DNS `A`/`AAAA` record for that hostname already points at the VM —
Caddy will not be able to get a certificate until it does.

### 1. Get the code

```bash
sudo apt-get update && sudo apt-get install -y git

# /opt is root-owned, so take ownership BEFORE cloning rather than cloning with
# sudo -- a root-owned tree makes every later `git pull` and `docker compose`
# need sudo too, and mixes root-written files into a directory you then edit.
sudo mkdir -p /opt/orthonym-web && sudo chown "$USER:$USER" /opt/orthonym-web
git clone https://github.com/Steinbeck-Lab/Orthonym-Web.git /opt/orthonym-web
cd /opt/orthonym-web

# "Docker is installed" does not mean your user may talk to it. If this prints
# the hint, run it and start a new login shell (`newgrp docker` for this one).
docker ps >/dev/null 2>&1 || echo "run: sudo usermod -aG docker $USER  -- then log out and back in"
```

The engine, CDK, OPSIN and centres are **not** needed here: the backend image build downloads
all four and SHA-checks the three jars.

### 2. Configure

```bash
cp .env.example .env
```

For a 4-core / 16 GB box the shipped defaults are already the `medium` profile, so the only line
that must change is the proxy trust — and it is already correct at `true` for this topology.
Read `.env` once and confirm:

| key | value for this VM | why |
|---|---|---|
| `DEPLOYMENT_PROFILE` | `medium` | 2 + 2 workers, 10,000-molecule batches, 50 MB uploads |
| `TRUST_PROXY_HEADERS` | `true` | correct **only** because the backend is loopback-published |
| `WORKER_MEM_LIMIT` | `3g` | 512 MB JVM × 2 children + parent ≈ 2.3 GB, with headroom |
| `REDIS_MEM_LIMIT` | `3g` | must stay **above** `REDIS_MAXMEMORY` (2 GB), never equal |

Total steady-state footprint is roughly 8 GB, which leaves the box half free.

### 3. Build and start

The first build downloads a JRE, RDKit and two jars, so allow ten minutes or so.

```bash
docker compose up -d --build
docker compose ps                     # every service should reach (healthy)
```

The workers each boot a JVM before they report ready. Until one has, naming is refused
deliberately rather than answered without verification:

```bash
curl -s http://127.0.0.1:8000/api/health
# {"status":"OK","opsin":"available"}   <- ready
# {"status":"DEGRADED",...}             <- still starting, or check `docker compose logs worker-fast`
```

Confirm the site itself answers on loopback — it is **not** reachable from outside yet, by
design:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/     # 200
```

### 4. Choose a front door

**First work out whether this VM is reachable from the internet at all.** On an institutional
network it very often is not, and everything below depends on the answer:

```bash
ip -4 addr show scope global | grep inet          # a 10./172.16-31./192.168. address means NAT
curl -4 -s ifconfig.me; echo                      # egress address -- NOT proof of ingress
dig +short <a-sibling-service-you-run>            # where do your OTHER services resolve to?
```

If the VM has only private IPv4 and your other services resolve to some shared address, there
is already a reverse proxy in front of everything and **that is your front door** — skip to 4b.
Egress working proves nothing about ingress: a NAT gateway lets you out without letting anyone in.

#### 4a. Caddy on this VM — only if it holds a public address

Caddy is **not** in Ubuntu's default repositories — `apt-get install caddy` on a stock box

Caddy is **not** in Ubuntu's default repositories — `apt-get install caddy` on a stock box
either fails or installs something years old. Add the official repo first (these four lines are
from Caddy's own install docs):

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy
```

Then replace `/etc/caddy/Caddyfile` with:

```caddyfile
orthonym.example.org {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8080
}
```

That is the whole file. Caddy provisions and renews the certificate itself, and sets
`X-Forwarded-For` by default — which matters more than it looks: `app/ratelimit.py` counts per IP
using the address nginx derives from that header, so without it every visitor on the internet
would share **one** bucket of 2 concurrent jobs and 60 requests a minute.

```bash
sudo systemctl reload caddy
sudo systemctl enable --now caddy
```

#### 4b. An institutional reverse proxy on another host

This is the common case on a university network, and it is the better answer when it applies:
certificate issue and renewal, TLS policy and security headers are handled centrally by the
people who already do that for every other service.

Ask that team for a vhost. They need three things from you:

| | |
|---|---|
| hostname | `orthonym.example.org` |
| upstream | `http://<this VM's internal IP>:8080` |
| must forward | `Host`, `X-Forwarded-For`, `X-Forwarded-Proto` |

Then **bind the frontend to the internal interface**, or their proxy gets a connection refused
and serves a 502 — the container listens on loopback by default:

```bash
echo 'FRONTEND_BIND=10.0.0.5' >> .env        # this VM's internal address
docker compose up -d
docker ps --format '{{.Names}}\t{{.Ports}}' | grep frontend   # expect 10.0.0.5:8080->80/tcp
curl -s -o /dev/null -w '%{http_code}\n' http://10.0.0.5:8080/
```

Use the **address, not `0.0.0.0`**. A VM with private IPv4 may still hold a globally routable
IPv6, and `0.0.0.0` binds that too — publishing the site unencrypted to the internet, past the
proxy holding your certificate. Worth testing rather than assuming:
`curl -6 -sI http://[<your-v6>]/`.

Two things to check in the vhost they write:

- **`client_max_body_size`** must be at least as large as `MAX_FILE_SIZE_MB` (50 on `medium`).
  A smaller value rejects uploads the app would have accepted, with a bare nginx 413 instead of
  the app's own JSON error.
- **Whose address reaches you.** `frontend/nginx.conf` trusts `X-Forwarded-For` only from
  RFC1918 and loopback peers. If their proxy connects from a *public* address, the header is
  discarded and every visitor collapses into one rate-limit bucket. Verify with the Redis check
  in step 6, and add their address to `set_real_ip_from` if needed.

If you took this route, remove Caddy — it will contend for ports 80/443 on the next reboot:

```bash
sudo systemctl disable --now caddy && sudo apt-get purge -y caddy
```

### 5. Firewall

**Route 4a (Caddy here):** only 80 and 443 need to be open. Nothing else should be reachable —
the frontend is on `127.0.0.1:8080`, the backend on `127.0.0.1:8000`, Redis on `127.0.0.1:6379`.

**Route 4b (proxy elsewhere):** 80 and 443 should stay **closed**. The only thing that needs to
reach this VM is the proxy, on 8080, from its address alone.

```bash
sudo ufw allow OpenSSH

# route 4a -- this VM terminates TLS itself:
sudo ufw allow 80,443/tcp

# route 4b instead -- let ONLY the proxy in, and only to the app port:
#   sudo ufw allow from <proxy-ip> to any port 8080 proto tcp

sudo ufw enable
```

### 6. Verify from outside

Run these from your laptop, not the VM — the point is to test the path a visitor takes.

```bash
curl -sI https://orthonym.example.org | head -3                    # 200, and a valid cert
curl -s  https://orthonym.example.org/api/health                   # {"status":"OK",...}

# the round-trip gate, end to end: ethanol must be `pin`, the fused polycyclic `fallback`
curl -s -X POST https://orthonym.example.org/api/translate \
  -H 'Content-Type: application/json' \
  -d '{"smiles":["CCO","COC1C2=C(C)C(=O)OC2CC2CCC(O)C(C)C21C"]}' | head -c 400
```

**Confirm the rate limiter sees real client addresses.** If this shows one shared bucket instead
of per-visitor ones, `X-Forwarded-For` is not reaching the app and every cap is effectively void:

```bash
# on the VM, after making a request from your laptop
docker exec orthonym-redis redis-cli --scan --pattern 'orthonym:ip:*' | head
# expect your laptop's public IP in the key name -- NOT 127.0.0.1 or a 172.x address
```

### Putting the site behind a password

For a preview, or while a deployment is being checked, the whole site can sit behind HTTP Basic
Auth. Do it here rather than asking whoever runs the upstream proxy — nothing needs to change
outside this VM, and it lifts in one command.

```bash
cd /opt/orthonym-web
mkdir -p ops/snippets

# the credential. openssl is already present; apache2-utils is not needed.
printf 'orthonym:%s\n' "$(openssl passwd -apr1 'CHOOSE-A-PASSWORD')" > ops/htpasswd
chmod 600 ops/htpasswd

cat > ops/snippets/auth.conf <<'EOF'
satisfy any;
allow 127.0.0.1;
allow ::1;
deny all;
auth_basic "Orthonym — preview";
auth_basic_user_file /etc/nginx/htpasswd;
EOF

cat > docker-compose.override.yml <<'EOF'
services:
  frontend:
    volumes:
      - ./ops/snippets:/etc/nginx/snippets:ro
      - ./ops/htpasswd:/etc/nginx/htpasswd:ro
EOF

docker compose up -d frontend
```

Compose picks `docker-compose.override.yml` up automatically, and `ops/` is gitignored, so no
credential reaches the repository.

`satisfy any` with `allow 127.0.0.1` is the part that is easy to get wrong. The container's own
healthcheck requests `http://127.0.0.1/`; a bare `auth_basic` answers it with a 401, the
container is marked **unhealthy**, and compose then treats a perfectly working site as broken.
The allow rule exempts that one caller and nobody else — `set_real_ip_from` has already
rewritten `$remote_addr` to the visitor's real address by the time this is evaluated, so a
visitor can never match it.

Verify all four, not just the first:

```bash
curl -s -o /dev/null -w 'no creds:   %{http_code}\n' http://10.232.0.68:8080/          # 401
curl -s -u orthonym:PASS -o /dev/null -w 'with creds: %{http_code}\n' http://10.232.0.68:8080/   # 200
curl -s -o /dev/null -w 'api gated:  %{http_code}\n' http://10.232.0.68:8080/api/health # 401
sleep 12; docker inspect --format 'health: {{.State.Health.Status}}' orthonym-frontend    # healthy
```

**To remove it**, which is the point of doing it this way:

```bash
rm -f docker-compose.override.yml && docker compose up -d frontend
```

Two limits worth knowing. Basic Auth sends the password on every request — fine over the HTTPS
the upstream proxy terminates, useless over plain HTTP. And it is a gate, not access control:
one shared credential, no accounts, no audit. It suits "not ready for the public yet"; it does
not suit protecting anything sensitive.

### 7. Updating

```bash
cd /opt/orthonym-web && git pull
docker compose up -d --build
```

The build installs the engine from its `main` branch. Docker reuses the engine layer while `main`
has not moved and reinstalls it when it has, so this one command also picks up engine changes.
The shared name cache clears itself: `backend/app/name_cache.py` keys every name on a fingerprint
of the installed engine source.

If a new engine commit breaks the build at the SELF-01 check (`verify_opsin_live.py` names every
Home example and asserts its tier), build the last good commit until the example is fixed:

```bash
docker compose build --build-arg ORTHONYM_REF=<full 40-character commit SHA>
docker compose up -d
```

**An install cloned before 2026-09-24** cannot `git pull`: the repository's history was rewritten
that day. Update it in place instead, which keeps every gitignored file (`.env`,
`docker-compose.override.yml`, `ops/`). Stop the stack first:

```bash
docker compose down
git status --short          # a local edit to a tracked file (frontend/nginx.conf?) is lost below: save it
git fetch origin && git reset --hard origin/main
```

Then compare `.env` with `.env.example` for any setting added since, and run
`docker compose up -d --build`. An old `backend/vendor/orthonym/` or `backend/vendor/opsin-resources/`
is no longer used and can be deleted.

### What runs, and what it costs

| service | role | memory cap |
|---|---|---|
| `frontend` | nginx serving the SPA, proxying `/api` | 256 MB |
| `backend` | FastAPI web process (2 uvicorn workers) | 1.5 GB |
| `worker-fast` | interactive naming, holds a JVM per child | 3 GB |
| `worker-batch` | batch jobs, holds a JVM per child | 3 GB |
| `redis` | broker, job store, name cache, rate limits | 3 GB |

All five restart automatically (`restart: unless-stopped`) and each is capped at 10 MB × 3 log
files, so an unattended box cannot fill its disk with worker logs.

## Run locally without Docker

You need **four** processes, not two. Redis first:

```bash
docker compose up -d redis    # container orthonym-redis, publishes localhost:6379
```

```bash

## Tests

```bash
docker compose up -d redis           # required — the suite fails with instructions without it
backend/scripts/run-tests.sh         # whole suite
backend/scripts/run-tests.sh tests/test_inputs.py -v
```

**Do not run a bare `pytest`.** JPype's JVM refuses to let the process exit, so a bare run looks like
a 10-minute hang ending in exit 144 — *after* it has already printed a correct summary. The script
waits for pytest's own summary line, kills the corpse, and exits `0` (passed) / `1` (failed) /
`2` (a real hang).

## The batch/job API

There is **no frontend UI for this yet**; it is reachable over the API.

| Endpoint | Purpose |
|---|---|
| `POST /api/jobs` | Upload `.sdf`, `.mol`, `.csv` (needs a `smiles` column), or a plain SMILES list |
| `POST /api/parse-preview` | Count an upload and sample-check its first few records, without dispatching it. Not a full validation — an empty `errors` means the sample was clean, not the file |
| `GET /api/jobs/{id}` | Progress |
| `GET /api/jobs/{id}/results` | Paged rows |
| `GET /api/jobs/{id}/results.csv` | Streamed CSV of the whole job |
| `POST /api/jobs/{id}/cancel` | Stop a running job and free its concurrent slot |
| `DELETE /api/jobs/{id}` | Discard a finished job |

**Cancel and delete need the job's `owner_token`**, returned once in the response that created
the job. A results URL carries the job id but not the token, so sharing results does not hand over
the ability to delete them. Pass it as a query parameter:
`POST /api/jobs/{id}/cancel?owner_token=...`.

Cancellation is cooperative: chunks not yet started stop immediately, and one already running
finishes that chunk (at most `BATCH_CHUNK_SIZE` molecules) because a running task cannot be
interrupted mid-molecule.

Upload size and molecule count **are** profile-dependent: **2,000 molecules / 20 MB** (`small`),
**10,000 / 50 MB** (`medium`, the default), **50,000 / 200 MB** (`large`).

Everything else is a code default, **not** profile-driven, though each is overridable by
environment variable: results live **24 h**, the shared name cache lives **7 days**, and the per-IP
caps are **2** concurrent jobs, **20** jobs/hour, **60** naming requests/min, **300** polls/min,
**1200** depictions/min.

## The Orthonym engine dependency

The Orthonym engine lives in its own repository,
[Steinbeck-Lab/Orthonym](https://github.com/Steinbeck-Lab/Orthonym). It is not on PyPI, so it is
installed from GitHub `main`:

- **Locally**, `backend/requirements.txt` has
  `orthonym @ git+https://github.com/Steinbeck-Lab/Orthonym.git@main`. Re-run
  `pip install --force-reinstall --no-deps "orthonym @ git+https://github.com/Steinbeck-Lab/Orthonym.git@main"`
  to pick up a newer commit; pip does not do that on its own for an unchanged git URL.
- **In the image**, `backend/Dockerfile` fetches the engine with a BuildKit git source
  (`ADD https://github.com/Steinbeck-Lab/Orthonym.git#${ORTHONYM_REF}`) and installs that tree.
  BuildKit resolves the ref to a commit on each build, so a rebuild picks up a new `main` and reuses
  the cached layer when `main` has not moved. `--build-arg ORTHONYM_REF=<full SHA>` builds another
  commit.

Because it tracks `main`, an engine push can change a name or a tier without a commit here. Two
gates catch that: the SELF-01 check at the end of the image build, and the backend CI job.

The engine does not ship its jars. It downloads the pinned **OPSIN 2.9.0** and **centres 1.2.1**
jars from their official releases and checks each against a SHA-256 (`orthonym/jars.py`), into
`$ORTHONYM_JAR_DIR` (the image sets `/opt/orthonym/jars`) or else `~/.cache/orthonym/jars`. The
install prefetches them on a best-effort basis; `orthonym --fetch-jars` fetches them and fails when
it cannot. The Dockerfile runs it, so a missing jar fails the build.

**CDK** is fetched by the app, not by the engine: `backend/Dockerfile` downloads it during the build
and checks it against the SHA-256 recorded in `backend/vendor/cdk/NOTICE`, which is tracked.
`backend/.dockerignore` keeps `backend/vendor/` out of the build context, so a build here exercises
the same download path a fresh clone does. Outside Docker, download it into `backend/vendor/cdk/`
the same way (the commands are in `.github/workflows/ci.yml`).

### The part that isn't optional: SELF-01 needs a real JVM

Without a live JVM (jpype + a JRE) and the OPSIN and centres jars, the Orthonym engine's SELF-01 self-consistency gate — the check that verifies a candidate name actually round-trips back to the right structure — silently **fails open**: confirmed by direct testing, a molecule that should honestly report as a lower-confidence `fallback` instead shipped as a `pin` nothing had checked. `JPype1` is in `requirements.txt` and `backend/Dockerfile` installs `default-jre-headless` for exactly this reason. If you ever strip either out "to slim the image," re-run the regression check below first.

That failure mode is why `app/jvm_guard.py` refuses rather than degrades: if no worker reports a live
JVM, every naming endpoint — including `POST /api/jobs` — returns 503 instead of serving names whose
confidence tier nothing has checked.

### The third jar: CDK draws every picture

`backend/vendor/cdk/cdk-2.12.jar` (42 MB, LGPL — see its `NOTICE`), downloaded as above, is the **default depiction
engine**. It annotates **CIP stereo descriptors** onto the drawing — `(R)`/`(S)`, `(E)`/`(Z)`, and
`(?)` for a stereocentre the input leaves undefined — which is the reason it replaced RDKit's
drawing. RDKit remains the fallback for any process where the JVM will not come up. CDK is also a
**second SMILES parser**: a string RDKit refuses is offered to it before the input is called
unreadable.

It is **not on the JVM's classpath**, and cannot be: the Orthonym engine owns the only `startJVM` call and
boots with a fixed one. `app/cdk_bridge.py` loads it in an isolated `java.net.URLClassLoader`
instead — read that module's docstring before changing anything about it, especially the parent
loader and the URL order, both of which are load-bearing and both of which fail in ways that look
like something else.

**`default-jre-headless` alone is not enough for this**, and the way it fails is the point:
`fontconfig`, `libfreetype6`, `libharfbuzz0b` and `fonts-dejavu-core` must be installed too, or
`libfontmanager.so` cannot load, only the *draw* step dies, and the app silently serves RDKit
pictures with no stereo labels. Nothing looks broken from the outside. `backend/Dockerfile`
installs all four.

**Regression check for CDK** (run it after any jar bump, JRE change, or image slimming):

```bash
docker compose run --rm --entrypoint sh backend -c \
  'python -c "from app import cdk_bridge as c; print(c.self_check(), c.cip_labels(\"C[C@H](N)C(=O)O\"))"'

## Stopping

```bash
docker compose down
```
