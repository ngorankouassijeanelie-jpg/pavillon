"""
Étape 2/3 — Construit le lobby dans Blender aux dimensions exactes de
pavillon.html (fonction buildWorld), pose l'éclairage (soleil bas + HDRI),
puis rend 4 vues de validation et sauvegarde lobby_stage1.blend.

Lancer avec :
    /Applications/Blender.app/Contents/MacOS/Blender -b --python blender/build_lobby_stage1.py

Ne pas lancer avant que blender/fetch_polyhaven_assets.py ait terminé.

--- Conversion d'axes ---
pavillon.html utilise Three.js (Y vers le haut). Blender utilise Z vers le
haut. La conversion utilisée partout ici est :
    Blender(X, Y, Z) = (Three.x, -Three.z, Three.y)
C'est une rotation pure (pas une réflexion), donc les angles de rotation
autour de l'axe vertical (ry en Three.js) se reportent tels quels sur
l'axe Z de Blender.
"""
import bpy
import math
import os
import mathutils

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
RENDERS_DIR = os.path.join(PROJECT_ROOT, "renders")
BLEND_OUT = os.path.join(PROJECT_ROOT, "lobby_stage1.blend")
os.makedirs(RENDERS_DIR, exist_ok=True)

# ---------------------------------------------------------------- utilitaires

def P(x, y, z):
    """Position Three.js (Y-up) -> Blender (Z-up)."""
    return (x, -z, y)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block_type in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for block in list(block_type):
            if block.users == 0:
                block_type.remove(block)


def find_file(*candidates):
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def find_texture_folder(name):
    folder = os.path.join(ASSETS_DIR, "textures", name)
    maps = {}
    if not os.path.isdir(folder):
        return maps
    for fname in os.listdir(folder):
        key = os.path.splitext(fname)[0]
        maps[key] = os.path.join(folder, fname)
    return maps


def load_image(path, non_color=False):
    if not path:
        return None
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def make_pbr_material(name, texture_folder_name, base_color=(0.8, 0.8, 0.8, 1), roughness=0.6, metallic=0.0, uv_scale=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    out.location = (500, 0)
    bsdf.location = (200, 0)

    maps = find_texture_folder(texture_folder_name)
    if maps:
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (uv_scale, uv_scale, uv_scale)
        mapping.location = (-800, 0)
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.location = (-1000, 0)
        links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])

        def wire_image(key_names, target_socket, non_color=False, colsp=None):
            path = None
            for k in maps:
                if any(k.lower().startswith(kn) for kn in key_names):
                    path = maps[k]
                    break
            if not path:
                return
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = load_image(path, non_color=non_color)
            tex.location = (-500, -len(nodes) * 40)
            links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
            if target_socket == "normal":
                normal_map = nodes.new("ShaderNodeNormalMap")
                links.new(tex.outputs["Color"], normal_map.inputs["Color"])
                links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
            else:
                links.new(tex.outputs["Color" if not non_color else "Color"], bsdf.inputs[target_socket])

        wire_image(["diffuse", "color", "col_"], "Base Color")
        wire_image(["rough"], "Roughness", non_color=True)
        wire_image(["metal"], "Metallic", non_color=True)
        wire_image(["normal", "nor_gl", "nor"], "normal", non_color=True)
    return mat


def simple_material(name, color, roughness=0.7, metallic=0.0, alpha=1.0, transmission=0.0, specular=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    for spec_key in ("Specular IOR Level", "Specular"):
        if spec_key in bsdf.inputs:
            bsdf.inputs[spec_key].default_value = specular
            break
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    elif "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = transmission
    if alpha < 1.0:
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND"
        mat.show_transparent_back = True
    return mat


def add_box(w, h, d, x, y, z, ry=0.0, mat=None, name="Box", collection=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=P(x, y, z))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (w, d, h)
    obj.rotation_euler = (0, 0, ry)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if mat:
        obj.data.materials.append(mat)
    if collection:
        move_to_collection(obj, collection)
    return obj


def add_cylinder(r1, r2, h, x, y, z, ry=0.0, mat=None, name="Cyl", collection=None, vertices=24):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=h, location=P(x, y + h / 2, z))
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = (math.pi / 2, 0, 0)
    # Le cône Blender pointe le long de +Z local avant la rotation ci-dessus ;
    # on tourne autour de X pour le redresser le long de Z monde (car notre
    # mapping vertical est Blender Z = Three Y), puis on applique.
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=False)
    obj.rotation_euler = (0, 0, ry)
    if mat:
        obj.data.materials.append(mat)
    if collection:
        move_to_collection(obj, collection)
    return obj


