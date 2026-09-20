#!/usr/bin/env python3
"""
Statut partagé du C Brain — écrit state/status.json que la capsule lit.
Best-effort : n'échoue jamais, ne bloque jamais un hook.

Activités possibles (mappées à une animation dans la capsule) :
  distilling   ⚗️  extraction de fiches (distillateur)
  gardening    🌱  rangement global de l'arbre (jardinier)
  filing       📁  classement d'une fiche
  correcting   ✏️  correction / masquage de secret
  mapping      🗺️  mise à jour de la carte
  committing   💾  sauvegarde git
  challenging  🔴  mise à l'épreuve (challenger)
  archiving    🍂  tri du froid / archivage (archiviste)
  synthesizing 🕸️  tissage transverse (synthétiseur)
  auditing     🔧  audit/réparation de la machine (mécanicien)
  architecting 🏗️  cohésion globale / ponts inter-domaines (architecte)
  idle             au repos (Tamagotchi qui dort)

Usage CLI :  python3 brain_status.py <state> [activity] [detail]
"""
import json, os, time, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # CODE_ROOT, légitime
from brain_racine import brain_root

# I-1 (2026-08-21). Surface HUMAINE de diagnostic : un outil de statut qui lit
# silencieusement ~/.c-brain/trunk alors qu'on l'interroge sur un autre Brain rend une
# déclaration FAUSSE avec une apparence d'autorité. Mesuré le 2026-08-20 : `brain doctor`
# lancé dans un worktree annonçait les métriques du tronc auteur, sans le moindre signe.
STATE_DIR = os.path.join(brain_root(__file__), "state")
STATUS = os.path.join(STATE_DIR, "status.json")

def write_status(state, activity=None, detail=None, source=None):
    if source is None:
        source = "agent" if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1" else "you"
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = STATUS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"state": state, "activity": activity, "detail": detail,
                       "source": source, "ts": time.time()}, f, ensure_ascii=False)
        os.replace(tmp, STATUS)  # écriture atomique
    except Exception:
        pass

AGENTS_JOURNAL = os.path.join(STATE_DIR, "agents.jsonl")

def journal_agent(agent, phase, **champs):
    """Une ligne par PASSAGE D'AGENT, en ajout seul — la trace que status.json ne peut
    pas porter.

    Pourquoi ce fichier existe (19/09/2026) : status.json ne garde qu'UN état global,
    écrasé par le passage suivant ; upkeep.json ne compte que des totaux ; cost.jsonl
    porte le coût mais AUCUN nom d'agent. Impossible, avec ces trois-là, de dire ce
    qu'un agent donné a fait et quand. Le panneau des huit voyants (chantier MAGI) a
    besoin de cette ligne-là, sinon les huit cases affichent toutes la même chose.

    `phase` vaut "debut" ou "fin". Best-effort comme le reste du module : n'échoue
    jamais, ne bloque jamais un hook.
    """
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        ligne = {"agent": agent, "phase": phase, "ts": time.time()}
        # LE VAISSEAU EN PLUS DE LA MISSION (20/09/2026). Depuis le regroupement en
        # familles, `agent` nomme la mission ; un affichage par vaisseau devrait sinon
        # refaire la table de correspondance de son côté, et les deux dériveraient.
        try:
            from robots_permissions import FAMILLE
            if agent in FAMILLE:
                ligne["vaisseau"] = FAMILLE[agent]
        except Exception:
            pass
        ligne.update({k: v for k, v in champs.items() if v is not None})
        with open(AGENTS_JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return ligne["ts"]
    except Exception:
        return None


def touch_status():
    """HEARTBEAT : rafraîchit seulement `ts` du statut courant, sans toucher
    state/activity/detail. Appelé en boucle par auto_maintain pendant les longues
    passes d'agent (un `claude -p` dure des minutes) → la capsule reste « busy »
    tout du long au lieu de clignoter en idle quand sa fenêtre de fraîcheur expire.
    No-op si le fichier n'existe pas / est illisible (best-effort, ne casse rien)."""
    try:
        with open(STATUS, "r", encoding="utf-8") as f:
            cur = json.load(f)
        cur["ts"] = time.time()
        tmp = STATUS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
        os.replace(tmp, STATUS)
    except Exception:
        pass

ETATS = ("busy", "idle")   # le 1er argument est un ÉTAT ; l'activité est le 2e


def show_status():
    """AFFICHE le statut courant. Ne l'écrit JAMAIS.

    Existe depuis le 2026-08-04. Avant : `brain status` appelait `brain_status.py show`,
    or ce fichier n'était qu'un ÉCRIVAIN — « show » était donc pris pour un état et
    ENREGISTRÉ dans status.json. Résultat : la commande phare du CLI n'affichait rien
    (sortie vide, code 0, donc les replis `||` du script `brain` ne partaient pas) et
    corrompait au passage l'état que lit la capsule. Deux fautes en une ligne."""
    try:
        with open(STATUS, "r", encoding="utf-8") as f:
            s = json.load(f)
    except FileNotFoundError:
        print("(aucun statut : state/status.json absent)")
        return 0
    except Exception as e:
        print(f"(statut illisible : {e})")
        return 1
    age = time.time() - (s.get("ts") or 0)
    frais = age < 120
    etat = s.get("state") or "?"
    if etat not in ETATS:
        etat += "  ⚠️ état inconnu (status.json a été corrompu par un appel fautif)"
    print(f"état     : {etat}")
    print(f"activité : {s.get('activity') or '—'}")
    print(f"détail   : {s.get('detail') or '—'}")
    print(f"source   : {s.get('source') or '—'}")
    quand = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.get('ts') or 0))
    print(f"depuis   : {quand}  ({int(age)} s — {'frais' if frais else 'PÉRIMÉ, la capsule le lit comme idle'})")
    return 0



if __name__ == "__main__":
    a = sys.argv
    cmd = a[1] if len(a) > 1 else "idle"
    if cmd == "touch":
        touch_status()
    elif cmd == "journal":
        # `journal <mission> <debut|fin> [clé=valeur ...]` — la porte en ligne de commande
        # de journal_agent, ouverte le 20/09/2026 pour la couche 1. auto_maintain lance le
        # distillateur et le jardinier par un shell, pas par Python : sans ce verbe, les
        # DEUX agents les plus sollicités n'écrivaient aucune ligne, et tout affichage par
        # agent les déclarait « jamais vus ».
        if len(a) < 4:
            print("Usage : brain_status.py journal <mission> <debut|fin> [clé=valeur ...]",
                  file=sys.stderr)
            sys.exit(2)
        champs = {}
        for kv in a[4:]:
            k, _, v = kv.partition("=")
            try:
                champs[k] = float(v) if v.replace(".", "", 1).isdigit() else v
            except Exception:
                champs[k] = v
        journal_agent(a[2], a[3], **champs)
    elif cmd in ("show", "status"):
        sys.exit(show_status())
    elif cmd in ETATS:
        write_status(cmd, a[2] if len(a) > 2 else None, a[3] if len(a) > 3 else None)
    else:
        # REFUSER plutôt qu'enregistrer : n'importe quel mot était accepté comme état, donc
        # une faute de frappe empoisonnait silencieusement le fichier que lit la capsule.
        print(f"état inconnu : {cmd!r} — attendu {' | '.join(ETATS)} (ou touch / show).",
              file=sys.stderr)
        print("Usage : brain_status.py <busy|idle> [activité] [détail]  ·  ... touch  ·  ... show",
              file=sys.stderr)
        sys.exit(2)
