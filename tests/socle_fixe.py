#!/usr/bin/env python3
"""Banc du SOCLE FIXE — le bloc de règles relu à CHAQUE échange ne doit pas regrossir.

Pourquoi ce banc existe
-----------------------
Le 2026-09-14, la mesure de consommation a montré que le contexte relu à chaque appel pèse
66 000 jetons AVANT le premier mot de l'auteur, et que **66 % de la dépense d'une session est
cette relecture**. Le levier P4 du chantier sobriété — alléger ce socle — est resté sans
réponse cinq jours, pendant lesquels `~/.claude/CLAUDE.md` est passé de 30 à 39 Ko : il a
GROSSI au lieu de maigrir. C'est ce mouvement-là que ce banc arrête.

Ce qu'il vérifie, et pourquoi ce sont ces deux choses
-----------------------------------------------------
1. **Le budget d'octets.** Une taille qui n'est pas mesurée dérive toujours vers le haut,
   parce que chaque ajout pris isolément est raisonnable. Le seuil est daté et argumenté.

2. **Chaque règle globale pointe une fiche qui existe.** C'est l'invariant qui compte
   vraiment, et il est structurel plutôt que cosmétique : une règle grossit dans le socle
   exactement quand elle n'a **nulle part d'autre où aller**. Tant que chaque bloc a une
   fiche vivante derrière lui, « on déplace la nuance, on ne la supprime jamais » reste
   applicable ; sans fiche, couper signifierait détruire, et le banc n°1 pousserait à
   détruire. Les deux contrôles ne valent donc QUE pris ensemble.

Ce qu'il ne prouve PAS (honnêteté d'instrument)
------------------------------------------------
Il compte des octets et vérifie des chemins. Il ne lit pas les fiches et ne peut donc pas
dire qu'une nuance retirée du socle est bien ARRIVÉE dans sa fiche — ça, c'est un jugement,
il se fait à la main au moment de la coupe (contrôle de couverture du 2026-09-19 : 194
passages en gras de l'ancien socle, 194 encore atteignables). Il ne mesure pas non plus des
jetons : l'octet est une PROXY du jeton, fidèle pour du texte français, fausse pour du code
ou des emoji.
"""
import os
import re
import sys

SOCLE = os.path.expanduser("~/.claude/CLAUDE.md")
BRAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Seuil posé le 2026-09-19, après la taille de P4 : le socle passe de 39 310 à ~24 300
# octets, sans perdre une règle (les diagnostics partent dans les fiches déjà pointées).
# 26 000 laisse environ 1,7 Ko — la place d'UN contrat de règle neuve, pas d'un récit.
# Le dépassement n'est pas une erreur en soi : c'est le signal qu'il faut déplacer un
# diagnostic vers sa fiche, ou assumer le coût et remonter le seuil en l'écrivant ici.
BUDGET_OCTETS = 26_000

# TOUT bloc de premier niveau est concerné, pas seulement ceux marqués « RÈGLE GLOBALE ».
# Le contrôle ne portait d'abord que sur ce marqueur, et il ratait le plus gros bloc du
# socle — celui du style de réponse, 12 079 octets à lui seul, soit 31 % du total, qui ne
# porte aucun marqueur. Un capteur qui laisse passer sa plus grosse cible ne mesure rien.
POINTEUR = re.compile(r"`((?:meta|lessons)/[a-z0-9/-]+\.md)`")


def blocs(texte):
    """Découpe le socle en (titre, corps) sur les titres de premier niveau."""
    coupes = [m.start() for m in re.finditer(r"^# ", texte, re.M)] + [len(texte)]
    for i in range(len(coupes) - 1):
        bloc = texte[coupes[i]:coupes[i + 1]]
        yield bloc.split("\n", 1)[0][2:].strip(), bloc


def main():
    if not os.path.exists(SOCLE):
        print(f"⏭️  socle absent ({SOCLE}) — banc sauté, cette machine n'a pas de socle global")
        return 0

    # ─── LE SOCLE DOIT VIVRE DANS LE DÉPÔT, PAS À CÔTÉ ───
    # Mesuré le 2026-09-19 : ce fichier, relu intégralement à CHAQUE échange, n'était
    # versionné nulle part. `~/.claude` n'est pas un dépôt, et le Brain n'en avait aucune
    # copie — un disque perdu et toutes les règles partaient avec, y compris celles qu'une
    # mesure avait coûté des jours à établir. Il vit maintenant dans le Brain, et
    # `~/.claude/CLAUDE.md` est un lien vers lui, comme `~/.claude/agents` et
    # `~/.claude/skills` depuis août.
    #
    # POURQUOI CE CONTRÔLE, ET PAS SEULEMENT LE DÉPLACEMENT. Un lien peut être défait sans
    # bruit : une restauration de sauvegarde, un éditeur qui réécrit au lieu de modifier,
    # une machine neuve où l'installeur repose un vrai fichier. Le socle redeviendrait
    # alors un fichier ordinaire, hors dépôt, et la copie du Brain vieillirait en silence
    # en donnant l'illusion d'être sauvegardée. C'est exactement le défaut mesuré le 15/09
    # sur les hooks : installés une fois, jamais réinstallés, et verts pour rien.
    attendu = os.path.join(BRAIN, "tools", "socle", "CLAUDE.md")
    if not os.path.islink(SOCLE) or os.path.realpath(SOCLE) != os.path.realpath(attendu):
        print(f"⛔ {SOCLE} n'est pas un lien vers {attendu}")
        print("   Le socle est relu à chaque échange et n'existerait alors dans aucun dépôt.")
        print(f"   Répare :  cp {SOCLE} {attendu} && rm {SOCLE} && ln -s {attendu} {SOCLE}")
        return 1

    texte = open(SOCLE, encoding="utf-8").read()
    taille = len(texte.encode("utf-8"))

    sans_fiche, fiches_mortes = [], []
    gouvernants = 0
    for titre, bloc in blocs(texte):
        gouvernants += 1
        cibles = POINTEUR.findall(bloc)
        if not cibles:
            sans_fiche.append(titre)
            continue
        for c in cibles:
            if not os.path.exists(os.path.join(BRAIN, c)):
                fiches_mortes.append((titre, c))

    if taille > BUDGET_OCTETS:
        print(f"⛔ le socle a regrossi : {taille} octets pour un budget de {BUDGET_OCTETS}. "
              f"Il est relu à CHAQUE échange — déplace un diagnostic vers sa fiche, "
              f"ou remonte le seuil en écrivant pourquoi dans ce fichier.")
        return 1

    if sans_fiche:
        print("⛔ bloc de règles sans fiche derrière lui — la nuance n'aurait nulle part "
              "où être déplacée, donc la couper reviendrait à la détruire :")
        for t in sans_fiche:
            print(f"     · {t}")
        return 1

    if fiches_mortes:
        print("⛔ le socle pointe une fiche qui n'existe pas — le détail est injoignable :")
        for t, c in fiches_mortes:
            print(f"     · {t} → {c}")
        return 1

    print(f"✅ socle fixe tenu — {taille} octets sur {BUDGET_OCTETS}, "
          f"{gouvernants} blocs de règles, chacune adossée à une fiche vivante")
    return 0


if __name__ == "__main__":
    sys.exit(main())
