# AGENTS.md

Ziel: Dieses Dokument beschreibt die Agenten‑Rollen, Übergaben und Orchestrierung für das CLI „claumake“, das aus beliebigen GitHub‑Repos robuste Build‑Artefakte generiert: `Makefile.claude`, `Makefile.build`, `.claude/plan.json` und optional `compose.yaml`/`Dockerfile`.

Die Agenten sind logisch getrennte „Arbeitsprofile“, die lokal sequenziell (oder iterativ) ausgeführt werden. Jeder Agent hat klare Inputs/Outputs, Erfolgs‑Kriterien und nutzt definierte Tools (Claude Code SDK, Read/Bash, YAML‑Parser, Git).

---

## Übersicht der Artefakte

- `.claude/plan.json`: Deterministischer BuildPlan (JSON, Version/Felder siehe Schema in task.md).
- `Makefile.build`: Konkrete Build/Run/Test‑Targets (Compose‑first; Shell‑Kommandos).
- `Makefile.claude`: Headless‑Automationen für Plan/Refine/Regenerate.
- Optional `compose.yaml` und `Dockerfile`: Falls nicht vorhanden, minimaler Vorschlag gemäß Heuristiken.

---

## Orchestrierung (Datenfluss)

1) RepoFetcher → 2) ContextScanner → 3) ActionsAnalyzer → 4) HeuristicsEngineer → 5) ClaudePlanSynthesizer → 6) MakefileGenerator → 7) Validator → 8) Refiner

Jeder Schritt produziert strukturierte Notizen/Signale, die in die nächste Stufe einfließen. Die Claude‑Synthese konsumiert kompakten Kontext (Markdown/JSON) und liefert ausschließlich JSON nach Schema.

---

## Agenten‑Rollen

### 1) RepoFetcher
- Zweck: GitHub‑Repo (shallow) klonen, Arbeitsverzeichnis setzen.
- Inputs: `--repo`, `--branch` (optional), `--path` (optional Subdir).
- Tools: `git clone --depth 1`, Sparse‑Checkout optional, GitHub REST (Fallback für Workflows).
- Outputs: `repo_root` (lokaler Pfad), kurze Repo‑Metadaten.
- Done: Verzeichnis vorhanden, lesbar; ggf. `.git` erhalten für spätere Diffs.
- Fehlerfälle: Private Repos ohne Token, Submodule, große LFS – nur loggen, nicht blockieren.

### 2) ContextScanner
- Zweck: Dokumentation und Manifeste erfassen; vorhandene Build‑Artefakte auflisten.
- Inputs: `repo_root`.
- Tools: Dateiscan (`README*`, `docs/**`, `CONTRIBUTING*`, `INSTALL*`); Erkennen von `compose.yaml|yml`, `docker-compose.*`, `Dockerfile*`, `Makefile`, Sprach‑Manifesten (`package.json`, `pyproject.toml`, `requirements.txt`, `pom.xml`, `build.gradle`, `go.mod`, `Cargo.toml`, …).
- Outputs: `context.md` (kompakte Stichpunkte + Pfade), `manifests.json` (gefundene Dateien), Kandidaten‑Kommandos aus README/Makefile.
- Done: Relevante Pfade + kurze Auszüge gesammelt (keine Volltexte; 1–2 Sätze/Datei).

### 3) ActionsAnalyzer
- Zweck: `.github/workflows/*.yml` parsen und Signale extrahieren.
- Inputs: `repo_root`; ggf. GitHub REST als Fallback.
- Tools: YAML‑Parser (PyYAML), REST Endpunkte (List/Contents); Regex für `jobs.*.steps[].run`.
- Outputs: `actions_signals.json` mit:
  - Runtimes (`actions/setup-*`), Versionen.
  - Build/Test/Lint‑Kommandos (aus `run:`), Services/Env aus `services:`/`env:`.
  - Matrix/OS, Caches.
- Done: Extraktion mit Datei‑Referenzen; bei Fehlern Rohtext + Warnung beilegen.

