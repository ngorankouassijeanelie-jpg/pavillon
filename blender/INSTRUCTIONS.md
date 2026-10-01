# Mode d'emploi — reconstruire le lobby avec Blender et Poly Haven

Ces 3 scripts tournent avec votre Blender 5.2.2, en ligne de commande,
sans ouvrir l'interface graphique. Chaque étape prend quelques minutes.

## Préparation

1. Placez ce dossier `blender/` à côté de `pavillon.html`, dans votre dossier
   **Pavillon Final** sur le Bureau. L'arborescence doit ressembler à :

   ```
   Pavillon Final/
     pavillon.html
     homme-tunique-wax-anime.glb
     blender/
       fetch_polyhaven_assets.py
       build_lobby_stage1.py
       bake_and_export.py
       INSTRUCTIONS.md
   ```

2. Ouvrez l'application **Terminal** (Cmd+Espace, tapez « Terminal »).
3. Déplacez-vous dans le dossier du projet :

   ```bash
   cd ~/Desktop/"Pavillon Final"
   ```

   (adaptez le chemin si le dossier n'est pas sur le Bureau)

## Étape 1 — Télécharger les ressources Poly Haven

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b --python blender/fetch_polyhaven_assets.py
```

Ça télécharge dans `assets/` : le ciel HDRI de fin de journée, les textures
(pierre, bois sombre, laiton, cuir, tissu, terre cuite) et le mobilier
(fauteuils, table basse, lampe, plante), tous CC0 depuis polyhaven.com.
Un fichier **ASSETS.md** est créé à la racine du projet avec le détail de
chaque ressource choisie — vous pouvez y jeter un œil, mais aucune action
n'est requise de votre part.

Si une ressource n'est pas trouvée, le script l'indique avec `!!` dans le
terminal et continue quand même : l'étape suivante utilisera une forme
simple à la place, rien ne bloque.

## Étape 2 — Construire le lobby et produire les rendus de validation

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b --python blender/build_lobby_stage1.py
```

Ça construit le lobby aux dimensions du prototype, pose l'éclairage (soleil
bas + ciel HDRI), et produit 4 images dans `renders/` :
`01_entree.png`, `02_vers_auditorium.png`, `03_salon.png`, `04_vers_lagune.png`.

**Envoyez-moi ces 4 images ici dans la conversation.** Je les regarde, et je
vous dis si on ajuste quelque chose ou si on peut continuer.

**Important : n'allez pas plus loin tant que je n'ai pas validé ces images.**

## Étape 3 — Précalculer l'éclairage et exporter (seulement après mon accord)

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b --python blender/bake_and_export.py
```

Ça précalcule la lumière (lightmap), crée les volumes de collision, et
produit `lobby.glb` à la racine du projet. Cette étape est plus longue que
les précédentes (le calcul de lumière peut prendre plusieurs minutes).

**Envoyez-moi ensuite `lobby.glb`** (et dites-moi sa taille affichée dans le
Finder) : je l'intègre dans `pavillon.html` à la place du lobby actuel.

## En cas de problème

- Une ligne commençant par `!!` dans le terminal est un avertissement, pas
  forcément bloquant : copiez-collez-moi le message et je vous dis quoi
  faire.
- Si le Terminal affiche une longue erreur rouge (« Traceback »), copiez tout
  le texte et envoyez-le-moi : je corrige le script.
