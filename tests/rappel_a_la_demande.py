#!/usr/bin/env python3
"""rappel_a_la_demande.py — le bloc <brain-recall> ne s'affiche QUE si on le demande.

L'INVARIANT (décidé par l'auteur le 2026-09-09, sur mesure) :

    Un message ordinaire ne déclenche AUCUNE injection de fiches.
    Un message qui demande explicitement une recherche en déclenche une, et
    reçoit toujours une réponse — même « rien trouvé ».
    Et l'instrument A8.8 (`state/requete-forme.jsonl`) continue d'être alimenté
    dans les DEUX cas.

POURQUOI IL EXISTE :

    Le rappel automatique a été mesuré sur 30 jours : 4,27 % des fiches proposées
    étaient ensuite ouvertes (139 / 3 256), 1,95 % sur les 7 derniers jours. Il
    coûtait son bruit à chaque message pour un service rendu 2 à 4 fois sur 100.
    Ce que la coupure ne doit PAS emporter, c'est la RECHERCHE : 61 % des fiches
    réellement ouvertes ne sont pas nommées dans MEMORY.md.

POURQUOI CE TEST PORTE SES PROPRES SABOTAGES :

    Une coupure ne rougit jamais toute seule. Si quelqu'un rétablit l'injection
    automatique, le Brain redevient bavard et rien ne le dit — le système marche,
    il coûte simplement à nouveau. Le test vérifie donc AUSSI que, privé de sa
    porte, le hook REDEVIENDRAIT bavard, et que privé de nettoyer() il
    REDEVIENDRAIT muet sur une demande formulée en français.

CE QU'IL NE VÉRIFIE PAS — DEUX ANGLES MORTS NOMMÉS (mesurés le 2026-09-20) :

    1. IL MESURE PARTIELLEMENT LA MACHINE. `lancer()` détourne `BRAIN_HOME` vers un
       faux tronc, mais laisse `$HOME` intact : le hook charge donc le vrai
       `~/brain-v3-lab/lab/moteur`, et c'est le pointeur `state/MOTEUR` de l'hôte qui
       décide quel moteur de recherche tourne. Mesuré ce jour-là : v2 des deux côtés,
       donc les résultats sont valides — mais si l'hôte basculait en v3, ce banc
       emprunterait une autre branche de code SANS LE DIRE. C'est l'entrée D2 de C bis.
       Le détourner vers un faux `$HOME` ne réparerait rien : le lab disparaîtrait du
       `sys.path` et le hook retomberait en silence sur v2, c'est-à-dire qu'il
       mesurerait une configuration qui n'est celle de personne.

    2. IL NE DIT PAS SI 4.0 EST LA BONNE VALEUR. Il verrouille QUELLE barre s'applique
       à quel chemin, jamais si la barre est bien placée. Le corpus d'essai compte
       dix-huit fiches et presque toute correspondance y dépasse 4.0 — la question du
       réglage reste ouverte et se mesure ailleurs.
"""
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
HOOK = os.path.join(BRAIN, "hooks", "inject_recall.py")

# Les DEUX barres du hook. Elles sont écrites ici pour être comparées à ce que le hook
# journalise — et `barres_declarees()` vérifie qu'elles n'ont pas dérivé dans la source,
# sans importer le hook (il insère des chemins et charge le moteur au passage).
BARRE_AUTO, BARRE_DEMANDE = 4.0, 1.0


def barres_declarees():
    src = open(HOOK, encoding="utf-8").read()
    lire = lambda nom: re.search(rf"^{nom}\s*=\s*([0-9.]+)", src, re.M)
    a, d = lire("MIN_SCORE"), lire("MIN_SCORE_DEMANDE")
    return (float(a.group(1)) if a else None, float(d.group(1)) if d else None)

