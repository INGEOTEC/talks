#!/usr/bin/env python3
"""Captura las pantallas del atlas y de la página Instruments de LegalIA.

Uso, desde la raíz del repositorio (no instala nada global):

    uv run --with playwright playwright install chromium     # una sola vez
    uv run --with playwright python LegalIA/scripts/atlas_screenshots.py \
        [--img-dir LegalIA/img] [--site https://ingeotec.github.io/LegalIA]

Abre el sitio público con Chromium (viewport 1400x900, escala 1) y guarda en
--img-dir:

- atlas_chapingo.png      la LEY que crea la Universidad Autónoma Chapingo
                          seleccionada, con el mapa y el panel de detalle
- atlas_cpeum.png         la Constitución seleccionada, igual
- atlas_cpeum_lgipe.png   el diálogo con los 16 pares Constitución -> LGIPE
- atlas_estelas.png       la Constitución al cambiar la vecindad de 16 a 8,
                          con las estelas del movimiento sobre el mapa
- instruments.png         la página Instruments de la ley de Chapingo con un
                          fragmento comparado y sus cinco textos más cercanos

Las capturas pueden variar en píxeles entre corridas (el sitio es una página
viva), no en contenido. Los selectores se leen de
../LegalIA/website/pages/atlas/atlas.js y de
../LegalIA/website/pages/instruments/instruments.js.
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://ingeotec.github.io/LegalIA"
N_INSTRUMENTS = 2670
TRAIL_DELAY_MS = 1200  # el movimiento dura menos y las estelas se desvanecen en 2.5 s


def open_atlas(page, site):
    page.goto(f"{site}/pages/atlas.html")
    page.wait_for_function(
        "n => document.querySelectorAll('.atlas-map-wrap svg circle').length === n",
        arg=N_INSTRUMENTS, timeout=120_000)


def select_instrument(page, query, name_start):
    """Escribe en el buscador y elige la sugerencia que empieza con `name_start`."""
    box = page.locator("div.atlas-search input")
    box.fill(query)
    suggestion = page.locator("li.atlas-suggestion").filter(has_text=name_start).first
    suggestion.wait_for(timeout=30_000)
    suggestion.dispatch_event("mousedown")
    page.locator("div[role=complementary] .atlas-panel-title").wait_for(timeout=30_000)
    page.wait_for_timeout(800)


def shot_main(page, path):
    """El mapa más el panel de detalle."""
    page.locator("div.atlas-main").screenshot(path=str(path))
    print(path)


def atlas_screenshots(page, site, img_dir):
    open_atlas(page, site)

    select_instrument(page, "Universidad Autónoma Chapingo", "LEY que crea la Universidad")
    shot_main(page, img_dir / "atlas_chapingo.png")

    select_instrument(page, "Constitución Política", "CONSTITUCIÓN Política")
    shot_main(page, img_dir / "atlas_cpeum.png")

    # El botón del peso 16.0 abre el diálogo con los pares que lo explican.
    page.locator("div[role=complementary] button.atlas-why").first.click()
    dialog = page.locator("dialog.atlas-explain[open]")
    dialog.locator("table.atlas-explain-table tbody tr").first.wait_for(timeout=60_000)
    page.wait_for_timeout(800)
    dialog.screenshot(path=str(img_dir / "atlas_cpeum_lgipe.png"))
    print(img_dir / "atlas_cpeum_lgipe.png")
    dialog.locator("button.atlas-explain-close").click()
    dialog.wait_for(state="hidden")

    # Con la Constitución aún seleccionada, de la vecindad 16 a la 8.
    page.locator("button.atlas-segment[data-value='8']").click()
    page.wait_for_timeout(TRAIL_DELAY_MS)
    n_trails = page.locator("line.atlas-trail").count()
    assert n_trails > 0, "no hay estelas sobre el mapa"
    shot_main(page, img_dir / "atlas_estelas.png")
    print(f"  {n_trails} estelas")


def instruments_screenshot(page, site, img_dir):
    page.goto(f"{site}/pages/instruments.html?c=leyes&k=luach")
    compared = page.locator(".instruments-excerpt[data-compared='true']")
    compared.first.wait_for(timeout=120_000)
    # El primer fragmento comparado es el artículo 1.
    first = compared.first
    first.scroll_into_view_if_needed()
    first.locator("details.instruments-near summary").click()
    first.locator("li.instruments-near-item").nth(4).wait_for(timeout=30_000)
    assert first.locator("li.instruments-near-item").count() == 5
    page.wait_for_timeout(500)
    first.evaluate("el => el.scrollIntoView({block: 'start'})")
    page.evaluate("window.scrollBy(0, -150)")
    page.wait_for_timeout(300)
    page.screenshot(path=str(img_dir / "instruments.png"))
    print(img_dir / "instruments.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--img-dir", type=Path, default=ROOT / "img")
    parser.add_argument("--site", default=SITE)
    args = parser.parse_args()
    args.img_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1)
        atlas_screenshots(page, args.site, args.img_dir)
        instruments_screenshot(page, args.site, args.img_dir)
        browser.close()


if __name__ == "__main__":
    main()
