#!/usr/bin/env python3
"""Render the site and verify the freeze cache that CI publishes from.

`.github/workflows/publish.yml` renders the whole project with `quarto
render .` and then publishes `_site/` to gh-pages. `execute: freeze: auto` in
_quarto.yml makes quarto reuse the execution results already committed under
_freeze instead of re-running a page's Python cells, as long as the frozen
result's `hash` still matches the current source file.

Only the pages under TextClassification/ execute Python (EvoMSA, microtc,
CompStats, encexp, dialectid, ...); everything else (IberLEF2023, MexLEF2023,
MetricSearch, the landing page) is plain markdown/revealjs with no code, so
quarto never freezes it and there is nothing to verify there.

CI does install the full conda environment (see environment.yml), so a stale
freeze cache will not break the publish the way it would on a bare runner —
quarto just falls back to re-executing the page, including re-downloading
datasets like TextClassification/delitos.zip. That is slow and, worse, means
the HTML that ships is whatever CI happened to (re)compute rather than what
you last reviewed locally. This script makes that drift visible instead of
silent: it renders, then checks that every executed page's committed hash
matches its source and that every figure the frozen markdown points at is
actually committed.

Usage, from anywhere in the repo:

    python scripts/render.py                          # deps, render, verify
    python scripts/render.py --verify-only             # check the cache only
    python scripts/render.py TextClassification/general.qmd
    python scripts/render.py --force TextClassification/general.qmd

quarto itself is not installed by this script: install it separately (see
https://quarto.org/docs/get-started/), or use the devcontainer if this repo
has one configured.
"""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FREEZE = REPO / "_freeze"
WORKFLOW = REPO / ".github" / "workflows" / "publish.yml"

# What the executable pages import, as {module: pip requirement}. `jupyter`
# is quarto's execution engine for the ```{python} cells, not itself imported.
PYPI_DEPS = {
    "jupyter": "jupyter",
    "IPython": "ipython",
    "numpy": "numpy",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "plotly": "plotly",
    "wordcloud": "wordcloud",
    "country_converter": "country_converter",
    "microtc": "microtc",
    "EvoMSA": "EvoMSA",
    "CompStats": "CompStats",
    "encexp": "encexp",
    "dialectid": "dialectid",
}

CODE_CELL = re.compile(r"^```\{(python|r|julia|ojs)\}", re.MULTILINE)


def log(message: str) -> None:
    print(f"[render] {message}", flush=True)


def executes_code(page: Path) -> bool:
    """Whether `page` has any executable cell, i.e. whether quarto freezes it."""
    return bool(CODE_CELL.search(page.read_text(encoding="utf-8")))


def pages() -> list[Path]:
    """The executable .qmd pages, as paths relative to the repo root.

    Most .qmd files here (IberLEF2023, MexLEF2023, MetricSearch, index.qmd)
    are plain markdown/revealjs with no code, so quarto never freezes them —
    only pages with at least one ```{python} cell are relevant to this script.
    """
    found = [
        p.relative_to(REPO)
        for p in REPO.rglob("*.qmd")
        if not any(part in {"_freeze", "_site", ".quarto"} for part in p.parts)
        and executes_code(p)
    ]
    return sorted(found)


def freeze_result(page: Path) -> Path:
    """Where quarto keeps `page`'s frozen execution result."""
    return FREEZE / page.with_suffix("") / "execute-results" / "html.json"


def quarto_version() -> str:
    """The quarto on PATH, or exit telling the caller where to get one."""
    try:
        out = subprocess.run(
            ["quarto", "--version"], capture_output=True, text=True, check=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        sys.exit(
            "[render] quarto not found on PATH. Install it from "
            "https://quarto.org/docs/get-started/ first."
        )
    return out.stdout.strip()


def ci_quarto_version() -> str | None:
    """The version publish.yml pins for quarto-actions/setup, if any."""
    if not WORKFLOW.exists():
        return None
    text = WORKFLOW.read_text(encoding="utf-8")
    step = re.search(r"quarto-actions/setup@[^\n]*\n(.*?)(?:\n\s*- name:|\Z)", text, re.S)
    if not step:
        return None
    match = re.search(r"version:\s*[\"']?([^\"'\n]+)", step.group(1))
    return match.group(1).strip() if match else None


def ensure_dependencies() -> None:
    """Install whatever the executable pages import and is not importable yet."""
    missing = [req for module, req in PYPI_DEPS.items() if importlib.util.find_spec(module) is None]
    if not missing:
        log("rendering dependencies already installed")
        return
    log(f"installing {' '.join(missing)}")
    subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=True)


def render(targets: list[Path], force: bool) -> None:
    """Run quarto over `targets` (the whole project when empty)."""
    if force:
        for page in targets or pages():
            stale = FREEZE / page.with_suffix("")
            if stale.exists():
                log(f"dropping frozen result for {page}")
                shutil.rmtree(stale)

    command = ["quarto", "render", *(str(t) for t in targets)] if targets else ["quarto", "render", "."]
    log(f"{' '.join(command)}  (cwd: {REPO})")
    result = subprocess.run(command, cwd=REPO)
    if result.returncode != 0:
        sys.exit(f"[render] quarto render failed with exit code {result.returncode}")


