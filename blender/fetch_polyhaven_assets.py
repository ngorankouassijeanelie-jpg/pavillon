"""
Étape 1/3 — Télécharge les ressources Poly Haven (CC0) nécessaires au lobby.

Lancer avec :
    /Applications/Blender.app/Contents/MacOS/Blender -b --python blender/fetch_polyhaven_assets.py

Ce script n'ouvre aucune scène 3D : il interroge l'API publique de Poly Haven
(api.polyhaven.com), choisit la meilleure ressource pour chaque besoin (sol,
bois, laiton, cuir, tissu, terre cuite, HDRI, mobilier), télécharge les
fichiers en 2K dans assets/, et écrit ASSETS.md à la racine du projet.

Tout ce qui vient de Poly Haven est sous licence CC0 (domaine public) —
c'est la seule source de ressources utilisée ici.
"""
import bpy
import json
import os
import sys
import urllib.request
import urllib.parse
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
API = "https://api.polyhaven.com"
RESOLUTION = "2k"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PavillonLobbyBuilder/1.0)"}


def http_get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        print(f"  déjà présent : {dest_path}")
        return dest_path
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=180) as r, open(dest_path, "wb") as f:
        f.write(r.read())
    print(f"  téléchargé : {dest_path}")
    return dest_path


def find_leaf_url(node, resolution, prefer_formats):
    """Les réponses /files/{id} sont imbriquées {clé_carte: {résolution: {format: {url:...}}}}.
    On cherche la résolution demandée puis le meilleur format disponible, sans dépendre
    d'une structure figée (le catalogue Poly Haven évolue)."""
    if not isinstance(node, dict):
        return None
    sub = node.get(resolution)
    if sub is None and node:
        # Résolution absente : on prend la plus proche disponible (triée par nom, ex. 1k/2k/4k)
        keys = sorted(node.keys())
        sub = node[keys[0]] if keys else None
    if not isinstance(sub, dict):
        return None
    for fmt in prefer_formats:
        entry = sub.get(fmt)
        if isinstance(entry, dict) and "url" in entry:
            return entry["url"]
    for entry in sub.values():
        if isinstance(entry, dict) and "url" in entry:
            return entry["url"]
    return None


def get_map_url(files_json, key_substrings, resolution=RESOLUTION, prefer_formats=("jpg", "png", "exr")):
    for key, node in files_json.items():
        kl = key.lower()
        if any(sub in kl for sub in key_substrings):
            url = find_leaf_url(node, resolution, prefer_formats)
            if url:
                return url
    return None


def score_asset(meta, asset_id, include_kw, exclude_kw):
    haystack = " ".join([asset_id] + meta.get("categories", []) + meta.get("tags", []) + [meta.get("name", "")]).lower()
    if any(bad in haystack for bad in exclude_kw):
        return -1
    score = sum(1 for kw in include_kw if kw in haystack)
    return score


def pick_best(assets, include_kw, exclude_kw=()):
    best_id, best_score, best_downloads = None, -1, -1
    for asset_id, meta in assets.items():
        s = score_asset(meta, asset_id, include_kw, exclude_kw)
        if s < 0:
            continue
        dl = meta.get("download_count", 0)
        if s > best_score or (s == best_score and dl > best_downloads):
            best_id, best_score, best_downloads = asset_id, s, dl
    return best_id


print("== Poly Haven : téléchargement du catalogue (hdris / textures / models) ==")
hdris = http_get_json(f"{API}/assets?type=hdris")
textures = http_get_json(f"{API}/assets?type=textures")
models = http_get_json(f"{API}/assets?type=models")