### 4) HeuristicsEngineer
- Zweck: Sprache/Framework/Ports/Compose‑Strategie ableiten, Kommandos konsolidieren.
- Inputs: `manifests.json`, `actions_signals.json`, `context.md`.
- Regeln:
  - Compose‑first: existierendes `compose.yaml` übernehmen; sonst minimal generieren (moderner Dateiname `compose.yaml`).
  - Ports aus Dockerfile `EXPOSE` oder Framework‑Defaults (Node 3000, Django 8000, Spring Boot 8080, …) – Annahmen dokumentieren.
  - Runtimes aus Workflows/Manifeste (Node 20, Python 3.12, …).
- Outputs: `heuristics.json` mit `language`, `compose.present/file`, `dockerfile.present/path`, `commands.build/start/test/lint/fmt`, `notes`.
- Done: Konsistenter Vorschlag ohne Ausführung; Unsicherheiten transparent in `notes`.

### 5) ClaudePlanSynthesizer
- Zweck: Aus Kontext + Heuristiken einen validen BuildPlan (JSON) erzeugen.
- Inputs: `context.md`, `actions_signals.json`, `heuristics.json` (kompakt zusammengeführt).
- Tools: Claude Code Python‑SDK (`ClaudeSDKClient`, `ClaudeCodeOptions`), Headless‑Konfiguration:
  - `allowed_tools`: `Read,WebSearch,Write,Bash` (WebSearch optional per Flag).
  - `permission_mode`: `acceptEdits` (kontrolliertes Schreiben im `cwd`).
  - `cwd`: Repo‑Root; `max_turns`: konfigurierbar; `model`: per CLI.
- Output: `.claude/plan.json` – strikt gemäß Schema (siehe task.md §6).
- Done: JSON parsebar; `version` gesetzt; Kommandos + Compose‑Flag vorhanden.
- Prompt‑Bausteine:
  - System: „Du bist DevOps/Build‑Engineer. Lies README/Docs, parse .github/workflows, bevorzuge Docker Compose (Dateiname compose.yaml). Liefere ausschließlich JSON im Schema BuildPlan. Keine Prosa.“
  - User: Kompakter Kontext (max. ~2–3k Tokens), inkl. extrahierter `run:` Kommandos.

### 6) MakefileGenerator
- Zweck: Aus `plan.json` die Makefiles und optional Compose/Dockerfile erzeugen.
- Inputs: `.claude/plan.json`.
- Outputs:
  - `Makefile.build`: Targets `help build start stop logs test lint fmt clean compose-up compose-down`.
  - `Makefile.claude`: Headless‑Targets `plan refine regenerate update-compose explain`.
  - Optional `compose.yaml` und `Dockerfile` (wenn im Plan gefordert oder nicht vorhanden).
- Regeln:
  - Compose als `docker compose …`; Service‑Name standardmäßig `app`, per Plan überschreibbar.
  - Keine destruktiven Defaults; `clean` respektiert übliche Excludes (z. B. `node_modules`, `.venv`).
- Done: Dateien geschrieben; `docker compose config` ist syntaktisch valide (wenn Compose erzeugt wurde).

### 7) Validator
- Zweck: Statische Sanity‑Checks, Dry‑Runs, klarer Report.
- Checks:
  - `docker compose config` (wenn Compose existiert).
  - Make‑Targets vorhanden; referenzierte Services existieren.
  - Warnungen bei unbekannten Kommandos (z. B. `npm` ohne `package.json`).
- Output: `validation_report.md` (optional), kurze Zusammenfassung in CLI.

### 8) Refiner (optional/iterativ)
- Zweck: Auf Basis von Nutzerhinweisen/Fehlern `plan.json` verfeinern und Makefiles regenerieren.
- Tools: `Makefile.claude` Targets `refine`/`regenerate` nutzen den Headless‑Modus.
- Output: Aktualisierte Artefakte; Changelog im CLI‑Log.

---

## Schnittstellen (Inputs/Outputs je Agent)