# Vocabulaire inventé : le corpus d'essai ne doit dépendre d'AUCUNE fiche réelle,
# sinon renommer une fiche ferait rougir ce test pour une raison étrangère.
#
# Il est CALIBRÉ, pas décoratif, et la première version était fausse : avec 4 fiches,
# le meilleur score plafonnait à 3,64 — sous le seuil de 4,0. Le contrôle « un message
# ordinaire n'affiche rien » passait donc au vert parce que le moteur ne trouvait RIEN,
# pas parce que la porte tenait. C'est le sabotage n°1 qui l'a révélé en refusant de
# rougir. Il faut 18 fiches pour que la rareté des mots (l'IDF de BM25) fasse monter
# le score de la cible à 13,65, franchement au-dessus du seuil.
#
# Les deux fiches `brain-*` sont là pour le sabotage n°2 : elles parlent le vocabulaire
# de la DEMANDE elle-même (« cherche », « brain », « fiche »). Sans nettoyer(), les mots
# de la question viennent donc squatter la réponse — c'est exactement le défaut mesuré.
FICHES = {
    "zorglub-cadrage": "Le zorglub de cadrage se pose avant toute mesure : sans zorglub de cadrage, le zorglub dérive et la mesure du zorglub ne veut plus rien dire.",
    "zorglub-panne": "Quand le zorglub tombe en panne, relire le cadrage avant de toucher au zorglub.",
    "brain-recherche": "Chercher dans le brain : la recherche du brain cherche une fiche, et le brain cherche encore quand la fiche cherchée manque au brain.",
    "brain-fiches": "Une fiche du brain se cherche par sa description ; le brain range chaque fiche et chaque fiche du brain se cherche ainsi.",
}
DISTRACTEURS = {
    "peinture-mur": "Peindre un mur demande une sous-couche et deux passes croisées.",
    "velo-chaine": "La chaîne du vélo se graisse après chaque sortie sous la pluie.",
    "pain-levain": "Le levain double de volume en quatre heures dans une pièce tiède.",
    "jardin-tomate": "Les tomates veulent du soleil, un tuteur et un arrosage au pied.",
    "guitare-accord": "Un accord barré exige un index bien à plat sur la première case.",
    "photo-lumiere": "La lumière rasante du matin sculpte les reliefs d'un paysage.",
    "cuisine-riz": "Le riz absorbe une fois et demie son volume d'eau à couvert.",
    "chien-rappel": "Le chiot apprend le retour au pied par le jeu, jamais par la contrainte.",
    "montagne-neige": "La neige de printemps devient lourde dès que le soleil tape.",
    "clavier-touche": "Une touche de clavier qui colle se nettoie à l'alcool isopropylique.",
    "livre-reliure": "La reliure cousue survit à des centaines d'ouvertures du livre.",
    "cafe-mouture": "Une mouture trop fine bouche le filtre et rend le café amer.",
    "bateau-noeud": "Le noeud de chaise se défait même après une forte traction.",
    "horloge-ressort": "Le ressort d'une horloge mécanique se remonte tous les huit jours.",
}


def brain_dessai():
    d = tempfile.mkdtemp(prefix="rappel-demande-")
    os.makedirs(os.path.join(d, "lessons"))
    os.makedirs(os.path.join(d, "state"))
    for nom, corps in {**FICHES, **DISTRACTEURS}.items():
        with open(os.path.join(d, "lessons", nom + ".md"), "w", encoding="utf-8") as f:
            f.write(f'---\nname: {nom}\ndescription: "{corps}"\n---\n\n{corps}\n')
    return d


def lancer(prompt, brain, hook=HOOK, env_sup=None):
    env = dict(os.environ, BRAIN_HOME=brain)
    env.pop("BRAIN_RECALL_AUTO", None)
    env.update(env_sup or {})
    p = subprocess.run([sys.executable, hook], input=json.dumps(
        {"prompt": prompt, "session_id": "TEST-DEMANDE"}), capture_output=True,
        text=True, env=env)
    return p.returncode, p.stdout


def bloc(sortie):
    return "<brain-recall>" in sortie


def lignes(brain, fichier):
    p = os.path.join(brain, "state", fichier)
    if not os.path.exists(p):
        return 0
    return sum(1 for _ in open(p, encoding="utf-8"))