NEEDS = {
    "hdri_golden_hour": {
        "pool": hdris, "kind": "hdri",
        "include": ["sunset", "dusk", "golden", "evening", "afternoon"],
        "exclude": ["night", "indoor", "studio", "overcast", "storm"],
    },
    "floor_stone": {
        "pool": textures, "kind": "texture",
        "include": ["marble", "stone", "polished", "terrazzo", "travertine", "tile"],
        "exclude": ["wood", "fabric", "leather", "metal", "rough_rock", "cliff", "ground"],
    },
    "wood_dark": {
        "pool": textures, "kind": "texture",
        "include": ["wood", "dark", "walnut", "wenge", "plank"],
        "exclude": ["light", "pale", "white", "bleached"],
    },
    "brass": {
        "pool": textures, "kind": "texture",
        "include": ["metal", "brass", "gold", "brushed", "bronze"],
        "exclude": ["rust", "rusty", "corrugated"],
    },
    "leather": {
        "pool": textures, "kind": "texture",
        "include": ["leather"],
        "exclude": [],
    },
    "fabric": {
        "pool": textures, "kind": "texture",
        "include": ["fabric", "linen", "textile", "cloth"],
        "exclude": ["leather"],
    },
    "terracotta": {
        "pool": textures, "kind": "texture",
        "include": ["terracotta", "clay", "brick", "tile"],
        "exclude": ["wood", "fabric"],
    },
    "model_armchair": {
        "pool": models, "kind": "model",
        "include": ["armchair", "chair", "sofa"],
        "exclude": ["office", "gaming"],
    },
    "model_coffee_table": {
        "pool": models, "kind": "model",
        "include": ["coffee_table", "table", "side_table"],
        "exclude": ["dining", "pool"],
    },
    "model_lamp": {
        "pool": models, "kind": "model",
        "include": ["lamp", "light"],
        "exclude": ["street", "traffic"],
    },
    "model_plant": {
        "pool": models, "kind": "model",
        "include": ["plant", "palm", "monstera", "potted", "tropical"],
        "exclude": ["dead", "dry"],
    },
}

chosen = {}
for need_name, spec in NEEDS.items():
    asset_id = pick_best(spec["pool"], spec["include"], spec["exclude"])
    if not asset_id:
        print(f"!! Aucune ressource trouvée pour « {need_name} » (mots-clés {spec['include']}) — à vérifier manuellement sur polyhaven.com")
        continue
    chosen[need_name] = {"id": asset_id, "kind": spec["kind"], "meta": spec["pool"][asset_id]}
    print(f"-> {need_name} : {asset_id} ({spec['pool'][asset_id].get('name', asset_id)})")

assets_md_lines = [
    "# ASSETS.md — Ressources Poly Haven utilisées pour le lobby",
    "",
    "Toutes les ressources ci-dessous viennent de https://polyhaven.com et sont",
    "sous licence **CC0 1.0** (domaine public, usage libre y compris commercial,",
    "aucune attribution requise). Générées automatiquement par",
    "`blender/fetch_polyhaven_assets.py`.",
    "",
    "| Besoin | Ressource Poly Haven | Type | Page | Licence |",
    "|---|---|---|---|---|",
]

for need_name, info in chosen.items():
    pid = info["id"]
    name = info["meta"].get("name", pid)
    kind = info["kind"]
    page = f"https://polyhaven.com/a/{pid}"
    assets_md_lines.append(f"| {need_name} | {name} (`{pid}`) | {kind} | {page} | CC0 |")

print("\n== Téléchargement des fichiers (résolution 2K) ==")

# HDRI
if "hdri_golden_hour" in chosen:
    pid = chosen["hdri_golden_hour"]["id"]
    files_json = http_get_json(f"{API}/files/{pid}")
    url = get_map_url(files_json, ["hdri"], prefer_formats=("hdr", "exr")) or get_map_url(files_json, [""], prefer_formats=("hdr", "exr"))
    if url:
        ext = os.path.splitext(url)[1]
        download(url, os.path.join(ASSETS_DIR, "hdri", f"golden_hour{ext}"))
    else:
        print("!! Impossible de trouver le fichier HDRI pour", pid)

