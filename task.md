Unten ist ein **konzeptioneller Entwurf** für ein Python‑CLI, das mithilfe des *Claude Code SDK* ein `Makefile.claude` sowie ein daraus abgeleitetes `Makefile.build` für ein beliebiges GitHub‑Repository erzeugt. Es liest Anleitungen (README/Docs), **analysiert die GitHub‑Actions**‑Workflows, **baut daraus ein Build‑Environment** – bevorzugt mit **Docker/Docker Compose** – und generiert robuste Make‑Targets für **build / start / test**.

> Relevante Grundlagen aus der Doku (kurz):
> – *Headless/Non‑interactive*: `claude -p "…" --allowedTools …` für automatisierbare Pipeline-Aufgaben. ([Anthropic][1])
> – *Python‑SDK*: `ClaudeSDKClient`, `ClaudeCodeOptions`, `allowed_tools`, `permission_mode`, `cwd`, Streaming‑Antworten. ([Anthropic][2])
> – *GitHub Actions*: Workflows liegen in `.github/workflows`, können mit REST API gelistet/gelesen werden. ([GitHub Docs][3])
> – *Docker Compose*: Bevorzugte Datei **`compose.yaml`** (alternativ `compose.yml`), ältere `docker-compose.yml` weiterhin unterstützt. Compose‑CLI via `docker compose …`. ([Docker Documentation][4])

---

## 1) Zielbild

**CLI‑Name:** z. B. `claumake`

**Output‑Artefakte:**

* `Makefile.claude` – *Automations-Makefile*, dessen Targets den `claude`‑CLI in Headless‑Mode mit passenden Tools/Prompts aufrufen (Recherche, Analyse, Generierung). ([Anthropic][1])
* `Makefile.build` – *konkrete Build‑Targets* (Shell/Docker/Compose‑Befehle) für lokale Nutzung/CI.
* `.claude/plan.json` – strukturierter Build‑Plan (Zwischenformat).
* Optional: `compose.yaml` + `Dockerfile` (falls nicht vorhanden, werden Vorschläge/Entwürfe generiert).

---

## 2) High‑Level‑Ablauf (Datenfluss)

1. **Repository erfassen**

   * Eingabe: GitHub‑URL, optional Branch/Path.
   * Klonen (shallow) in ein Temp‑Verzeichnis, `cwd` auf Repo‑Root setzen.

2. **Kontext sammeln**

   * Lesen von `README*`, `docs/**`, `CONTRIBUTING*`, `INSTALL*`.
   * Scannen nach Build‑Artefakten: `compose.yaml|yml`, `docker-compose.*`, `Dockerfile*`, `Makefile`, Sprach‑Manifeste (`package.json`, `pyproject.toml`, `requirements.txt`, `pom.xml`, `build.gradle`, `go.mod`, `Cargo.toml` etc.).
   * **GitHub‑Actions analysieren:** alle YAMLs in `.github/workflows` parsen (oder via REST API listen & laden). Ziel: Laufzeit‑Matrix, Setup‑Schritte (z. B. `actions/setup-node`, `setup-python`), Build/Test‑Kommandos aus `run:` Schritten extrahieren. ([GitHub Docs][3])

3. **Heuristiken anwenden**

   * **Sprache/Framework** anhand Manifeste/Dateien bestimmen.
   * **Docker/Compose** bevorzugen: existiert `compose.yaml`? Wenn ja: Services/Ports übernehmen; andernfalls aus `Dockerfile` + Heuristiken eine minimale Compose‑Definition erzeugen. **Modernes Standard‑Naming:** `compose.yaml` bevorzugen. ([Docker Documentation][4])
   * Ports aus Dockerfile (`EXPOSE`) bzw. Framework‑Defaults ableiten.
   * Build/Test‑Kommandos aus Workflows + README abgleichen.

4. **Claude‑gestützte Synthese**

   * Den gesammelten Kontext + extrahierte Signale an **Claude Code** geben, mit Tools **Read/WebSearch/Bash/Write** (je nach Modus). Headless‑Aufruf liefert deterministisch **JSON (Build‑Plan)**. ([Anthropic][1])
   * JSON→`Makefile.build` Generator setzt die Targets **build/start/test** (und ergänzend `lint`, `fmt`, `clean`, `compose-up/-down`, `help`).
   * Zusätzlich erzeugt die CLI ein **`Makefile.claude`** mit Targets, die den `claude`‑CLI erneut nutzen, um Recherche/Regeneration reproduzierbar auszuführen (z. B. `make plan`, `make refine`).

