#!/usr/bin/env python3
"""Genera las figuras del atlas de la charla LegalIA a partir del atlas en línea.

Uso, desde la raíz del repositorio (no instala nada global):

    uv run --with matplotlib --with numpy python LegalIA/scripts/atlas_figures.py \
        [--data-dir DIR] [--img-dir LegalIA/img]

Descarga (si no existen ya en --data-dir, por defecto un directorio temporal
fuera del repositorio) los tres archivos que publica el sitio
https://ingeotec.github.io/LegalIA/pages/atlas/

- atlas-qwen3-4b.json  Qwen3-Embedding-4B (el atlas que abre la página)
- atlas.json           Qwen3-Embedding-0.6B
- atlas-bm25.json      BM25

imprime su `meta.generated` y `meta.commit`, y escribe en --img-dir, de forma
determinista (tamaños fijos, sin aleatoriedad) y con dpi 150:

- atlas_portada.png     el mapa 4B a vecindad 16 sin ejes ni anotaciones (1280x720)
- atlas.png             el mapa 4B a vecindad 16 con leyenda y anotaciones
- atlas_vecindades.png  el mapa 4B con vecindades 4, 8, 16 y 32
- atlas_mapa.png        los mapas 0.6B, 4B y BM25 a vecindad 16
- atlas_entrantes.png   los 15 instrumentos con más peso entrante en el 4B

Los tres archivos ya vienen alineados al 4B a vecindad 16 (Procrustes de
Wasserstein), así que los mapas se dibujan tal cual, sin girarlos. Los JSON no
se versionan. Referencia: ../LegalIA-overleaf/scripts/atlas_figures.py.
"""

import argparse
import json
import tempfile
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://ingeotec.github.io/LegalIA/pages/atlas/"
FILES = {"4b": "atlas-qwen3-4b.json", "0.6b": "atlas.json", "bm25": "atlas-bm25.json"}
DPI = 150

# Orden, nombre y color de cada colección: la paleta del sitio de LegalIA
# (website/pages/atlas/atlas.js).
COLLECTIONS = ("leyes", "reglamentos", "lineamientos", "tratados")
LABELS = {"leyes": "Leyes", "reglamentos": "Reglamentos",
          "lineamientos": "Lineamientos", "tratados": "Tratados"}
COLORS = {"leyes": "#2a78d6", "reglamentos": "#008300", "lineamientos": "#e87ba4",
          "tratados": "#eda100"}
INK = "#52514e"

# Grupos que se anotan en el mapa (Figura 1 del artículo): etiqueta en español,
# claves (la línea apunta a su centroide), posición del texto en coordenadas del
# mapa 4B a vecindad 16 y alineación. Las posiciones se eligieron para este
# mapa, no son las del artículo, que usa otra proyección.
GROUPS = (
    ("Constitución", ("cpeum",), (0.43, 0.20), "center"),
    ("Leyes orgánicas de Chapingo,\nAntonio Narro, UAM y UNAM",
     ("luach", "louaaan", "louam", "lounam"), (0.74, 0.30), "left"),
    ("Leyes orgánicas y reglamentos\nde los bancos de desarrollo",
     ("lonf", "loshf", "lobb", "lobnosp", "lobnce", "lobnefaa"), (0.10, 0.69), "left"),
    ("Reglamentos de exámenes\nprofesionales de la Armada",
     ("14706", "14707", "14708", "14709", "14710", "14711", "14712", "14713",
      "17158", "163753", "164836", "167322"), (0.10, 0.15), "left"),
    ("Reglamentos de las\nescuelas militares",
     ("20289", "20291", "20292", "20293", "20294", "20295", "20296", "20298",
      "20299", "20301", "20302", "20303", "20305"), (0.36, 0.09), "left"),
    ("Códigos marítimos de la OMI",
     ("114738", "96707", "96728"), (0.12, 0.79), "left"),
    ("Protocolo del T-MEC\ny la LIGIE",
     ("137355", "ligie-2022"), (0.68, 0.18), "left"),
    ("Actas de las Conferencias Mundiales\nde Radiocomunicaciones",
     ("84855", "44552"), (0.34, 0.87), "left"),
)
# Nombres cortos de los tratados entrantes cuyo título, truncado, queda igual a
# otro o es ilegible en mayúsculas.
SHORT_NAMES = {
    "114738": "Código marítimo internacional de mercancías peligrosas (IMDG)",
    "137355": "Protocolo que sustituye el TLCAN por el T-MEC (2018)",
    "96707": "Código internacional de gaseros (CIG)",
    "84855": "Actas finales de la CMR-07 de la UIT",
    "47860": "Actas finales de la CMR-2003 de la UIT",
    "44552": "Actas finales de la CMR-2000 de la UIT",
}
# Límites de atlas.png: los del mapa 4B a vecindad 16 más el margen que necesitan
# las etiquetas.
MAP_LIM = ((0.08, 1.0), (0.06, 0.92))
STOPWORDS = {"de", "del", "la", "las", "los", "el", "y", "e", "en", "a", "al",
             "para", "por", "que", "con", "o", "u", "sobre"}


