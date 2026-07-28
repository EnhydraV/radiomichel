#!/usr/bin/env python3
"""Mise a jour automatique de GuSi.

Deux choses independantes :
  1. le code du depot, recupere depuis GitHub (git fetch + reset --hard) ;
  2. la liste des stations, decrite par un manifeste JSON heberge sur GitHub.

Chaque station du manifeste porte une url, un type ("stream" ou "mp3") et une
date de mise a jour. Un stream est joue directement par MPD ; un mp3 est
telecharge dans /var/lib/mpd/music et n'est re-telecharge que si sa date a
change.

Utilisable en direct (`python3 updater.py`), depuis start.py au demarrage, ou
depuis une tache cron.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = "/var/lib/mpd/music"
STATE_DIR = "/var/lib/gusi"
CONFIG_FILE = os.path.join(STATE_DIR, "config.json")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
STATIONS_CACHE = os.path.join(STATE_DIR, "stations.json")
LOG_FILE = "/var/log/gusi-update.log"

MANIFEST_URL = ("https://raw.githubusercontent.com/EnhydraV/radiomichel/"
                "main/stations.json")
REPO_MANIFEST = os.path.join(REPO_DIR, "stations.json")

DEFAULT_LANGUAGE = "FR"
HTTP_TIMEOUT = 30
DOWNLOAD_ATTEMPTS = 2
USER_AGENT = "gusi-radio-updater/1"
UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]+")

# Dernier repli : si ni le cache local ni aucun manifeste n'est lisible, la
# radio doit quand meme jouer quelque chose.
FALLBACK_STATIONS = [
    {"id": "live", "name": "Radio Michel Live", "type": "stream",
     "uri": "https://listen.radioking.com/radio/142981/stream/183163",
     "announcement": "s1.mp3"},
    {"id": "rmil", "name": "Radio Michel", "type": "mp3",
     "uri": "rmil.mp3", "announcement": "s2.mp3"},
    {"id": "rm20240111", "name": "Radio Michel", "type": "mp3",
     "uri": "rm20240111.mp3", "announcement": "s3.mp3"},
]


#---------- UTILITAIRES ----------#
def log(message):
    line = "%s [update] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    print(line)
    try:
        with open(LOG_FILE, "a") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def read_json(path):
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_json(path, data):
    """Ecriture atomique : le lecteur ne voit jamais un fichier tronque."""
    temporary = path + ".tmp"
    try:
        with open(temporary, "w") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
        return True
    except OSError as error:
        log("cannot write %s: %s" % (path, error))
        try:
            os.remove(temporary)
        except OSError:
            pass
        return False


def ensure_directories():
    for path in (STATE_DIR, MUSIC_DIR):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as error:
            log("cannot create %s: %s" % (path, error))


def load_config():
    config = read_json(CONFIG_FILE)
    if not isinstance(config, dict):
        config = {}
    return {
        "language": config.get("language", DEFAULT_LANGUAGE),
        "manifest_url": config.get("manifest_url", MANIFEST_URL),
        "update_code": config.get("update_code", True),
    }


#---------- MISE A JOUR DU CODE ----------#
def git(arguments):
    """Retourne (code de retour, sortie standard nettoyee)."""
    try:
        process = subprocess.Popen(
            ["git"] + arguments,
            cwd=REPO_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output, _ = process.communicate(timeout=120)
        return process.returncode, output.decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError) as error:
        return 1, str(error)


def update_code():
    """git fetch + reset --hard sur la branche suivie. Retourne True si le
    depot a bouge. ATTENTION : les modifications locales non commitees du
    depot sont ecrasees, c'est voulu (appareil non modifiable a la main)."""
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        log("no git repository in %s, code update skipped" % REPO_DIR)
        return False

    code, branch = git(["rev-parse", "--abbrev-ref", "HEAD"])
    if code != 0 or not branch or branch == "HEAD":
        branch = "main"

    code, output = git(["fetch", "--quiet", "origin", branch])
    if code != 0:
        log("git fetch failed: %s" % output)
        return False

    _, before = git(["rev-parse", "HEAD"])
    code, output = git(["reset", "--hard", "origin/" + branch])
    if code != 0:
        log("git reset failed: %s" % output)
        return False
    _, after = git(["rev-parse", "HEAD"])

    if before == after:
        log("code already up to date (%s)" % after[:8])
        return False
    log("code updated %s -> %s" % (before[:8], after[:8]))
    git(["config", "core.fileMode", "false"])
    return True