5. **Optionale Artefakt‑Generierung**

   * Falls **kein** Compose vorhanden: `compose.yaml` + `Dockerfile` schreiben (oder als Patch‑Vorschlag ablegen). Compose wird via `docker compose` angesprochen. ([Docker Documentation][5])

---

## 3) CLI‑Schnittstelle

Beispiel:

```bash
claumake \
  --repo https://github.com/org/repo \
  --branch main \
  --prefer-compose \
  --out . \
  --model claude-*-sonnet-latest \
  --max-turns 6 \
  --permission acceptEdits \
  --websearch on \
  --no-exec   # (optional) führt keine erzeugten build/test-Kommandos aus
```

**Environment:** `ANTHROPIC_API_KEY` muss gesetzt sein (oder Cloud‑Provider‑Modus), siehe SDK‑Auth. ([Anthropic][6])

---

## 4) Kernkomponenten (Modulskizze)

```
claumake/
  cli.py               # Argumente, Orchestrierung
  repo/clone.py        # Git clone / Sparse checkout
  scan/context.py      # README/docs, Manifeste, Docker/Compose, Makefile
  scan/actions.py      # .github/workflows/*.yml analysieren / REST-Fallback
  analyze/heuristics.py# Sprache/Framework/Ports/Kommandos ableiten
  llm/claude.py        # ClaudeSDKClient + Prompt/JSON-Streaming
  plan/schema.py       # Pydantic-Schemas für BuildPlan
  gen/makefile.py      # Makefile.build + Makefile.claude schreiben
  gen/compose.py       # compose.yaml & Dockerfile (falls nötig)
```

---

## 5) Claude‑Integration (robust & reproduzierbar)

### 5.1 Python‑SDK (empfohlen im Script)

* **`ClaudeSDKClient`** mit `ClaudeCodeOptions`: `system_prompt`, `allowed_tools`, `permission_mode`, `cwd`, `max_turns`. Streaming lesen, **JSON‑Output** erzwingen. ([Anthropic][2])

**Beispielschnipsel:**

```python
# llm/claude.py
import asyncio, json
from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions

SYSTEM_PROMPT = """Du bist DevOps-/Build-Engineer. ...
Gib ausschließlich JSON gemäß dem Schema 'BuildPlan' zurück."""

OPTIONS = ClaudeCodeOptions(
    system_prompt=SYSTEM_PROMPT,
    allowed_tools=["Read","WebSearch","Write","Bash"],
    permission_mode="acceptEdits",   # schreibt Dateien im cwd, wenn angewiesen
    cwd=str(repo_root),              # Repo-Working-Dir
    max_turns=6,
    # model, settings etc. über CLI-Flags injizierbar
)

async def synthesize_plan(context_markdown: str) -> dict:
    async with ClaudeSDKClient(options=OPTIONS) as client:
        await client.query(context_markdown)
        result_text = ""
        async for msg in client.receive_response():
            # sammle nur Textblöcke (oder nutze 'json' Output-Format)
            if getattr(msg, "content", None):
                for block in msg.content:
                    if hasattr(block, "text"):
                        result_text += block.text
        return json.loads(result_text)  # erzwinge valides JSON im Prompt
```

*(Die SDK‑Seite zeigt die Klassen und Parameter; Headless/CLI‑Flags sind ebenfalls verfügbar.)* ([Anthropic][2])

### 5.2 Headless‑CLI (im erzeugten `Makefile.claude`)

**Nicht‑interaktive** Aufrufe via `claude -p … --output-format json --allowedTools "Read,WebSearch,Write,Bash" --permission-mode acceptEdits --cwd <repo>`. ([Anthropic][1])

---

## 6) Prompting & Schema

**Schema (vereinfacht):**

```json
{
  "version": "1",
  "language": "node|python|java|go|rust|mixed|unknown",
  "compose": {
    "present": true,
    "file": "compose.yaml",
    "services": [{"name":"app","build":"./","ports":["3000:3000"],"env":["..."]}]
  },
  "dockerfile": {"present": true, "path": "Dockerfile"},
  "commands": {
    "build": ["docker compose build"],
    "start": ["docker compose up -d"],
    "test":  ["docker compose run --rm app npm test"]
  },
  "notes": ["... rationale ..."]
}
```

**System‑Prompt (Auszug):**

* Lies **README/Docs**, **parste** `.github/workflows/*.yml`, trianguliere Build/Test‑Kommandos.
* **Bevorzuge Docker Compose** (`compose.yaml` bevorzugt) und erzeuge Vorschläge, falls nicht vorhanden. Liefere **nur** JSON im obigen Schema. ([Docker Documentation][4])

---

## 7) Analyse der GitHub‑Actions (Details)