def add_torus(major_r, minor_r, x, y, z, mat=None, name="Torus", collection=None):
    # Le tore de Blender est déjà créé à plat (axe du trou = Z monde), contrairement
    # à THREE.TorusGeometry qui a besoin d'une rotation : ici, aucune rotation requise.
    bpy.ops.mesh.primitive_torus_add(major_radius=major_r, minor_radius=minor_r, location=P(x, y, z),
                                      major_segments=96, minor_segments=16)
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    if collection:
        move_to_collection(obj, collection)
    return obj


def add_disc(radius, x, y, z, mat=None, name="Disc", collection=None, inner_radius=0.0):
    if inner_radius > 0:
        bpy.ops.mesh.primitive_circle_add(radius=radius, location=P(x, y, z), fill_type="NOTHING", vertices=96)
        obj = bpy.context.object
        # anneau plat : on extrude un léger biseau via une deuxième boucle serait
        # plus complexe qu'utile ici ; un simple disque aplati en guise d'anneau
        # au sol suffit visuellement pour la validation.
    bpy.ops.mesh.primitive_circle_add(radius=radius, location=P(x, y, z), fill_type="NGON", vertices=96)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = (0, 0, 0)
    if mat:
        obj.data.materials.append(mat)
    if collection:
        move_to_collection(obj, collection)
    return obj


def move_to_collection(obj, collection):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection.objects.link(obj)


def new_collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def look_at(obj, target):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


# ---------------------------------------------------------------- scène de base

clear_scene()

col_arch = new_collection("Lobby_Architecture")
col_furniture = new_collection("Lobby_Furniture")

SUN_DIR_THREE = mathutils.Vector((-0.72, 0.5, -0.46)).normalized()

# ---------------------------------------------------------------- matériaux

mat_floor = make_pbr_material("M_Floor_Stone", "floor_stone", base_color=(0.85, 0.83, 0.78, 1), roughness=0.25, uv_scale=6)
mat_wood_dark = make_pbr_material("M_Wood_Dark", "wood_dark", base_color=(0.16, 0.10, 0.07, 1), roughness=0.55, uv_scale=3)
mat_brass = make_pbr_material("M_Brass", "brass", base_color=(0.65, 0.49, 0.27, 1), roughness=0.3, metallic=0.9, uv_scale=2)
mat_leather = make_pbr_material("M_Leather", "leather", base_color=(0.54, 0.34, 0.20, 1), roughness=0.5, uv_scale=2)
mat_fabric = make_pbr_material("M_Fabric", "fabric", base_color=(0.11, 0.19, 0.32, 1), roughness=0.9, uv_scale=3)
mat_terracotta = make_pbr_material("M_Terracotta", "terracotta", base_color=(0.65, 0.35, 0.23, 1), roughness=0.8, uv_scale=2)

mat_glass = simple_material("M_Glass", (0.84, 0.90, 0.94), roughness=0.04, transmission=1.0, alpha=0.2)
mat_column = simple_material("M_Column", (0.95, 0.94, 0.91), roughness=0.4)
mat_medallion_navy = simple_material("M_Medallion_Navy", (0.04, 0.07, 0.13), roughness=0.9, specular=0.1)
mat_rug = simple_material("M_Rug", (0.79, 0.71, 0.58), roughness=0.9)

# Claustra en terre cuite ajourée : motif de perforation procédural (losanges)
# en plus de la couleur terre cuite, car Poly Haven ne fournit pas de découpe
# toute faite pour ce motif précis.
def make_claustra_material():
    mat = bpy.data.materials.new("M_Claustra")
    mat.use_nodes = True
    mat.blend_method = "CLIP"
    mat.show_transparent_back = False
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.62, 0.33, 0.20, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (8, 8, 8)
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.inputs["Scale"].default_value = 3.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[1].position = 0.55
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Alpha"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


mat_claustra = make_claustra_material()

# ---------------------------------------------------------------- sol et médaillon