def sync_announcements(language):
    """Recopie les mp3 de langue du depot vers le dossier de musique de MPD."""
    source = os.path.join(REPO_DIR, language)
    if not os.path.isdir(source):
        log("language folder %s not found" % source)
        return False

    changed = False
    for name in sorted(os.listdir(source)):
        if not name.lower().endswith(".mp3"):
            continue
        origin = os.path.join(source, name)
        target = os.path.join(MUSIC_DIR, name)
        try:
            if (os.path.exists(target)
                    and os.path.getsize(target) == os.path.getsize(origin)):
                continue
            shutil.copy2(origin, target)
            os.chmod(target, 0o644)
            changed = True
            log("announcement copied: %s" % name)
        except OSError as error:
            log("cannot copy %s: %s" % (name, error))
    return changed


#---------- MANIFESTE ----------#
def is_supported_url(url):
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def http_get(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=HTTP_TIMEOUT)  # nosem


def fetch_manifest(url):
    """Manifeste distant, sinon la copie du depot (mise a jour par git)."""
    if is_supported_url(url):
        try:
            with http_get(url) as response:
                manifest = json.loads(response.read().decode("utf-8"))
            log("manifest fetched from %s" % url)
            return manifest
        except (urllib.error.URLError, OSError, ValueError) as error:
            log("manifest download failed (%s), falling back to repository"
                % error)
    manifest = read_json(REPO_MANIFEST)
    if manifest is None:
        log("no usable manifest")
    return manifest


def safe_id(value, position):
    cleaned = UNSAFE_CHARS.sub("", str(value or "")).strip("-_")
    return cleaned or ("station%d" % (position + 1))


def manifest_stations(manifest):
    """Extrait et valide les entrees du manifeste."""
    if isinstance(manifest, dict):
        raw = manifest.get("stations")
    elif isinstance(manifest, list):
        raw = manifest
    else:
        raw = None
    if not isinstance(raw, list):
        return []

    stations = []
    for position, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        url = entry.get("url")
        if kind not in ("stream", "mp3"):
            log("station %d ignored: unknown type %r" % (position + 1, kind))
            continue
        if not is_supported_url(url):
            log("station %d ignored: invalid url %r" % (position + 1, url))
            continue
        if entry.get("enabled") is False:
            continue
        identifier = safe_id(entry.get("id"), position)
        stations.append({
            "id": identifier,
            "name": entry.get("name") or identifier,
            "type": kind,
            "url": url,
            "updated": str(entry.get("updated") or ""),
            "announcement": entry.get("announcement")
                            or ("s%d.mp3" % (position + 1)),
        })
    return stations


#---------- TELECHARGEMENT ----------#
def download(url, target):
    """Telechargement vers un .part puis remplacement atomique : MPD garde
    l'ancien fichier ouvert sans probleme s'il est en train de le lire."""
    partial = target + ".part"
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            with http_get(url) as response, open(partial, "wb") as handle:
                shutil.copyfileobj(response, handle, 64 * 1024)
            size = os.path.getsize(partial)
            if size == 0:
                raise OSError("empty file")
            os.replace(partial, target)
            os.chmod(target, 0o644)
            log("downloaded %s (%.1f MB)"
                % (os.path.basename(target), size / 1048576.0))
            return True
        except (urllib.error.URLError, OSError, ValueError) as error:
            log("download attempt %d/%d failed for %s: %s"
                % (attempt, DOWNLOAD_ATTEMPTS, url, error))
            try:
                os.remove(partial)
            except OSError:
                pass
            if attempt < DOWNLOAD_ATTEMPTS:
                time.sleep(3)
    return False


