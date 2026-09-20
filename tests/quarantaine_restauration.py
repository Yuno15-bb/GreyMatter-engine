"""Contre-épreuve de la quarantaine — elle doit rendre à l'identique, et refuser sinon.

Tourne sur un tronc de fixtures jetable. AUCUNE fiche réelle n'est touchée.

Le parcours normal doit passer entièrement ; les quatre sabotages doivent chacun produire
un refus ou un rouge. Un mécanisme de non-perte qui ne sait pas refuser ne protège de rien.
"""
import os
import shutil
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "tools", "nettoyage"))
import quarantaine as Q  # noqa: E402

FICHE = """---
name: fiche-de-test-jetable
title: "Fiche de test jetable"
---

# Fiche de test jetable

Contenu unique qui doit revenir octet pour octet : é à ü — 42.
"""


def tronc():
    d = tempfile.mkdtemp(prefix="r3quar-")
    p = os.path.join(d, "lessons", "fiche-de-test-jetable.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(FICHE)
    return d, "lessons/fiche-de-test-jetable.md"


def main():
    echecs = []

    # ── 1. PARCOURS NORMAL, les six étapes demandées
    d, rel = tronc()
    try:
        src = os.path.join(d, rel)
        avant = Q.sha(open(src, "rb").read())
        q = Q.Quarantaine(d)

        print("PARCOURS NORMAL")
        print("   1. la fiche existe ................................. %s"
              % ("✅" if os.path.exists(src) else "❌"))
        e, msg = q.mettre(rel, "fixture de qualification", "banc automatique")
        print("   2. mise en quarantaine ............................. %s  (%s)"
              % ("✅" if e else "❌", msg))
        partie = not os.path.exists(src)
        print("   3. elle a quitté le corpus actif ................... %s" % ("✅" if partie else "❌"))
        garde = os.path.exists(os.path.join(d, e["fichier_quarantaine"])) and e["sha256"] == avant
        print("   4. contenu et empreinte conservés .................. %s  (%s)"
              % ("✅" if garde else "❌", e["sha256"][:12]))
        ok, msg = q.restaurer(e["id"])
        print("   5. restauration .................................... %s  (%s)"
              % ("✅" if ok else "❌", msg))
        apres = Q.sha(open(src, "rb").read()) if os.path.exists(src) else None
        identique = apres == avant
        print("   6. revenue au même endroit, octet pour octet ....... %s" % ("✅" if identique else "❌"))
        if not all((e, partie, garde, ok, identique)):
            echecs.append("parcours normal")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # ── 2. SABOTAGES
    print("\nSABOTAGES — chacun doit refuser ou rougir")

    def sabotage(nom, prepare, attendu):
        d, rel = tronc()
        try:
            q = Q.Quarantaine(d)
            e, _ = q.mettre(rel, "fixture", "banc")
            restaure = prepare(d, q, e)
            ok, msg = (restaure if restaure is not None else q.restaurer(e["id"]))
            refuse = not ok and attendu in msg
            # NON-PERTE : quel que soit le refus, la sauvegarde doit survivre et aucun
            # fichier abîmé ne doit rester à la place de la fiche.
            sauve = os.path.exists(os.path.join(d, e["fichier_quarantaine"])) \
                or "sauvegarde absente" in msg
            propre = not os.path.exists(os.path.join(d, rel))
            print("   %s %-42s %s" % ("✅" if (refuse and sauve and propre) else "❌",
                                      nom, msg[:64]))
            if not refuse:
                echecs.append(nom)
            elif not sauve:
                echecs.append(nom + " (sauvegarde perdue)")
            elif not propre:
                echecs.append(nom + " (fichier abîmé laissé en place)")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def sha_faux(d, q, e):
        p = os.path.join(d, e["fichier_quarantaine"])
        open(p, "ab").write(b"octet en trop")
        return None

    def sauvegarde_absente(d, q, e):
        os.remove(os.path.join(d, e["fichier_quarantaine"]))
        return None

    def manifeste_incomplet(d, q, e):
        m = q._charger()
        m["entrees"][0].pop("sha256")
        q._sauver(m)
        return None

    def restauration_differente(d, q, e):
        vrai = Q._ecrire
        Q._ecrire = lambda c, o: vrai(c, o + b"\n# ligne parasite\n")
        try:
            return q.restaurer(e["id"])
        finally:
            Q._ecrire = vrai

    sabotage("empreinte de sauvegarde faussée", sha_faux, "REFUS : empreinte")
    sabotage("sauvegarde effacée", sauvegarde_absente, "REFUS : sauvegarde absente")
    sabotage("manifeste amputé d'un champ", manifeste_incomplet, "REFUS : manifeste incomplet")
    sabotage("écriture altérée à la restauration", restauration_differente, "ROUGE")

    print()
    if echecs:
        print("❌ %d échec(s) : %s" % (len(echecs), ", ".join(echecs)))
        return 1
    print("✅ la quarantaine rend à l'identique, et refuse dans les quatre cas d'atteinte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