add_box(44, 0.2, 44, 0, -0.1, -5, mat=mat_floor, name="Floor_Main", collection=col_arch)
add_disc(6.8, 0, 0.02, -5, mat=mat_medallion_navy, name="Medallion", collection=col_arch)
add_disc(10.0, 0, 0.019, -5, mat=mat_brass, name="Medallion_Ring_Base", collection=col_arch)
add_disc(9.85, 0, 0.021, -5, mat=mat_medallion_navy, name="Medallion_Ring_Cut", collection=col_arch)

# ---------------------------------------------------------------- anneau suspendu en bronze

add_torus(9.0, 0.13, 0, 9.5, -5, mat=mat_brass, name="Ring_Outer", collection=col_arch)
add_torus(8.4, 0.05, 0, 9.15, -5, mat=mat_brass, name="Ring_Inner", collection=col_arch)
for i in range(4):
    a = i * math.pi / 2 + math.pi / 4
    cx, cz = math.sin(a) * 9, math.cos(a) * 9
    add_cylinder(0.015, 0.015, 1.0, cx, 9.5, cz - 5, mat=mat_brass, name=f"Ring_Cable_{i}", collection=col_arch)

# ---------------------------------------------------------------- colonnes + pergola (zone 42x42, rayon 21)

for i in range(8):
    a = (i * 45 + 22.5) * math.pi / 180
    x, z = math.sin(a) * 21, math.cos(a) * 21
    add_cylinder(0.55, 0.5, 10, x, 0, z - 5, mat=mat_column, name=f"Column_{i}", collection=col_arch)

for v in (-19.4, 19.4):
    add_box(40, 0.35, 0.45, 0, 10.2, v - 5, mat=mat_wood_dark, name=f"Pergola_Beam_X_{v}", collection=col_arch)
    add_box(0.45, 0.35, 40, v, 10.2, -5, mat=mat_wood_dark, name=f"Pergola_Beam_Z_{v}", collection=col_arch)

for i in range(35):
    x = -20.4 + i * 1.2
    add_box(0.14, 0.4, 42, x, 10.6, -5, mat=mat_wood_dark, name=f"Pergola_Slat_{i}", collection=col_arch)

# ---------------------------------------------------------------- façades vitrées (2 côtés, vue lagune à l'ouest)

def facade(horizontal, fixed, a, b):
    length = b - a
    mid = (a + b) / 2
    if horizontal:
        add_box(length, 1.1, 0.3, mid, 0.55, fixed - 5, mat=mat_wood_dark, name="Facade_Base", collection=col_arch)
        add_box(length, 0.45, 0.45, mid, 10.95, fixed - 5, mat=mat_wood_dark, name="Facade_Top", collection=col_arch)
        glass = add_box(length, 9.7, 0.05, mid, 5.95, fixed - 5, mat=mat_glass, name="Facade_Glass", collection=col_arch)
    else:
        add_box(0.3, 1.1, length, fixed, 0.55, mid - 5, mat=mat_wood_dark, name="Facade_Base", collection=col_arch)
        add_box(0.45, 0.45, length, fixed, 10.95, mid - 5, mat=mat_wood_dark, name="Facade_Top", collection=col_arch)
        glass = add_box(0.05, 9.7, length, fixed, 5.95, mid - 5, mat=mat_glass, name="Facade_Glass", collection=col_arch)
    return glass


facade(False, -21, -21, 21)   # mur ouest : vue sur la lagune
facade(True, 21, -21, 21)     # mur sud

# ---------------------------------------------------------------- banque d'accueil

add_box(6, 1.1, 1.3, -9, 0.55, 3, mat=mat_wood_dark, name="Reception_Counter", collection=col_arch)
add_box(6.1, 0.06, 1.4, -9, 1.13, 3, mat=mat_brass, name="Reception_Trim", collection=col_arch)
add_box(4.4, 1.3, 0.12, -9, 2.9, 1.5, mat=mat_medallion_navy, name="Reception_Backdrop", collection=col_arch)
add_box(0.12, 2.3, 0.12, -10.9, 1.15, 1.5, mat=mat_brass, name="Reception_Post_L", collection=col_arch)
add_box(0.12, 2.3, 0.12, -7.1, 1.15, 1.5, mat=mat_brass, name="Reception_Post_R", collection=col_arch)

# ---------------------------------------------------------------- claustras en terre cuite

