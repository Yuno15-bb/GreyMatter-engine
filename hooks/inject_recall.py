#!/usr/bin/env python3
"""inject_recall — hook UserPromptSubmit : rappel de mémoire pertinente, À LA DEMANDE.

Le hook lance brain_recall sur la demande et peut injecter en contexte les 2-3 fiches du
C Brain les plus pertinentes (nom + description + chemin).

⚠️ DEPUIS LE 2026-09-09, IL N'AFFICHE PLUS RIEN TOUT SEUL. Décision de l'utilisateur, sur mesure :
sur 30 jours, 4,27 % des fiches proposées étaient ensuite ouvertes (139 / 3 256) et 1,95 %
sur les 7 derniers jours ; dans l'autre sens, quand une fiche finissait par être lue, la
suggestion l'avait devinée 8,8 % du temps. Le bloc coûtait donc son bruit à chaque message
pour un service rendu 2 à 4 fois sur 100. Mesure d'août : 1,98 % — un an... un mois sans
la moindre amélioration.

⚠️ CE QUI N'EST PAS SUPPRIMÉ, ET NE DOIT PAS L'ÊTRE : la RECHERCHE. 61 % des fiches
réellement ouvertes ne sont pas nommées dans MEMORY.md (193 / 495 sur 30 jours) — sans
moyen de fouiller, ce savoir-là devient introuvable. Trois portes restent ouvertes :
  - `./brain recall "ma question"` en ligne de commande (inchangé) ;
  - un mot-clé dans le message (voir DEMANDES et MARQUEUR ci-dessous) ;
  - BRAIN_RECALL_AUTO=1 dans l'environnement, qui rétablit l'ancien comportement.

Le calcul BM25, lui, TOURNE TOUJOURS à chaque message (~105 ms, aucun token) : c'est lui
qui alimente l'instrument A8.8 `state/requete-forme.jsonl` et le canal held-out. Les
couper aurait éteint en silence une mesure en cours.

Garde-fous :
  - n'affiche QUE sur demande explicite, et QUE si la pertinence dépasse un seuil,
  - silencieux et non bloquant : sort toujours 0, n'injecte rien en cas de souci,
  - léger : pointeurs (nom/desc/chemin), pas le contenu intégral → coût en tokens minime.
"""
import os, re, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import brain_recall as recall
except Exception:
    recall = None
try:
    from context_usage import read_context_tokens
except Exception:
    def read_context_tokens(_transcript_path):
        return None

sys.path.insert(0, os.path.expanduser("~/brain-v3-lab/lab"))
try:
    import moteur                      # le dispatcher : LUI seul décide
except Exception:
    moteur = None

TOP_K = 3
MIN_SCORE = 4.0   # en dessous : pas assez pertinent → on n'injecte rien
CONTEXT_WARN_TOKENS = 300_000

# ─── Le rappel est passé « à la demande » le 2026-09-09 ────────────────────────────────
# Le marqueur est volontairement imprononçable en français courant : il ne peut pas se
# déclencher par accident. Les phrases, elles, sont toutes des DEMANDES de recherche —
# on exige un verbe d'intention, jamais le seul mot « brain » : ce mot revient dans un
# tiers des lectures du mois (le Brain qui parle de lui-même), il rallumerait le bruit
# exactement là où il était le plus dense.
MIN_SCORE_DEMANDE = 1.0   # sur demande explicite, on répond même faiblement : voir nettoyer()
MARQUEUR = "?brain"
DEMANDES = (
    "cherche dans le brain", "cherche dans la memoire", "cherche dans les fiches",
    "fouille le brain", "fouille la memoire",
    "regarde dans le brain", "regarde dans la memoire",
    "que dit le brain", "qu en dit le brain", "qu est ce que dit le brain",
    "rappel brain", "rappelle le brain", "brain recall",
    "une fiche sur", "des fiches sur", "une lecon sur", "des lecons sur",
    "on a deja vu", "on l a deja vu", "deja croise ca",
)


def _fold(s):
    """minuscule, sans accents, apostrophes et ponctuation ramenées à l'espace.

    Écrit ici plutôt qu'importé de brain_recall : la détection de la demande doit
    fonctionner même quand le moteur de rappel est injoignable, sinon un import raté
    rendrait le mot-clé muet sans que rien ne le dise.
    """
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9?]+", " ", s)