def resolve_stations(stations, state):
    """Transforme les entrees du manifeste en stations jouables par MPD.

    Un stream garde son url. Un mp3 devient un nom de fichier relatif au
    dossier de musique de MPD, telecharge si besoin. Une station de type mp3
    dont le fichier est absent est ecartee (plutot que de laisser le bouton
    tomber sur du silence) et sera retentee au prochain demarrage.
    """
    known = state.get("stations") if isinstance(state, dict) else None
    if not isinstance(known, dict):
        known = {}

    playable = []
    downloaded = False
    for station in stations:
        if station["type"] == "stream":
            playable.append({
                "id": station["id"],
                "name": station["name"],
                "type": "stream",
                "uri": station["url"],
                "announcement": station["announcement"],
            })
            continue

        filename = station["id"] + ".mp3"
        target = os.path.join(MUSIC_DIR, filename)
        exists = os.path.exists(target)
        previous = known.get(station["id"], {}).get("updated")

        if not exists:
            needed = True
        elif previous is None:
            # Fichier deja la mais jamais suivi (installation existante) : on
            # adopte la date du manifeste sans retelecharger.
            needed = False
            log("%s already present, adopting date %s"
                % (filename, station["updated"] or "-"))
        else:
            needed = previous != station["updated"]

        if needed and download(station["url"], target):
            downloaded = True
            exists = True
        elif needed:
            exists = os.path.exists(target)

        if not exists:
            log("station %s skipped: %s missing" % (station["id"], filename))
            continue

        known[station["id"]] = {
            "updated": station["updated"],
            "file": filename,
            "url": station["url"],
        }
        playable.append({
            "id": station["id"],
            "name": station["name"],
            "type": "mp3",
            "uri": filename,
            "announcement": station["announcement"],
        })

    state["stations"] = known
    state["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return playable, downloaded


def mpc_update():
    try:
        subprocess.call(["mpc", "update"], timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        log("mpc update failed: %s" % error)


#---------- API ----------#
def run_update():
    """Cycle complet. Retourne la liste des stations jouables."""
    ensure_directories()
    config = load_config()

    if config["update_code"]:
        update_code()
    files_changed = sync_announcements(config["language"])

    manifest = fetch_manifest(config["manifest_url"])
    stations = manifest_stations(manifest)
    if not stations:
        log("no valid station in manifest, keeping previous list")
        return load_stations()

    state = read_json(STATE_FILE) or {}
    playable, downloaded = resolve_stations(stations, state)
    if not playable:
        log("no playable station after update, keeping previous list")
        return load_stations()

    if downloaded or files_changed:
        mpc_update()

    write_json(STATE_FILE, state)
    write_json(STATIONS_CACHE, {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stations": playable,
    })
    log("%d station(s) available: %s"
        % (len(playable), ", ".join(s["id"] for s in playable)))
    return playable


def offline_stations(manifest):
    """Stations utilisables sans reseau : streams + mp3 deja presents."""
    playable = []
    for station in manifest_stations(manifest):
        if station["type"] == "stream":
            uri = station["url"]
        else:
            uri = station["id"] + ".mp3"
            if not os.path.exists(os.path.join(MUSIC_DIR, uri)):
                continue
        playable.append({
            "id": station["id"],
            "name": station["name"],
            "type": station["type"],
            "uri": uri,
            "announcement": station["announcement"],
        })
    return playable


def load_stations():
    """Lecture seule, pour gusi.py : cache, puis manifeste du depot, puis
    liste de repli."""
    cached = read_json(STATIONS_CACHE)
    if isinstance(cached, dict) and cached.get("stations"):
        return cached["stations"]

    stations = offline_stations(read_json(REPO_MANIFEST))
    if stations:
        log("station cache missing, using repository manifest")
        return stations

    log("no station list available, using fallback")
    return list(FALLBACK_STATIONS)


if __name__ == "__main__":
    sys.exit(0 if run_update() else 1)