* Dateien in `.github/workflows` laden & parsen (YAML). Existieren keine lokalen Files, verwende **GitHub REST**:
  – *List Workflows*: `GET /repos/{owner}/{repo}/actions/workflows` (IDs/Dateinamen).
  – *Get Content*: `GET /repos/{owner}/{repo}/contents/.github/workflows/<file>` (Base64‑Inhalt). ([GitHub Docs][7])

**Extraktion:**

* `jobs.*.steps[].run` aggregieren → Suche nach Befehlen wie `npm ci && npm test`, `pytest`, `mvn -B test`, `go test ./...`, `cargo test`.
* `uses: actions/setup-*` → Runtimes/Versionen ableiten (z. B. Node 20, Python 3.12).
* `services:` in Workflows → abhängige Dienste (DB/Cache) → Compose‑Services vorschlagen.

---

## 8) Makefiles, die generiert werden

### 8.1 `Makefile.build` (Template, Compose‑first)

```make
SHELL := /bin/bash
COMPOSE ?= docker compose
SERVICE ?= app

.PHONY: help build start stop logs test lint fmt clean compose-up compose-down

help:
	@echo "Targets: build start stop logs test lint fmt clean compose-up compose-down"

build:
	$(COMPOSE) build

start:
	$(COMPOSE) up -d

stop:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f $(SERVICE)

test:
	$(COMPOSE) run --rm $(SERVICE) npm test       # wird aus Plan gesetzt (Sprache/Stack-spezifisch)

lint:
	$(COMPOSE) run --rm $(SERVICE) npm run lint   # optional je nach Plan

fmt:
	$(COMPOSE) run --rm $(SERVICE) npm run fmt    # optional je nach Plan

clean:
	git clean -xfd -e node_modules -e .venv

compose-up: start
compose-down: stop
```

> Falls kein Compose existiert, schreibt der Generator (je nach Sprache) minimal:
> – Node: Basisimage `node:XX-alpine`, Arbeitsdir `/app`, `npm ci`, Port 3000.
> – Python: `python:3.12-slim`, `pip install -r requirements.txt`, Port aus Framework/ENV.
> – … (Heuristiken, siehe Abschnitt 3).

### 8.2 `Makefile.claude` (Headless‑Automationen)

```make
SHELL := /bin/bash
CLAUDE ?= claude
ALLOWED := "Read,WebSearch,Write,Bash"
PERM := acceptEdits
CWD := $(PWD)

.PHONY: plan refine regenerate update-compose explain

plan:
	$(CLAUDE) -p "Erstelle einen BuildPlan als valides JSON (Schema BuildPlan). \
	Lies README/docs und .github/workflows, bevorzuge Docker Compose." \
	 --output-format json --allowedTools $(ALLOWED) --permission-mode $(PERM) --cwd $(CWD) \
	 | jq -r '.result // . | tostring' > .claude/plan.json

refine:
	$(CLAUDE) -p "Überarbeite den vorliegenden BuildPlan (.claude/plan.json) auf Basis \
	neuer Erkenntnisse. Liefere nur JSON." \
	 --output-format json --allowedTools $(ALLOWED) --permission-mode $(PERM) --cwd $(CWD) \
	 | jq -r '.result // . | tostring' > .claude/plan.json

regenerate:
	python -m claumake.gen.makefile --plan .claude/plan.json --out .

update-compose:
	$(CLAUDE) -p "Wenn kein compose.yaml existiert, generiere eine minimal lauffähige Compose-Datei \
	(services: app, ports, env). Schreibe die Datei und erkläre kurz die Annahmen." \
	 --allowedTools $(ALLOWED) --permission-mode $(PERM) --cwd $(CWD)

explain:
	$(CLAUDE) -p "Erkläre kurz die Build-/Test-Ströme aus Workflows & README." \
	 --print --allowedTools "Read" --cwd $(CWD)
```

> Die Nutzung von `claude -p` im **non‑interactive/headless**‑Modus, inkl. `--allowedTools`, `--permission-mode` und JSON‑Output, folgt der offiziellen Doku. ([Anthropic][1])

---

## 9) Heuristiken (Auswahl)

* **Compose bevorzugen:** Wenn `compose.yaml|yml` existiert → übernehmen. Sonst generieren; **`compose.yaml`** ist der moderne Standardname. ([Docker Documentation][4])
* **Workflows als Wahrheit:** Schritte in `run:` sind starke Signale für `test`/`build`. Pfade/Env aus `env:` und `services:` extrahieren. ([GitHub Docs][3])
* **Ports:** `EXPOSE` im Dockerfile, sonst Framework‑Defaults (z. B. Node 3000, Django 8000, Spring Boot 8080) – als Annahme transparent in `notes` dokumentieren.
* **Versionsmanagement:** `actions/setup-*` → Basisimages wählen (z. B. `node:20`, `python:3.12`) oder `ASDF/.tool-versions`/`.nvmrc` berücksichtigen.
* **Fallback:** falls *weder* Dockerfile *noch* Compose, generiere minimale Dockerfile + Compose.