- Gemeinsames Format: JSON‑Dateien unter `.claude/` und kurze Markdown‑Auszüge.
- Naming: Moderne Compose‑Datei `compose.yaml` bevorzugt.
- Determinismus: Plan ist die Quelle der Wahrheit; Generator leitet sich strikt davon ab.

---

## Prompts & Schema (Kurzfassung)

- Schema: Siehe task.md §6 (Version, language, compose{…}, dockerfile{…}, commands{build/start/test}, notes[]).
- System‑Prompt (Auszug): „Bevorzuge Docker Compose (compose.yaml), trianguliere Build/Test aus Workflows + README, liefere nur JSON gemäß Schema. Keine Erklärtexte.“
- Output‑Garantie: JSON erzwingen (Parsing‑Fehler → Retry/Refine). Keine Tools nutzen, die nicht explizit erlaubt sind.

---

## Safety & Permissions

- Claude SDK: `permission_mode=acceptEdits` für kontrollierte Dateischreibvorgänge im Repo‑Root.
- Secrets: `ANTHROPIC_API_KEY` via ENV; GitHub‑Token nur read‑only (`repo` minimal).
- WebSearch: Standard aus; einschaltbar via Flag. Netzwerk nur für nötige REST‑Reads.
- Audit: Logs der extrahierten Signale und generierten Dateien; diffs bevorzugt.

---

## Betriebsmodi

- Headless (CI): Nur `Makefile.claude` Targets verwenden; keine interaktive Genehmigung nötig.
- Lokal (CLI): `claumake --repo … --prefer-compose --no-exec` um zunächst Artefakte zu erzeugen; Ausführung später.

---

## Erfolgs‑Kriterien

- Plan ist valide JSON und deckt `build/start/test` ab.
- Makefile.build führt ohne manuelle Anpassung typische Projekte (Node/Python/Java/Go/Rust) aus.
- Compose wird übernommen oder minimal korrekt generiert (`docker compose config` ok).
- Annahmen/Unsicherheiten sind in `notes` dokumentiert.

---

## Failure Handling

- YAML‑Parsing‑Fehler: betroffene Datei im Report markieren, Rohtext beilegen, trotzdem Plan generieren.
- Fehlende Manifeste: konservative Defaults, laut `notes` dokumentieren.
- Ambiguitäten: mehrere Kandidaten‑Kommandos → priorisieren nach Workflows, sonst README.

---

## Beispiel: Minimaler Ablauf (manuell)

1) Repo klonen: RepoFetcher.
2) Scans ausführen: ContextScanner + ActionsAnalyzer.
3) Heuristiken bilden: HeuristicsEngineer.
4) Plan synthetisieren: ClaudePlanSynthesizer → `.claude/plan.json`.
5) Artefakte generieren: MakefileGenerator → `Makefile.build`, `Makefile.claude`, optional Compose/Dockerfile.
6) Validieren: Validator; bei Bedarf Refiner anstoßen.

---

## Anhang: Beispiel‑Targets (Kurzform)

Makefile.build (Auszug):

```
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
	$(COMPOSE) run --rm $(SERVICE) <TEST_CMD_AUS_PLAN>
```

Makefile.claude (Auszug):

```
SHELL := /bin/bash
CLAUDE ?= claude
ALLOWED := "Read,WebSearch,Write,Bash"
PERM := acceptEdits
CWD := $(PWD)

.PHONY: plan refine regenerate

plan:
	$(CLAUDE) -p "Erstelle BuildPlan als valides JSON (Schema BuildPlan). Lies README/docs und .github/workflows; bevorzuge Docker Compose." \
	 --output-format json --allowedTools $(ALLOWED) --permission-mode $(PERM) --cwd $(CWD) \
	 | jq -r '.result // . | tostring' > .claude/plan.json
```

---

Hinweis: Dieses Dokument konkretisiert die in task.md beschriebenen Anforderungen als ausführbare Agenten‑Spezifikation. Es dient als Grundlage für Implementierung, Tests und CI‑Automatisierung.

