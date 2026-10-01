"""
Étape 3/3 — À lancer seulement après validation des 4 rendus de l'étape 2.

Ouvre lobby_stage1.blend, précalcule l'éclairage (lightmap Cycles sur un
second jeu d'UV, débruitée, atlas 4096x4096 max), crée les volumes de
collision simplifiés (préfixés COL_), puis exporte lobby.glb (Draco + WebP,
objectif 25 Mo / 500 000 triangles maximum).

Lancer avec :
    /Applications/Blender.app/Contents/MacOS/Blender -b --python blender/bake_and_export.py
"""
import bpy
import json
import math
import os
import struct

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_IN = os.path.join(PROJECT_ROOT, "lobby_stage1.blend")
GLB_OUT = os.path.join(PROJECT_ROOT, "lobby.glb")
LIGHTMAP_SIZE = 1024  # 2048 donnait encore un fichier > 30 Mo ; 1024 reste net à la distance de vue du lobby

bpy.ops.wm.open_mainfile(filepath=BLEND_IN)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
try:
    scene.cycles.device = "GPU"
except Exception:
    pass
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPENIMAGEDENOISE"

arch_collection = bpy.data.collections.get("Lobby_Architecture")
if arch_collection is None:
    raise SystemExit("Collection 'Lobby_Architecture' introuvable — avez-vous bien lancé build_lobby_stage1.py avant ?")

# ---------------------------------------------------------------- 1) fusionner l'architecture statique

bpy.ops.object.select_all(action="DESELECT")
arch_objects = [o for o in arch_collection.objects if o.type == "MESH"]
for o in arch_objects:
    o.select_set(True)
bpy.context.view_layer.objects.active = arch_objects[0]
bpy.ops.object.join()
lobby_shell = bpy.context.view_layer.objects.active
lobby_shell.name = "Lobby_Shell_Baked"

tris = sum(len(p.vertices) - 2 for p in lobby_shell.data.polygons)
print(f"Architecture fusionnée : {tris} triangles (estimation)")

# ---------------------------------------------------------------- 2) UV de lightmap (2e jeu d'UV)

bpy.ops.object.select_all(action="DESELECT")
lobby_shell.select_set(True)
bpy.context.view_layer.objects.active = lobby_shell
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_PACK_IN_ONE=True, PREF_NEW_UVLAYER=True,
                          PREF_MARGIN_DIV=0.3)
lightmap_uv = lobby_shell.data.uv_layers[-1]
lightmap_uv.name = "UVLightmap"
lightmap_uv.active = True
lightmap_uv.active_render = False  # le rendu Cycles doit utiliser l'UV0 pour les textures PBR existantes

# ---------------------------------------------------------------- 3) image cible du bake

bake_image = bpy.data.images.new("Lightmap_Atlas", width=LIGHTMAP_SIZE, height=LIGHTMAP_SIZE, float_buffer=True)
bake_image.colorspace_settings.name = "Non-Color"

gltf_group = bpy.data.node_groups.get("glTF Settings")
if gltf_group is None:
    gltf_group = bpy.data.node_groups.new("glTF Settings", "ShaderNodeTree")
    gltf_group.interface.new_socket(name="Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")

bake_target_nodes = []
for mat in lobby_shell.data.materials:
    if mat is None:
        continue
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    uv_node = nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = "UVLightmap"

    img_node = nodes.new("ShaderNodeTexImage")
    img_node.image = bake_image
    img_node.select = True
    nt.nodes.active = img_node
    links.new(uv_node.outputs["UV"], img_node.inputs["Vector"])
    bake_target_nodes.append(img_node)

    try:
        group_node = nodes.new("ShaderNodeGroup")
        group_node.node_tree = gltf_group
        links.new(img_node.outputs["Color"], group_node.inputs["Occlusion"])
    except Exception as e:
        print(f"!! Impossible de relier le noeud glTF Settings sur {mat.name} : {e}")

# ---------------------------------------------------------------- 4) bake Cycles (lumière directe + indirecte, sans l'albédo)

scene.render.bake.use_selected_to_active = False
scene.cycles.samples = 512
print("Calcul du lightmap (peut prendre plusieurs minutes)...")
bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=8)
print("Bake terminé.")

lightmaps_dir = os.path.join(PROJECT_ROOT, "assets", "lightmaps")
os.makedirs(lightmaps_dir, exist_ok=True)
bake_image.filepath_raw = os.path.join(lightmaps_dir, "lobby_atlas.png")
bake_image.file_format = "PNG"
bake_image.save()
print(f"Atlas sauvegardé : {bake_image.filepath_raw}")

# ---------------------------------------------------------------- 5) volumes de collision simplifiés (COL_)

col_collection = bpy.data.collections.new("Collisions")
bpy.context.scene.collection.children.link(col_collection)


def P(x, y, z):
    return (x, -z, y)


def add_collider_box(w, d, x, z, ry, name):
    bpy.ops.mesh.primitive_cube_add(size=1, location=P(x, 0.0, z))
    obj = bpy.context.object
    obj.name = f"COL_{name}"
    obj.scale = (w, d, 3.0)
    obj.rotation_euler = (0, 0, ry)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.hide_render = True
    obj.display_type = "WIRE"
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col_collection.objects.link(obj)
    return obj


# Correspond aux addCollider(...) de buildWorld() pour les éléments reconstruits ici.
for i in range(8):
    a = (i * 45 + 22.5) * math.pi / 180
    x, z = math.sin(a) * 21, math.cos(a) * 21
    add_collider_box(1.1, 1.1, x, z - 5, 0, f"Column_{i}")

for x in (-14.5, 14.5):
    add_collider_box(0.2, 7, x, -15.5, 0, f"Claustra_{x}")