def download(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in FILES.values():
        path = data_dir / name
        if not path.exists():
            with urllib.request.urlopen(BASE_URL + name, timeout=120) as r:
                path.write_bytes(r.read())


def load(data_dir):
    atlases = {}
    for key, name in FILES.items():
        with open(data_dir / name, encoding="utf-8") as f:
            atlases[key] = json.load(f)
        meta = atlases[key]["meta"]
        print(f"{name}: generated {meta['generated']}, commit {meta['commit']}, "
              f"{meta['instruments']} instrumentos")
    return atlases


def check(atlases):
    ref = atlases["4b"]["instruments"]
    for key, atlas in atlases.items():
        instruments = atlas["instruments"]
        assert len(instruments) == atlas["meta"]["instruments"] == 2670, key
        assert [x["k"] for x in instruments] == [x["k"] for x in ref], key
        for proj in atlas["projections"].values():
            assert len(proj) == len(instruments)
        assert atlas["meta"]["default_n_neighbors"] == 16


def short_name(name, width=None):
    """El título tal como lo publica la SCJN, sin mayúsculas sostenidas."""
    name = name.strip().rstrip(".")
    words = name.split()
    if name.isupper():
        words = [w.lower() if i and w.lower() in STOPWORDS else w.capitalize()
                 for i, w in enumerate(words)]
    elif words and words[0].isupper():
        words[0] = words[0].capitalize()
    text = " ".join(words)
    if width and len(text) > width:
        text = text[: width - 1].rstrip() + "…"
    return text


def setup_matplotlib():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": "#c3c2b7",
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    })


def save(fig, path):
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"{path} ({path.stat().st_size / 1024:.0f} KB)")


def extent(panels, pad=0.02):
    """Límites que contienen todos los puntos de `panels`, una lista de (atlas, vecindad)."""
    pts = [p for atlas, key in panels for p in atlas["projections"][key]]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - pad, max(xs) + pad), (min(ys) - pad, max(ys) + pad)


def draw_map(ax, atlas, key, lim, scale, annotate=False, fontsize=8):
    instruments = atlas["instruments"]
    xy = atlas["projections"][key]
    # Área proporcional a los fragmentos contados, con un piso para que se vean.
    sizes = [max(1.5, scale * x["pc"]) for x in instruments]
    # Los grandes primero, para que los pequeños queden encima.
    order = sorted(range(len(instruments)), key=lambda i: (-instruments[i]["pc"], i))
    ax.scatter([xy[i][0] for i in order], [xy[i][1] for i in order],
               s=[sizes[i] for i in order],
               c=[COLORS[instruments[i]["c"]] for i in order],
               alpha=0.75, linewidths=0.2, edgecolors="white")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(*lim[0])
    ax.set_ylim(*lim[1])
    ax.set_aspect("equal")
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    if not annotate:
        return
    index = {x["k"]: i for i, x in enumerate(instruments)}
    for label, keys, pos, ha in GROUPS:
        points = [xy[index[k]] for k in keys]
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        ax.annotate(label, (cx, cy), xytext=pos, fontsize=fontsize, ha=ha, va="center",
                    arrowprops={"arrowstyle": "-", "color": INK, "lw": 0.6,
                                "shrinkA": 2, "shrinkB": 3},
                    bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none",
                          "alpha": 0.8})


def legend_handles(meta=None, size=7):
    def label(c):
        return f"{LABELS[c]} {meta['collections'][c]:,}" if meta else LABELS[c]
    return [Line2D([0], [0], marker="o", linestyle="", markersize=size,
                   markerfacecolor=COLORS[c], markeredgecolor="white",
                   label=label(c)) for c in COLLECTIONS]