def demande_explicite(prompt):
    """l'auteur a-t-il DEMANDÉ une recherche dans CE message ?

    ⚠️ CETTE FONCTION NE RÉPOND PLUS « EST-CE QU'ON AFFICHE » (corrigé le 2026-09-20).
    Jusqu'ici elle rendait True dès que `BRAIN_RECALL_AUTO=1`, et ce raccourci rendait
    fausse la promesse écrite partout — « BRAIN_RECALL_AUTO=1 remet l'ancien
    comportement ». Un seul nom portait deux questions : « on affiche ? » et « quelle
    barre ? ». L'interrupteur répondait oui aux DEUX, il repassait donc la barre de
    demande explicite (`MIN_SCORE_DEMANDE`, 1.0) là où l'ancien comportement montait à
    `MIN_SCORE` (4.0) — quatre fois plus exigeant. Mesuré ce jour-là sur un corpus de
    deux fiches : l'interrupteur affichait un bloc à 2,69, score qu'aucun rappel
    automatique n'aurait jamais montré avant le 09/09. Conséquence de bord : `MIN_SCORE`
    ne gouvernait plus qu'un chemin dont la sortie n'était affichée nulle part — une
    constante morte qui avait l'air vivante.

    Les deux questions sont maintenant séparées : celle-ci dit si l'auteur a demandé (elle
    choisit la barre et le nettoyage de la requête), `auto_arme()` dit si on a le droit
    de parler sans qu'il demande. Voir `un-champ-homonyme-fait-citer-un-chiffre-qui-
    mesure-autre-chose` : le défaut n'est pas le chiffre, c'est le nom qui en recouvre
    deux.
    """
    p = _fold(prompt)
    if _fold(MARQUEUR) in p:
        return True
    return any(d in p for d in DEMANDES)



def auto_arme():
    """Le rappel a-t-il le droit de parler SANS qu'on le lui demande ?

    C'est la marche arrière de la coupure du 2026-09-09 : elle rend l'affichage
    automatique, jamais l'indulgence du seuil. Un message ordinaire reste jugé à
    `MIN_SCORE`, et quand rien ne passe la barre il ne se passe RIEN — pas même le
    « rien trouvé », réservé à une vraie demande. Sans cette réserve, chaque message
    de la journée repartirait avec un bloc, ce qui est exactement le bruit qui a fait
    couper le rappel automatique.
    """
    return os.environ.get("BRAIN_RECALL_AUTO") == "1"


def nettoyer(prompt):
    """Retire les mots de la DEMANDE avant de chercher.

    Mesuré au premier essai, et c'est un vrai défaut, pas une précaution : « cherche dans
    le brain railway deploiement github » tombait à 3,195 de score quand « railway ne
    deploie pas mon service depuis github » montait à 4,947. Les quatre mots de la
    formule de politesse comptent dans le calcul et diluent la vraie question — la
    demande explicite se punissait donc elle-même, et se retrouvait sous le seuil.

    BM25 replie déjà minuscules et accents : lui passer la version repliée ne change
    rien à son résultat. Le prompt BRUT, lui, reste intact pour l'instrument A8.8.
    """
    p = _fold(prompt)
    p = p.replace(_fold(MARQUEUR), " ")
    for d in DEMANDES:
        p = p.replace(d, " ")
    p = " ".join(p.split())
    return p or _fold(prompt)