add_collider_box(6, 1.3, -9, 3, 0, "Reception")

for cx, cz in ((-13, 9), (13, 9)):
    add_collider_box(1.2, 1.2, cx, cz - 5, 0, f"Table_{cx}")

# ---------------------------------------------------------------- 6) réduire les textures pour tenir le budget 25 Mo

MAX_TEXTURE_SIZE = 768  # 1024 ne suffisait pas (fichier > 30 Mo avec le mobilier Poly Haven) ; 768 tient le budget
for img in bpy.data.images:
    if img.name == bake_image.name or not img.has_data:
        continue
    w, h = img.size
    if w > MAX_TEXTURE_SIZE or h > MAX_TEXTURE_SIZE:
        scale = MAX_TEXTURE_SIZE / max(w, h)
        img.scale(max(1, round(w * scale)), max(1, round(h * scale)))
        # Les images du mobilier Poly Haven viennent d'un fichier JPEG non empaqueté
        # sur le disque : sans pack(), l'exportateur glTF recopiait les octets du
        # fichier source (toujours en 2K) au lieu de relire le buffer réduit en
        # mémoire, ce qui annulait silencieusement cette réduction (le fichier
        # final restait à 36.9 Mo, identique à avant la réduction).
        img.pack()
        print(f"  texture réduite : {img.name} ({w}x{h} -> {img.size[0]}x{img.size[1]})")

# ---------------------------------------------------------------- 7) export glTF (Draco + JPEG)

desired_kwargs = dict(
    filepath=GLB_OUT,
    export_format="GLB",
    export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=10,
    export_draco_position_quantization=12,
    export_draco_normal_quantization=8,
    export_draco_texcoord_quantization=10,
    # JPEG plutôt que WEBP : le GLTFLoader de Three.js r128 (version utilisée par
    # pavillon.html) ne sait pas décoder EXT_texture_webp et fait échouer tout le
    # chargement du fichier. JPEG plutôt que AUTO/PNG : AUTO a gardé des images non
    # compressées et a fait monter lobby.glb à 122 Mo au lieu des 25 Mo visés.
    export_image_format="JPEG",
    export_jpeg_quality=65,
    export_apply=True,
    use_visible=True,
    export_yup=True,
)
# Les noms de paramètres de l'exporteur glTF changent d'une version de Blender à
# l'autre : on ne garde que ceux que cette version reconnaît réellement, au lieu
# de deviner et de recommencer à chaque erreur.
valid_props = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
export_kwargs = {}
for key, value in desired_kwargs.items():
    if key in valid_props:
        export_kwargs[key] = value
    else:
        print(f"!! Option d'export ignorée (absente de cette version de Blender) : {key}")
bpy.ops.export_scene.gltf(**export_kwargs)

size_mb = os.path.getsize(GLB_OUT) / (1024 * 1024)
print(f"\n== Terminé ==")
print(f"lobby.glb : {GLB_OUT} ({size_mb:.1f} Mo)")
if size_mb > 25:
    print("!! Attention : le fichier dépasse les 25 Mo visés.")

# ---------------------------------------------------------------- 8) diagnostic : textures vs géométrie dans le .glb final
# La réduction de résolution des textures n'a pas fait bouger la taille lors des
# essais précédents (36.9 Mo avant et après) : plutôt que de continuer à deviner,
# on ouvre le .glb produit et on mesure exactement ce qui pèse.


def analyze_glb(path):
    with open(path, "rb") as f:
        magic, _version, total_length = struct.unpack("<4sII", f.read(12))
        if magic != b"glTF":
            print("!! Fichier glTF binaire invalide, diagnostic impossible.")
            return
        json_len, json_type = struct.unpack("<I4s", f.read(8))
        gltf = json.loads(f.read(json_len))
        bin_len = 0
        if f.tell() < total_length:
            bin_len, _bin_type = struct.unpack("<I4s", f.read(8))

    buffer_views = gltf.get("bufferViews", [])
    images = gltf.get("images", [])
    meshes = gltf.get("meshes", [])
    nodes = gltf.get("nodes", [])

    image_bytes = 0
    image_report = []
    for i, img in enumerate(images):
        bv_idx = img.get("bufferView")
        if bv_idx is None:
            continue
        size = buffer_views[bv_idx].get("byteLength", 0)
        image_bytes += size
        image_report.append((img.get("name", f"image_{i}"), size))
    image_report.sort(key=lambda t: -t[1])

    mesh_users = {}
    for node in nodes:
        if "mesh" in node:
            mesh_users[node["mesh"]] = mesh_users.get(node["mesh"], 0) + 1
    duplicated_meshes = [(meshes[i].get("name", f"mesh_{i}"), count)
                          for i, count in mesh_users.items() if count == 1]

    print("\n== Répartition du .glb ==")
    print(f"Taille totale             : {total_length / 1024 / 1024:.2f} Mo")
    print(f"Chunk binaire (BIN)       : {bin_len / 1024 / 1024:.2f} Mo")
    print(f"  dont textures           : {image_bytes / 1024 / 1024:.2f} Mo ({len(images)} images)")
    print(f"  dont géométrie (reste)  : {(bin_len - image_bytes) / 1024 / 1024:.2f} Mo")
    print(f"Nombre de meshes uniques  : {len(meshes)} (utilisés par {len(nodes)} objets dans la scène)")
    print("Top 10 textures les plus lourdes :")
    for name, size in image_report[:10]:
        print(f"  {size / 1024:7.0f} Ko  {name}")
    if not image_report:
        print("  (aucune, ou aucune texture n'est intégrée dans le binaire)")


analyze_glb(GLB_OUT)