def figure_portada(atlas, lim, path):
    fig = plt.figure(figsize=(1280 / DPI, 720 / DPI))
    ax = fig.add_axes([0, 0, 1, 1])
    draw_map(ax, atlas, "16", lim, scale=0.05)
    save(fig, path)


def figure_map(atlas, lim, path):
    fig, ax = plt.subplots(figsize=(8.4, 7.4))
    draw_map(ax, atlas, "16", lim, scale=0.06, annotate=True)
    fig.legend(handles=legend_handles(atlas["meta"], size=8), loc="lower center", ncol=4,
               frameon=False, fontsize=10)
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.07, top=0.99)
    save(fig, path)


def figure_neighbours(atlas, lim, path):
    keys = [str(n) for n in atlas["meta"]["n_neighbors"]]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 7.4))
    for ax, key in zip(axes.flat, keys):
        draw_map(ax, atlas, key, lim, scale=0.03)
        ax.set_title(f"Vecindad {key}", fontsize=11)
    fig.legend(handles=legend_handles(atlas["meta"]), loc="lower center", ncol=4,
               frameon=False, fontsize=9)
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.06, top=0.95,
                        wspace=0.03, hspace=0.10)
    save(fig, path)


def figure_models(atlases, lim, path):
    panels = (("0.6b", "Qwen3-Embedding-0.6B"), ("4b", "Qwen3-Embedding-4B"), ("bm25", "BM25"))
    fig, axes = plt.subplots(1, 3, figsize=(10.8, 4.2))
    for ax, (key, title) in zip(axes, panels):
        draw_map(ax, atlases[key], "16", lim, scale=0.03)
        ax.set_title(title, fontsize=11)
    fig.legend(handles=legend_handles(atlases["4b"]["meta"]), loc="lower center", ncol=4,
               frameon=False, fontsize=9)
    fig.subplots_adjust(left=0.005, right=0.995, bottom=0.09, top=0.92, wspace=0.02)
    save(fig, path)


def figure_incoming(atlas, path, n=15):
    instruments = atlas["instruments"]
    top = sorted(range(len(instruments)), key=lambda i: (-instruments[i]["in"], i))[:n]
    labels = [short_name(SHORT_NAMES.get(instruments[i]["k"], instruments[i]["n"]), width=45)
              for i in top]
    values = [instruments[i]["in"] for i in top]
    assert len(set(labels)) == n
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    y = list(range(n))[::-1]
    ax.barh(y, values, color=[COLORS[instruments[i]["c"]] for i in top], height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    for yi, v in zip(y, values):
        ax.text(v + 20, yi, f"{v:,.1f}", va="center", fontsize=8.5)
    ax.set_xlim(0, max(values) * 1.14)
    ax.set_xlabel("Peso entrante", fontsize=10)
    ax.tick_params(axis="y", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    present = [c for c in COLLECTIONS if any(instruments[i]["c"] == c for i in top)]
    ax.legend(handles=[h for h, c in zip(legend_handles(), COLLECTIONS) if c in present],
              loc="lower right", frameon=False, fontsize=9)
    fig.subplots_adjust(left=0.40, right=0.98, bottom=0.10, top=0.99)
    save(fig, path)
    return [(labels[k], values[k]) for k in range(n)]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path,
                        default=Path(tempfile.gettempdir()) / "legalia-atlas-data")
    parser.add_argument("--img-dir", type=Path, default=ROOT / "img")
    args = parser.parse_args()

    download(args.data_dir)
    atlases = load(args.data_dir)
    check(atlases)
    args.img_dir.mkdir(parents=True, exist_ok=True)

    setup_matplotlib()
    atlas = atlases["4b"]
    keys = [str(n) for n in atlas["meta"]["n_neighbors"]]
    figure_portada(atlas, extent([(atlas, "16")]), args.img_dir / "atlas_portada.png")
    figure_map(atlas, MAP_LIM, args.img_dir / "atlas.png")
    figure_neighbours(atlas, extent([(atlas, k) for k in keys]),
                      args.img_dir / "atlas_vecindades.png")
    figure_models(atlases, extent([(a, "16") for a in atlases.values()]),
                  args.img_dir / "atlas_mapa.png")
    top = figure_incoming(atlas, args.img_dir / "atlas_entrantes.png")
    for name, value in top[:3]:
        print(f"  {value:,.1f}  {name}")


if __name__ == "__main__":
    main()