def context_notice(data):
    """Alerte indépendante du rappel ; aucune erreur ne doit bloquer le prompt."""
    try:
        used = read_context_tokens((data or {}).get("transcript_path"))
    except Exception:
        return None
    if used is None or used <= CONTEXT_WARN_TOKENS:
        return None
    return (
        f"<contexte> {used//1000}k tokens — privilégie les lectures ciblées, "
        "propose /clear si le chantier change. </contexte>"
    )


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    lines = []
    notice = context_notice(data)
    if notice:
        lines.append(notice)

    prompt = (data.get("prompt") or data.get("user_prompt") or "").strip()
    demande = demande_explicite(prompt)
    # `demande` choisit la BARRE et le nettoyage ; `afficher` choisit la PAROLE.
    afficher = demande or auto_arme()

    # UNE seule décision, prise ici. Avant, ce hook appelait BM25 en dur : le
    # pointeur `state/MOTEUR` ne commandait rien, et « basculer » se réduisait à
    # réécrire un fichier que personne ne lisait.
    choix = moteur.choisir() if moteur is not None else {"moteur": "v2"}

    results = []
    _bm25 = _records = None            # gardés pour l'instrumentation A8.8 (forme des requêtes)
    requete = nettoyer(prompt) if demande else prompt
    seuil = MIN_SCORE_DEMANDE if demande else MIN_SCORE
    if len(prompt) >= 8:
        if choix["moteur"] == "v3":
            try:
                from serveur import demander
                r = demander(requete, k=TOP_K)
                # Un index périmé ou un repli ne sont PAS le moteur V3 : plutôt
                # que d'injecter en se faisant passer pour lui, on redescend.
                if r.get("perime") or r.get("repli"):
                    choix = {"moteur": "v2", "demande": "v3",
                             "raison": r.get("perime") or r.get("repli")}
                else:
                    results = [(None, {"name": os.path.basename(f)[:-3], "path": f,
                                       "desc": ""}) for f in (r.get("resultats") or [])]
            except Exception:
                choix = {"moteur": "v2", "demande": "v3", "raison": "V3 injoignable"}
        if choix["moteur"] == "v2" and recall is not None:
            try:
                _bm25 = recall.BM25(recall.load_corpus())
                brut = _bm25.search(requete, TOP_K)
            except Exception:
                brut = []
            results = [(s, d) for s, d in brut if s >= seuil]

    if choix.get("force"):
        # Le contournement du gate ne doit jamais passer inaperçu.
        lines.append("<brain-moteur> ⚠️ MOTEUR V3 FORCÉ, gate court-circuité "
                     "(BRAIN_GATE_FORCE_VERT) — mode test uniquement </brain-moteur>")

    if results and afficher:
        lines += ["<brain-recall> Fiches du C Brain potentiellement pertinentes "
                  "pour cette demande (lis-les si utile, ignore sinon) :"]
        for s, d in results:
            desc = (" — " + d["desc"][:120]) if d["desc"] else ""
            lines.append(f"- {d['name']} ({d['path']}){desc}")
        lines.append("</brain-recall>")
    elif demande:
        # Sans cette ligne, une recherche vide et un mot-clé non reconnu se ressemblent
        # exactement — l'auteur ne saurait pas lequel des deux vient de se produire.
        lines.append("<brain-recall> Rien de pertinent trouvé dans le C Brain pour "
                     "cette demande. </brain-recall>")

    # stdout d'un hook UserPromptSubmit = contexte ajouté à la session
    if lines:
        print("\n".join(lines))

    # boucle de vérité (H3) : journaliser ce qui a été REMONTÉ (pour mesurer l'utilité).
    # ⚠️ On ne journalise QUE ce qui a été réellement affiché : écrire des propositions
    # que personne n'a vues fausserait le taux d'ouverture (le dénominateur gonflerait
    # sans que la fiche ait jamais eu sa chance d'être lue) et nourrirait le bonus
    # d'utilité de recall_feedback.py avec des lignes fantômes.
    if results and afficher:
        try:
            import time
            sid = data.get("session_id") or ""
            log = os.path.join(recall.BRAIN, "state", "recall_log.jsonl")
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                for s, d in results:
                    f.write(json.dumps({"ts": int(time.time()), "sid": sid,
                                        "path": d["path"],
                                        "score": round(s, 2) if s is not None else None,
                                        "moteur": choix["moteur"]},
                                       ensure_ascii=False) + "\n")
        except Exception:
            pass

    journaliser_forme(requete, _bm25, bool(results), choix,
                      data.get("session_id") or "", bool(results) and afficher,
                      seuil, demande)
    capturer_heldout(prompt, _bm25, data)