---

## 10) Sicherheit & Permissions

* **`permission_mode="acceptEdits"`** erlaubt Dateischreibvorgänge durch Claude in das Arbeitsverzeichnis – kontrolliert & auditierbar; kein permissives `bypassPermissions`. ([Anthropic][2])
* **WebSearch nur bei Bedarf**, API‑Schlüssel als Secret/ENV (`ANTHROPIC_API_KEY`). ([Anthropic][6])
* GitHub‑Zugriffe mit Personal Access Token (scopes: `repo`, read‑only wo möglich); Workflows können zusätzlich über die **REST API** gelistet/gelesen werden. ([GitHub Docs][7])

---

## 11) Beispiel: Node‑Monorepo (fiktiv)

* Workflows zeigen: `actions/setup-node@v4` (Node 20), `npm ci`, `npm run build`, `npm test`.
* Kein Compose → Generator schreibt:

  * `Dockerfile`: `FROM node:20-alpine … EXPOSE 3000`
  * `compose.yaml`: Service `app`, Port‑Mapping `3000:3000`, `volumes` dev‑freundlich.
* `Makefile.build` setzt:

  * `build`: `docker compose build`
  * `start`: `docker compose up -d`
  * `test`: `docker compose run --rm app npm test`

---

## 12) Fehlertoleranz & Telemetrie

* Wenn YAML‑Parsing fehlschlägt, CLI loggt betroffene Datei und markiert die Schritte als *unsicher* → Claude erhält den Rohtext + Warnhinweis.
* Zeitouts/Retry‑Backoff für SDK‑Aufrufe; `--max-turns` begrenzen. (Siehe Headless Best Practices.) ([Anthropic][1])

---

## 13) Erweiterungen (optional)

* **MCP‑Tools**: z. B. GitHub‑/Ticket‑Systeme andocken (mcp‑Server), um Issues/PRs zu lesen. ([Anthropic][6])
* **CI‑Anbindung**: Action/Workflow zur automatischen Regeneration bei Änderungen (d. h. `anthropics/claude-code-action@v1` mit `prompt: "/review"` oder Custom‑Prompt). ([Anthropic][8])
* **Sprache erkennen**: Heuristiken + Manifeste; (GitHub nutzt *Linguist* für Spracherkennung – zur Einordnung). ([GitHub Docs][9])

---

## 14) Minimaler Implementierungsfahrplan

1. **CLI‑Gerüst** (Typer/argparse), **Repo‑Clone** (GitPython/Subprocess).
2. **Scanner** für `README/docs`, **Actions‑Parser** (PyYAML), **Manifest‑Detektoren**.
3. **Plan‑Schema** (Pydantic) + **Prompt‑Vorlagen**.
4. **Claude‑Call** (Python‑SDK) → `plan.json`. ([Anthropic][2])
5. **Generator** für `Makefile.build`, `Makefile.claude`, ggf. `compose.yaml`/`Dockerfile`.
6. **End‑to‑End‑Test** an 3–5 realen Repos (Node, Python, Java, Go, Mixed).

---

### Warum dieses Design?

* **Reproduzierbar & auditierbar:** deterministische JSON‑Pläne + Makefiles, klare Artefakte.
* **Compose‑first:** moderne, portable Standardisierung von Dev/CI‑Umgebungen. ([Docker Documentation][4])
* **Skalierbar:** Headless‑Claude‑Aufrufe oder Python‑SDK‑Streaming, `cwd` auf Repo, feingranulare Tool‑Permissions. ([Anthropic][1])

---

[1]: https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-headless "Headless mode - Anthropic"
[2]: https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-python "Python - Anthropic"
[3]: https://docs.github.com/actions/writing-workflows/about-workflows?utm_source=chatgpt.com "Workflows"
[4]: https://docs.docker.com/compose/intro/compose-application-model/?utm_source=chatgpt.com "How Compose works"
[5]: https://docs.docker.com/reference/cli/docker/compose/?utm_source=chatgpt.com "docker compose"
[6]: https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-overview "Overview - Anthropic"
[7]: https://docs.github.com/rest/actions/workflows?utm_source=chatgpt.com "REST API endpoints for workflows"
[8]: https://docs.anthropic.com/en/docs/claude-code/github-actions "Claude Code GitHub Actions - Anthropic"
[9]: https://docs.github.com/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-repository-languages?utm_source=chatgpt.com "About repository languages"