for x in (-14.5, 14.5):
    p = add_box(7, 4.2, 0.08, x, 2.25, -15.5, mat=mat_claustra, name=f"Claustra_{x}", collection=col_arch)
    add_box(0.2, 0.15, 7.2, x, 4.4, -15.5, mat=mat_wood_dark, name=f"Claustra_Top_{x}", collection=col_arch)
    add_box(0.2, 0.15, 7.2, x, 0.08, -15.5, mat=mat_wood_dark, name=f"Claustra_Bottom_{x}", collection=col_arch)

# ---------------------------------------------------------------- mobilier : import Poly Haven ou fallback procédural

def import_gltf_model(need_name):
    folder = os.path.join(ASSETS_DIR, "models", need_name)
    if not os.path.isdir(folder):
        return None
    gltf_path = None
    for root, _, files in os.walk(folder):
        for fn in files:
            if fn.lower().endswith((".gltf", ".glb")):
                gltf_path = os.path.join(root, fn)
    if not gltf_path:
        return None
    before = set(bpy.data.objects.keys())
    try:
        bpy.ops.import_scene.gltf(filepath=gltf_path)
    except RuntimeError as e:
        print(f"!! Import glTF échoué pour {need_name} ({gltf_path}) : {e}")
        print(f"   -> une forme simple sera utilisée à la place.")
        return None
    new_objs = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]
    if not new_objs:
        return None
    # On regroupe l'import dans un seul Empty pour le positionner/dupliquer facilement.
    bpy.ops.object.empty_add(type="PLAIN_AXES")
    root = bpy.context.object
    root.name = f"Imported_{need_name}"
    for o in new_objs:
        if o.parent is None:
            o.parent = root
    return root


def place(root_template, x, y, z, ry=0.0, scale=1.0, name=None):
    if root_template is None:
        return None
    dup = root_template.copy()
    dup.name = name or f"{root_template.name}_copy"
    bpy.context.collection.objects.link(dup)
    for child in root_template.children:
        c = child.copy()
        c.data = child.data  # partage des données maillage : léger en mémoire
        c.parent = dup
        bpy.context.collection.objects.link(c)
    dup.location = P(x, y, z)
    dup.rotation_euler = (0, 0, ry)
    dup.scale = (scale, scale, scale)
    move_to_collection(dup, col_furniture)
    return dup


armchair_tpl = import_gltf_model("model_armchair")
table_tpl = import_gltf_model("model_coffee_table")
lamp_tpl = import_gltf_model("model_lamp")
plant_tpl = import_gltf_model("model_plant")

if armchair_tpl:
    move_to_collection(armchair_tpl, col_furniture)
if table_tpl:
    move_to_collection(table_tpl, col_furniture)
if lamp_tpl:
    move_to_collection(lamp_tpl, col_furniture)
if plant_tpl:
    move_to_collection(plant_tpl, col_furniture)


def fallback_chair(x, y, z, ry):
    # Le dossier est décalé derrière l'assise, dans la direction opposée à celle
    # où le fauteuil fait face (vecteur local (0,-0.38) tourné de ry).
    back_x = x - 0.38 * math.sin(ry)
    back_z = z - 0.38 * math.cos(ry)
    add_box(0.95, 0.42, 0.9, x, y + 0.21, z, ry=ry, mat=mat_leather, name="Chair_Seat", collection=col_furniture)
    add_box(0.95, 0.62, 0.16, back_x, y + 0.6, back_z, ry=ry, mat=mat_leather, name="Chair_Back", collection=col_furniture)


def fallback_plant(x, y, z):
    add_cylinder(0.4, 0.32, 0.6, x, y, z, mat=mat_terracotta, name="Plant_Pot", collection=col_furniture)


# Deux salons (îlots), comme buildLobbyIslands() dans pavillon.html
for cx, cz in ((-13, 9), (13, 9)):
    add_disc(2.9, cx, 0.014, cz - 5, mat=mat_rug, name=f"Rug_{cx}", collection=col_furniture)
    if table_tpl:
        place(table_tpl, cx, 0, cz - 5, scale=1.0, name=f"Table_{cx}")
    else:
        add_cylinder(0.6, 0.6, 0.4, cx, 0, cz - 5, mat=mat_wood_dark, name=f"Table_{cx}", collection=col_furniture)
    for dx, dz, ry in ((-1.75, 0, math.pi / 2), (1.75, 0, -math.pi / 2), (0, -1.75, 0), (0, 1.75, math.pi)):
        if armchair_tpl:
            place(armchair_tpl, cx + dx, 0, cz + dz - 5, ry=ry, name=f"Chair_{cx}_{dx}_{dz}")
        else:
            fallback_chair(cx + dx, 0, cz + dz - 5, ry)
    lx = cx + (-2.4 if cx < 0 else 2.4)
    if lamp_tpl:
        place(lamp_tpl, lx, 0, cz - 2.2 - 5, name=f"Lamp_{cx}")
    else:
        add_cylinder(0.22, 0.3, 0.32, lx, 1.6, cz - 2.2 - 5, mat=mat_brass, name=f"Lamp_{cx}", collection=col_furniture)