def dernier(brain, fichier):
    """La DERNIÈRE ligne du journal — c'est elle que la passe qui vient de tourner a écrite."""
    p = os.path.join(brain, "state", fichier)
    if not os.path.exists(p):
        return {}
    lignes_ = [l for l in open(p, encoding="utf-8") if l.strip()]
    return json.loads(lignes_[-1]) if lignes_ else {}


def hook_sabote(remplacements):
    """Une COPIE du hook, amputée — l'original n'est jamais touché."""
    src = open(HOOK, encoding="utf-8").read()
    for avant, apres in remplacements:
        assert avant in src, f"sabotage impossible, motif absent : {avant!r}"
        src = src.replace(avant, apres, 1)
    d = tempfile.mkdtemp(prefix="hook-sabote-")
    # le hook importe brain_recall depuis SON dossier : on copie donc à côté des vrais
    faux = os.path.join(BRAIN, "hooks", "_inject_recall_sabote.py")
    open(faux, "w", encoding="utf-8").write(src)
    shutil.rmtree(d, ignore_errors=True)
    return faux


def main():
    echecs = []

    def verifie(nom, condition, detail=""):
        if condition:
            print(f"  ✅ {nom}")
        else:
            print(f"  ❌ {nom} {detail}")
            echecs.append(nom)

    brain = brain_dessai()
    try:
        # 1. Un message ordinaire, PARFAITEMENT pertinent, ne doit rien afficher.
        ordinaire = "le zorglub de cadrage a lâché en pleine mesure"
        rc, out = lancer(ordinaire, brain)
        verifie("message ordinaire → aucune injection", rc == 0 and not bloc(out), repr(out[:120]))

        # 2. L'instrument A8.8 continue de tourner malgré le silence — sinon la coupure
        #    éteindrait une mesure en cours sans que personne le voie.
        verifie("A8.8 alimenté même sans affichage", lignes(brain, "requete-forme.jsonl") == 1)

        # 2 bis. LE JOURNAL DOIT PORTER SA RÈGLE, PAS SEULEMENT SA MESURE.
        # Il enregistrait `s1` (meilleur score vu) et `injecte` (« au-dessus du seuil »)
        # sans jamais écrire QUEL seuil — alors qu'il y en a deux, 4.0 en automatique et
        # 1.0 sur demande explicite. Une ligne `injecte: false, s1: 2.5` était donc
        # illisible : personne ne pouvait dire si la barre était à 4.0 ou à 1.0. Un
        # chiffre sans sa règle ne se relit pas, il se devine.
        r = dernier(brain, "requete-forme.jsonl")
        verifie("…et la ligne dit à quelle barre elle s'est mesurée",
                r.get("seuil") is not None and r.get("demande") is False, repr(r)[:160])

        # 3. Rien n'est journalisé comme « proposé » si personne ne l'a vu : compter des
        #    propositions jamais montrées gonflerait le dénominateur du taux d'ouverture.
        verifie("recall_log vierge sans affichage", lignes(brain, "recall_log.jsonl") == 0)

        # ⚠️ Sans ce contrôle-ci, le n°1 serait vert dès que le moteur ne trouve rien —
        # c'est-à-dire pour la mauvaise raison. On exige donc la preuve que le moteur
        # AVAIT un candidat au-dessus du seuil, et s'est tu quand même. (C'est le
        # sabotage n°1, refusant de rougir, qui a fait apparaître ce trou.)
        _, auto = lancer(ordinaire, brain, env_sup={"BRAIN_RECALL_AUTO": "1"})
        verifie("…et il avait pourtant de quoi parler (le silence est un choix)",
                "zorglub-cadrage" in auto, repr(auto[:120]))

        # 4. Le marqueur explicite ouvre la porte.
        rc, out = lancer("?brain zorglub cadrage", brain)
        verifie("marqueur ?brain → injection", rc == 0 and bloc(out) and "zorglub" in out)

        # 4 bis. L'autre mode, l'autre barre. Si les deux modes écrivaient le même seuil,
        # le champ serait décoratif : c'est justement parce qu'il CHANGE qu'il fallait
        # l'écrire. On exige donc que les deux lignes ne disent pas la même chose.
        rd = dernier(brain, "requete-forme.jsonl")
        verifie("…et la demande explicite enregistre SA barre, plus basse",
                rd.get("demande") is True and rd.get("seuil") is not None
                and rd["seuil"] < r["seuil"], repr(rd)[:160])

        # 5. Une demande en français aussi — et elle ne doit pas se punir elle-même.
        rc, out = lancer("cherche dans le brain le zorglub de cadrage", brain)
        verifie("demande en français → injection", rc == 0 and "zorglub-cadrage" in out, repr(out[:160]))
        verifie("…et les mots de la question ne squattent pas la réponse",
                "brain-recherche" not in out and "brain-fiches" not in out, repr(out[:200]))

        # 6. Une demande sans réponse le DIT : le silence ne distingue pas
        #    « rien trouvé » de « mot-clé non reconnu ».
        rc, out = lancer("cherche dans le brain la recette du couscous royal", brain)
        verifie("demande sans résultat → le dit", rc == 0 and "Rien de pertinent" in out, repr(out[:160]))

        # 7. Marche arrière disponible sans toucher au code — et elle remet VRAIMENT
        #    l'ancien comportement, pas une version PLUS bavarde que lui.
        #    ⚠️ Jusqu'au 20/09 ce contrôle se contentait de « un bloc est apparu ». Il
        #    passait au vert avec les DEUX barres, il ne verrouillait donc rien — et il a
        #    laissé vivre six mois une promesse fausse : l'interrupteur rendait la parole
        #    au rappel, mais à la barre des demandes explicites (1.0) au lieu de la barre
        #    automatique (4.0), quatre fois plus indulgente que l'ancien comportement.
        #    On lit maintenant la barre que le hook a lui-même écrite dans son journal.
        verifie("les deux barres du hook n'ont pas dérivé",
                barres_declarees() == (BARRE_AUTO, BARRE_DEMANDE), repr(barres_declarees()))
        rc, out = lancer("le zorglub de cadrage a lâché en pleine mesure", brain,
                         env_sup={"BRAIN_RECALL_AUTO": "1"})
        r7 = dernier(brain, "requete-forme.jsonl")
        verifie("BRAIN_RECALL_AUTO=1 rend la parole au rappel", rc == 0 and bloc(out))
        verifie("…à la barre automatique, pas à celle des demandes explicites",
                bool(r7) and r7.get("seuil") == BARRE_AUTO and r7.get("demande") is False,
                repr(r7)[:170])

        # 7 bis. Et quand il ne trouve rien, l'interrupteur se TAIT. Le « rien trouvé »
        #    reste réservé à une vraie demande : sans cette réserve, CHAQUE message de la
        #    journée repartirait avec un bloc, exactement le bruit qui a fait couper le
        #    rappel automatique le 09/09.
        rc, out = lancer("xylophone quadrature nébuleuse tergiverse", brain,
                         env_sup={"BRAIN_RECALL_AUTO": "1"})
        verifie("…et sans résultat il se tait au lieu d'annoncer « rien trouvé »",
                rc == 0 and not bloc(out) and "Rien de pertinent" not in out,
                repr(out[:140]))

        # 8. Robustesse : jamais bloquant.
        for cas in ("ok", ""):
            rc, _ = lancer(cas, brain)
            verifie(f"exit 0 sur prompt trivial {cas!r}", rc == 0)

        # ── SABOTAGES ────────────────────────────────────────────────────────────
        # S1 — on retire la porte : le hook doit REDEVENIR bavard.
        faux = hook_sabote([("if results and afficher:", "if results:")])
        try:
            b2 = brain_dessai()
            _, out = lancer("le zorglub de cadrage a lâché en pleine mesure", b2, hook=faux)
            verifie("SABOTAGE 1 : sans la porte, le bavardage revient (donc le test mord)",
                    bloc(out), repr(out[:120]))
            shutil.rmtree(b2, ignore_errors=True)
        finally:
            os.remove(faux)

        # S2 — on retire le nettoyage de la requête ET le seuil abaissé : une demande
        # formulée en français doit REDEVENIR muette (défaut mesuré au premier essai :
        # score 3,195 avec les mots de politesse, 4,947 sans).
        faux = hook_sabote([
            ("requete = nettoyer(prompt) if demande else prompt", "requete = prompt"),
            ("seuil = MIN_SCORE_DEMANDE if demande else MIN_SCORE", "seuil = MIN_SCORE"),
        ])
        try:
            b3 = brain_dessai()
            _, out = lancer("cherche dans le brain le zorglub de cadrage", b3, hook=faux)
            # Les mots de la question (« cherche », « brain ») remontent leurs propres
            # fiches et chassent la vraie réponse du classement.
            verifie("SABOTAGE 2 : sans nettoyer(), les mots de la question polluent la réponse",
                    "brain-recherche" in out or "brain-fiches" in out, repr(out[:200]))
            shutil.rmtree(b3, ignore_errors=True)
        finally:
            os.remove(faux)

        # S3 — on retire la règle de la ligne et on ne garde que la mesure : le contrôle
        # 2 bis doit REDEVENIR aveugle. C'est l'état d'avant le 19/09, où 1 819 lignes
        # ont été écrites avec un `injecte` dont la barre n'était notée nulle part.
        # ⚠️ Le sabotage doit produire du code VALIDE : journaliser_forme est enveloppé
        # dans un `except: pass`, donc une erreur de syntaxe n'écrirait aucune ligne et
        # le contrôle rougirait pour la mauvaise raison — c'est arrivé au premier essai.
        faux = hook_sabote([('moteur=choix.get("moteur"),\n                     '
                            'seuil=seuil, demande=demande)',
                            'moteur=choix.get("moteur"))')])
        try:
            b4 = brain_dessai()
            lancer("le zorglub de cadrage a lâché en pleine mesure", b4, hook=faux)
            r4 = dernier(b4, "requete-forme.jsonl")
            verifie("SABOTAGE 3 : sans la règle, la ligne redevient illisible (donc le test mord)",
                    r4 and r4.get("seuil") is None, repr(r4)[:160])
            shutil.rmtree(b4, ignore_errors=True)
        finally:
            os.remove(faux)
        # S4 — on remet le raccourci corrigé le 20/09 : `demande_explicite()` répondait
        # « oui » à l'interrupteur automatique, donc l'interrupteur emportait AUSSI la
        # barre indulgente des demandes. C'est le vrai défaut, reproduit tel quel : le
        # journal doit redescendre à 1.0 sous `BRAIN_RECALL_AUTO=1`.
        faux = hook_sabote([('    p = _fold(prompt)\n    if _fold(MARQUEUR) in p:',
                             '    if os.environ.get("BRAIN_RECALL_AUTO") == "1":\n'
                             '        return True\n'
                             '    p = _fold(prompt)\n    if _fold(MARQUEUR) in p:')])
        try:
            b5 = brain_dessai()
            lancer("le zorglub de cadrage a lâché en pleine mesure", b5, hook=faux,
                   env_sup={"BRAIN_RECALL_AUTO": "1"})
            r5 = dernier(b5, "requete-forme.jsonl")
            verifie("SABOTAGE 4 : le raccourci rend l'interrupteur indulgent (donc le test mord)",
                    bool(r5) and r5.get("seuil") == BARRE_DEMANDE, repr(r5)[:160])
            shutil.rmtree(b5, ignore_errors=True)
        finally:
            os.remove(faux)
    finally:
        shutil.rmtree(brain, ignore_errors=True)

    print()
    if echecs:
        print(f"❌ {len(echecs)} contrôle(s) en échec : {', '.join(echecs)}")
        return 1
    print("✅ rappel à la demande : invariant tenu, et les quatre sabotages rougissent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