def capturer_heldout(prompt, bm25, data):
    """Canal d'ÉVALUATION, séparé d'A8.8 et ÉTEINT par défaut.

    Ne fait rien tant que `tests/heldout/PROTOCOLE.json` n'existe pas. Une fois armé, capture
    les N premières requêtes ÉLIGIBLES qui se présentent — consécutives, sans choisir — puis
    s'arrête seule. La consécutivité doit être mécanique : capturer « à la main » revient à
    retenir ce qui paraît intéressant, donc à déformer la distribution qu'on veut découvrir.

    ⚠️ Ce canal-ci conserve le TEXTE, dans tests/heldout/ (JSON, hors corpus, porte P1).
    `state/requete-forme.jsonl` reste, lui, sans aucun texte. Les deux ne se mélangent pas.
    """
    if bm25 is None or recall is None:
        return
    try:
        sys.path.insert(0, os.path.join(recall.BRAIN, "tests", "heldout"))
        import capture_heldout as ch
        if not os.path.exists(ch.PROTOCOLE):
            return                                   # non armé : rien, et sans coût
        if len(bm25.classer(prompt, 2)) < 2:
            return                                   # pas d'écart rang1/rang2 calculable
        tp = data.get("transcript_path") or ""
        kind = "agent" if "-Users-mac-claude-brain" in tp else (
               "humain" if "-Users-mac" in tp else "autre")
        ch.capturer(prompt, data.get("session_id") or "", kind)
    except Exception:
        pass


def journaliser_forme(requete, bm25, injecte, choix, sid, affiche=False,
                      seuil=None, demande=False):
    """A8.8 — enregistre la FORME de la requête, jamais son texte. Voir hooks/forme_requete.py.

    Journalise même quand RIEN n'a été injecté : savoir quelles formes ne déclenchent
    rien fait partie de la distribution qu'on cherche à connaître.
    Best-effort et silencieux : ce hook ne doit jamais faire échouer un prompt.

    ⚠️ LE JOURNAL ENREGISTRE SA RÈGLE, PAS SEULEMENT SA MESURE (corrigé le 2026-09-19).
    Jusqu'ici la ligne portait `s1` (le meilleur score vu) et `injecte` (« il y avait un
    candidat au-dessus du seuil »), mais JAMAIS le seuil lui-même — alors qu'il y en a
    deux, `MIN_SCORE` à 4.0 en automatique et `MIN_SCORE_DEMANDE` à 1.0 sur demande
    explicite. Le même nom de champ recouvrait donc deux règles différentes, choisies par
    une variable qui n'était écrite nulle part : une ligne `injecte: false, s1: 2.5` est
    illisible sans savoir si la barre était à 4.0 ou à 1.0. C'est le défaut d'homonymie
    de `un-champ-homonyme-fait-citer-un-chiffre-qui-mesure-autre-chose`, appliqué non plus
    au nom d'un champ mais à la règle invisible derrière lui. `seuil` et `demande` sont
    maintenant écrits sur chaque ligne ; leur ABSENCE date une ligne d'avant le 19/09.

    ⚠️ LA MESURE PORTE DÉSORMAIS SUR CE QUI A VRAIMENT ÉTÉ CHERCHÉ. Cette passe scorait
    `prompt` brut pendant que la production scorait `nettoyer(prompt)` sur une demande
    explicite : `s1` et `injecte` ne sortaient donc pas du même texte. Sans effet sur les
    1 809 lignes automatiques (où les deux sont identiques), correction réelle sur les 10
    lignes de demande explicite du journal au 19/09.
    """
    if bm25 is None or recall is None:
        return
    try:
        import time
        from forme_requete import mesurer
        # passe SÉPARÉE, à k=10 : la production garde son k=3 intact. Le moteur est déjà
        # construit et indexé, donc ce second classement ne recoûte que le scoring.
        records = bm25.classer(requete, 10)
        forme = mesurer(recall.tokenize(requete), records, k=10)
        # `injecte` garde son sens d'origine — « le moteur avait un candidat au-dessus du
        # seuil » — pour que la série A8.8 reste comparable de part et d'autre du
        # 2026-09-09. Le nouveau champ `affiche` dit ce qui a vraiment été montré.
        forme.update(ts=int(time.time()), sid=sid, injecte=injecte,
                     affiche=affiche, moteur=choix.get("moteur"),
                     seuil=seuil, demande=demande)
        chemin = os.path.join(recall.BRAIN, "state", "requete-forme.jsonl")
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(json.dumps(forme, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
