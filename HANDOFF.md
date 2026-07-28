# HANDOFF — radiomichel (fork GuSi-Radio)

## Contexte

Radio internet sur Raspberry Pi Zero (fork de GuSi-Radio, customisé « Radio Michel »).
Le dépôt est cloné sur l'appareil dans `/root/gusi-radio`, remote
`https://github.com/EnhydraV/radiomichel` (branche `main`).

Chaîne de démarrage : `/etc/rc.local` → joue `boot.mp3` → `start.py`
(vérifs DHCP / réseau local / internet) → `updater.py` → `gusi.py` (boucle GPIO :
bouton = station suivante, encodeur rotatif = volume). Audio via MPD/`mpc`, dossier
de musique `/var/lib/mpd/music`.

Deux variantes de démarrage maintenues : `start.py` (Bullseye, dhcpcd) et
`start_Bookworm.py` (Bookworm, NetworkManager). Code Python compatible 3.9+, stdlib
uniquement (+ gpiozero).

## Session 2026-07-28 — mise à jour automatique + stations en JSON

### Ce qui a été fait

Ajout d'un système de mise à jour automatique au démarrage et externalisation des
stations dans un manifeste JSON hébergé sur GitHub.

**Nouveau — `updater.py`** : un seul module, appelable en direct
(`sudo python3 /root/gusi-radio/updater.py`), depuis `start.py` ou par cron.
- `update_code()` : `git fetch origin <branche>` + `git reset --hard`. Écrase les
  modifications locales du dépôt (volontaire : appareil non modifiable à la main).
- `sync_announcements(language)` : recopie `<REPO>/<LANG>/*.mp3` vers
  `/var/lib/mpd/music` si taille différente ou fichier absent.
- `fetch_manifest()` : télécharge `stations.json` depuis raw.githubusercontent.com,
  repli sur la copie du dépôt.
- `resolve_stations()` : `stream` → url jouée telle quelle ; `mp3` → téléchargé en
  `<id>.mp3` (id assaini, pas de traversée de chemin) via `.part` + `os.replace`
  atomique, uniquement si `updated` a changé. Station mp3 dont le fichier manque =
  écartée de la rotation, retentée au boot suivant.
- `load_stations()` (utilisé par `gusi.py`, lecture seule) : cache
  `/var/lib/gusi/stations.json` → manifeste du dépôt (streams + mp3 déjà présents) →
  `FALLBACK_STATIONS` en dur. La radio joue toujours quelque chose.
- Logs : `/var/log/gusi-update.log`.

**Nouveau — `stations.json`** (racine du dépôt, servi par GitHub) : `id`, `name`,
`type` (`stream`|`mp3`), `url`, `updated`, `announcement` (optionnel, défaut
`s<position>.mp3`), `enabled` (optionnel).

**Nouveau — `/var/lib/gusi/`** (hors dépôt, survit aux `git reset`) :
`config.json` (`language`, `manifest_url`, `update_code`), `state.json` (dates
`updated` suivies par station), `stations.json` (liste résolue pour gusi.py).

**Modifié**
- `gusi.py` : stations lues via `updater.load_stations()`, plus de `S1/S2/S3`.
  Tous les `os.system("mpc ...")` remplacés par `subprocess.call(["mpc", ...])` —
  les uri viennent maintenant d'un JSON distant, plus question de les passer au shell.
  Nombre de stations dynamique, annonce portée par la station.
- `start.py` et `start_Bookworm.py` : `run_update()` appelé juste après la
  validation internet, avant le lancement de `gusi.py` (LED clignote vite, timeout
  600 s, échec non bloquant).
- `setup_gusi_FR.sh` : crée `/var/lib/gusi/config.json`, lance un premier
  `updater.py` après le démarrage de MPD, suppression des `wget` commentés.
- `README.md` : section 4.1 réécrite (stations.json au lieu de gusi.py) + nouvelle
  section 4.3 « Automatic update ».

### Décisions à connaître

- **Fichier mp3 déjà présent mais inconnu de `state.json`** → adopté sans
  retéléchargement (évite de retélécharger l'existant au premier update sur un
  appareil déjà installé). Corollaire : si le fichier local est en réalité périmé,
  il faut modifier `updated` dans le manifeste pour forcer le téléchargement.
- **Uri mp3 relatives** (`rmil.mp3`) et non absolues comme avant
  (`/var/lib/mpd/music/rmil.mp3`) : c'est la forme sûre pour `mpc add`.
- **`setup_gusi_EN.sh` / `setup_gusi_DE.sh` non touchés** : ils suppriment `.git`
  et les dossiers de langue en fin d'installation, donc incompatibles avec la mise
  à jour par git. Seule la variante FR est câblée.
- Mise à jour au boot uniquement ; cron documenté dans le README pour les radios
  qui restent allumées.

### Vérifications faites

- Cycle complet de `updater.py` testé hors Raspberry (serveur HTTP local, chemins
  redirigés) : premier update, idempotence, retéléchargement sur changement de date,
  404 → station écartée, manifeste injoignable → repli dépôt → cache → fallback,
  id piégé `../../etc/passwd` assaini, annonce recopiée.
- `update_code()` testé sur un clone jetable : pull effectif, écrasement d'une
  modification locale, second appel « already up to date ».
- Semgrep (`p/python`, `p/security-audit`) sur les 4 fichiers Python : 0 finding.

### Non fait / pistes

- Aucun test sur le matériel réel (pas de Pi ici) : `gpiozero`, MPD et les GPIO ne
  sont pas testables dans le conteneur. À valider sur l'appareil.
- Les urls de `stations.json` (`radiomichel.enhydra.fr`, radioking) sont reprises des
  anciens scripts, non vérifiées en ligne.
- `start.py` / `start_Bookworm.py` conservent un `SyntaxWarning` préexistant
  (regex `"inet (\d+...)"` sans préfixe `r`), hors périmètre.
- Pas de vérification d'intégrité des mp3 téléchargés (pas de somme de contrôle dans
  le manifeste) ; un champ `sha256` serait facile à ajouter si besoin.