# Plantes en pot (palmiers / monstera), positions reprises de buildWorld()
plant_positions = [(-15, 16), (15, 16), (-6.5, -20.5), (6.5, -20.5)]
for x, z in plant_positions:
    if plant_tpl:
        place(plant_tpl, x, 0, z - 5, name=f"Plant_{x}_{z}")
    else:
        fallback_plant(x, 0.3, z - 5)

# ---------------------------------------------------------------- éclairage : soleil bas + HDRI

world = bpy.data.worlds.new("World_GoldenHour")
bpy.context.scene.world = world
world.use_nodes = True
wnodes = world.node_tree.nodes
wlinks = world.node_tree.links
wnodes.clear()
bg = wnodes.new("ShaderNodeBackground")
out = wnodes.new("ShaderNodeOutputWorld")
hdri_dir = os.path.join(ASSETS_DIR, "hdri")
hdri_path = None
if os.path.isdir(hdri_dir):
    for fn in os.listdir(hdri_dir):
        if fn.lower().endswith((".hdr", ".exr")):
            hdri_path = os.path.join(hdri_dir, fn)
            break
if hdri_path:
    env = wnodes.new("ShaderNodeTexEnvironment")
    env.image = load_image(hdri_path)
    wlinks.new(env.outputs["Color"], bg.inputs["Color"])
else:
    bg.inputs["Color"].default_value = (0.85, 0.75, 0.6, 1)
bg.inputs["Strength"].default_value = 1.0
wlinks.new(bg.outputs["Background"], out.inputs["Surface"])

sun_dir_blender = mathutils.Vector(P(SUN_DIR_THREE.x, SUN_DIR_THREE.y, SUN_DIR_THREE.z))
bpy.ops.object.light_add(type="SUN", location=sun_dir_blender * 50)
sun = bpy.context.object
sun.name = "Sun_GoldenHour"
sun.data.energy = 5.5
sun.data.color = (1.0, 0.78, 0.52)
sun.data.angle = math.radians(2.0)  # léger flou de pénombre, soleil bas réaliste
look_at(sun, (0, 0, 0))

# ---------------------------------------------------------------- caméras et rendu de validation

bpy.context.scene.render.engine = "CYCLES"
try:
    bpy.context.scene.cycles.device = "GPU"
except Exception:
    pass
bpy.context.scene.cycles.samples = 256
bpy.context.scene.cycles.use_denoising = True
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
bpy.context.scene.render.image_settings.file_format = "PNG"

VIEWS = {
    "01_entree": {"pos": P(0, 1.6, 18), "look": P(0, 2.0, -8)},
    "02_vers_auditorium": {"pos": P(-6, 1.6, 6), "look": P(0, 3.5, -19.4)},
    "03_salon": {"pos": P(-6, 1.6, 4), "look": P(-13, 0.6, 9 - 5)},
    "04_vers_lagune": {"pos": P(4, 1.6, 0 - 5), "look": P(-21, 3, 0 - 5)},
}

cam_data = bpy.data.cameras.new("LobbyCam")
cam_data.lens = 24
cam_obj = bpy.data.objects.new("LobbyCam", cam_data)
bpy.context.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

for view_name, view in VIEWS.items():
    cam_obj.location = view["pos"]
    look_at(cam_obj, view["look"])
    bpy.context.scene.render.filepath = os.path.join(RENDERS_DIR, f"{view_name}.png")
    print(f"Rendu : {view_name}")
    bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print(f"\n== Terminé == \nRendus dans {RENDERS_DIR}\nScène sauvegardée : {BLEND_OUT}")
print("Envoyez les 4 images du dossier renders/ pour validation avant l'étape 3 (bake_and_export.py).")