def orphaned_freeze_dirs(current: list[Path]) -> list[str]:
    """Frozen result directories left behind by a renamed/deleted page.

    Checked by directory name rather than by looking for a html.json inside,
    since a half-cleaned-up rename can leave an empty directory behind with
    no execute-results at all.
    """
    known = {str(p.with_suffix("")) for p in current}
    orphans = []
    for content_dir in FREEZE.iterdir():
        if not content_dir.is_dir() or content_dir.name == "site_libs":
            continue
        for page_dir in content_dir.iterdir():
            if page_dir.is_dir() and str(page_dir.relative_to(FREEZE)) not in known:
                orphans.append(str(page_dir.relative_to(FREEZE)))
    return sorted(orphans)


def verify() -> list[str]:
    """Check every executable page's frozen result the way CI's quarto will read it."""
    problems = []
    current = pages()
    for page in current:
        source = REPO / page
        result_file = freeze_result(page)
        if not result_file.exists():
            problems.append(
                f"{page}: no frozen result at {result_file.relative_to(REPO)} — quarto "
                f"will execute this page from scratch. Render it (this script, without "
                f"--verify-only)."
            )
            continue

        frozen = json.loads(result_file.read_text(encoding="utf-8"))
        digest = hashlib.md5(source.read_bytes()).hexdigest()
        if digest != frozen["hash"]:
            problems.append(
                f"{page}: stale freeze — md5(source)={digest} but the frozen hash is "
                f"{frozen['hash']}. quarto will re-execute this page and publish "
                f"whatever that produces, not what you last reviewed. Re-render it, "
                f"and do not edit the .qmd afterwards without rendering again."
            )
            continue

        # Figures the frozen markdown points at live beside it under
        # _freeze/<page>/, one directory per name in `supporting`. A missing
        # one renders as a broken image on Pages, and quarto has no way to
        # notice since it never re-executes a page whose hash still matches.
        result = frozen["result"]
        markdown = result["markdown"]
        missing_assets = []
        for supporting in result.get("supporting", []):
            # `supporting` is quarto's on-disk resource dir for this render,
            # e.g. "name_files" or "name_files/figure-revealjs" — but under
            # _freeze/<page>/ only what comes after that first "name_files"
            # segment is kept, so strip just that segment, not all of `supporting`.
            top_level = Path(supporting).parts[0]
            referenced = set(re.findall(rf"{re.escape(supporting)}/[\w./-]+", markdown))
            for reference in sorted(referenced):
                relative = Path(reference).relative_to(top_level)
                asset = FREEZE / page.with_suffix("") / relative
                if not asset.exists():
                    missing_assets.append(
                        f"{page}: frozen markdown references {reference} but "
                        f"{asset.relative_to(REPO)} is missing."
                    )

        if missing_assets:
            problems.extend(missing_assets)
        else:
            log(f"{page}: freeze OK (hash {digest[:12]})")

    # A frozen result only helps CI once it is committed: the runner checks
    # the repo out and renders from that, so anything still untracked here is
    # invisible there.
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "_freeze"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.split()
    for path in untracked:
        problems.append(f"{path} is untracked — git add it, or CI will not see it.")

    for orphan in orphaned_freeze_dirs(current):
        log(
            f"note: _freeze/{orphan} has no matching source page anymore "
            f"(renamed or deleted?) — safe to 'git rm -r' if so."
        )

    return problems


def report_artifacts() -> None:
    """Show what the render touched, so the caller knows what to commit."""
    paths = ["_freeze", *(str(page) for page in pages())]
    changed = subprocess.run(
        ["git", "status", "--porcelain", "--", *paths],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not changed:
        log("nothing changed — the committed cache already matches the sources")
        return
    log("commit these together, so the .qmd sources and their freeze hashes stay in step:")
    for line in changed.splitlines():
        print(f"    {line}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="pages to render, relative to the repo root (default: the whole site)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="skip rendering; only check that the committed freeze cache is up to date",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="discard the frozen results of the selected pages so they re-execute",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="do not install missing Python dependencies before rendering",
    )
    args = parser.parse_args()

    targets = [Path(t) for t in args.targets]
    for target in targets:
        if not (REPO / target).exists():
            sys.exit(f"[render] no such page: {target}")

    if not args.verify_only:
        local = quarto_version()
        pinned = ci_quarto_version()
        log(f"quarto {local} (CI pins {pinned or 'nothing'})")
        if pinned == "pre-release":
            log(
                "note: CI installs quarto's 'pre-release' channel, which moves over time, "
                "so an exact local match is not expected. The freeze hash is a plain md5 "
                "of the source, so a cache written here stays valid there regardless."
            )
        elif pinned and local != pinned:
            log(
                f"note: CI renders with quarto {pinned}. The freeze hash is a plain md5 "
                f"of the source, so a cache written here is still valid there, but pin "
                f"your local quarto to {pinned} if the rendered HTML ever diverges."
            )
        if not args.skip_deps:
            ensure_dependencies()
        render(targets, args.force)

    problems = verify()
    if problems:
        log(f"{len(problems)} problem(s) — the committed freeze cache is not ready:")
        for problem in problems:
            print(f"    - {problem}")
        return 1

    log("every executed page's frozen result matches its source")
    if not args.verify_only:
        report_artifacts()
    return 0


if __name__ == "__main__":
    sys.exit(main())