# Textures (PBR : diffuse / normal / rugosité / AO / métallique)
TEXTURE_NEEDS = ["floor_stone", "wood_dark", "brass", "leather", "fabric", "terracotta"]
MAP_KEYS = {
    "diffuse": ["diff", "color", "col_"],
    "normal": ["nor_gl", "nor"],
    "roughness": ["rough"],
    "ao": ["ao"],
    "metal": ["metal"],
}
for need in TEXTURE_NEEDS:
    if need not in chosen:
        continue
    pid = chosen[need]["id"]
    files_json = http_get_json(f"{API}/files/{pid}")
    folder = os.path.join(ASSETS_DIR, "textures", need)
    for map_name, substrs in MAP_KEYS.items():
        url = get_map_url(files_json, substrs)
        if url:
            ext = os.path.splitext(url)[1]
            download(url, os.path.join(folder, f"{map_name}{ext}"))

def patch_missing_gltf_resources(gltf_path, base_url):
    """Un .gltf référence son .bin et ses textures en fichiers séparés
    (contrairement au .glb autonome). On relit le .gltf téléchargé et on va
    chercher, à côté de son URL d'origine, tout fichier référencé qui manque
    encore localement."""
    try:
        with open(gltf_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  !! Impossible de relire {gltf_path} : {e}")
        return
    folder = os.path.dirname(gltf_path)
    uris = [b["uri"] for b in data.get("buffers", []) if "uri" in b]
    uris += [i["uri"] for i in data.get("images", []) if "uri" in i]
    for uri in uris:
        if uri.startswith("data:"):
            continue
        rel = urllib.parse.unquote(uri)
        local_path = os.path.join(folder, rel)
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            continue
        file_url = urllib.parse.urljoin(base_url, uri)
        try:
            download(file_url, local_path)
        except Exception as e:
            print(f"  !! Ressource manquante introuvable ({rel}) : {e}")


# Modèles (fauteuil, table basse, lampe, plante) — au format glTF.
# Les modèles glTF de Poly Haven sont livrés en plusieurs fichiers (le
# .gltf lui-même, un .bin, et les textures) : le JSON /files/{id} liste les
# fichiers additionnels sous une clé "include" à côté du fichier principal.
MODEL_NEEDS = ["model_armchair", "model_coffee_table", "model_lamp", "model_plant"]
for need in MODEL_NEEDS:
    if need not in chosen:
        continue
    pid = chosen[need]["id"]
    files_json = http_get_json(f"{API}/files/{pid}")
    gltf_node = files_json.get("gltf")
    if not gltf_node:
        print(f"!! Pas de version glTF pour {pid}, ce meuble sera remplacé par une forme simple.")
        continue
    res_node = gltf_node.get(RESOLUTION) or next(iter(gltf_node.values()), None)
    if not isinstance(res_node, dict) or "url" not in res_node:
        print(f"!! Entrée glTF inattendue pour {pid}, ce meuble sera remplacé par une forme simple.")
        continue
    main_url = res_node["url"]
    folder = os.path.join(ASSETS_DIR, "models", need)
    main_name = os.path.basename(urllib.parse.urlparse(main_url).path) or "model.gltf"
    main_dest = os.path.join(folder, main_name)
    download(main_url, main_dest)
    for rel_path, info in (res_node.get("include") or {}).items():
        if isinstance(info, dict) and "url" in info:
            download(info["url"], os.path.join(folder, rel_path))
    if main_dest.endswith(".gltf"):
        patch_missing_gltf_resources(main_dest, main_url)
    elif main_dest.endswith(".zip"):
        with zipfile.ZipFile(main_dest) as z:
            z.extractall(folder)
        print(f"  décompressé dans {folder}")

with open(os.path.join(PROJECT_ROOT, "ASSETS.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(assets_md_lines) + "\n")

print("\n== Terminé ==")
print(f"Ressources dans : {ASSETS_DIR}")
print(f"Journal des choix : {os.path.join(PROJECT_ROOT, 'ASSETS.md')}")
