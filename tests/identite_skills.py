#!/usr/bin/env python3
"""
identite_skills.py — un fichier physique `SKILL.md` sous une identité logique `<slug>`.

LA DÉCISION QU'IL VERROUILLE (l'auteur, 2026-08-27) : la contrainte externe fait autorité sur
la forme physique. Claude Code exige `skills/<slug>/SKILL.md` ; le Brain ne renomme pas ce
fichier pour satisfaire son propre indexeur — c'est l'indexeur qui apprend.

CE QUE CE BANC EMPÊCHE DE REVENIR. Le 2026-08-25 puis le 2026-08-26, un agent a renommé les
24 `SKILL.md` en `<slug>.md`. Deux fois. Ce n'était pas une maladresse : il avait ajouté
`skills` à `LINKED_DIRS`, et le doctor exigeait alors `name == basename`, plus
`[a-z0-9-]+` — deux règles que `SKILL.md` ne peut pas satisfaire. Renommer était le SEUL
moyen de le taire. Tant que la règle spéciale n'existait pas, la casse était structurelle.

  python3 tests/identite_skills.py
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(ICI)
sys.path.insert(0, os.path.join(BRAIN, "hooks"))
from identite_fiche import identite, scanner, chemin_canonique  # noqa: E402

fails = []
def ok(m): print("  ✅ %s" % m)
def ko(m): print("  ❌ %s" % m); fails.append(m)


def scene(fichiers):
    """Dépôt jetable : {chemin relatif: contenu}."""
    d = tempfile.mkdtemp(prefix="ident-skills-")
    if not os.path.realpath(d).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
        raise RuntimeError("isolation")
    for rel, txt in fichiers.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(txt)
    return d


FM = "---\nname: %s\ndescription: d\n---\n\n# %s\n"


# ── 1 ───────────────────────────────────────────────────────────────────────
def cas_1():
    print("\n1. SKILL.md SEUL → indexé sous le slug du DOSSIER")
    d = scene({"skills/design/SKILL.md": FM % ("design", "design")})
    try:
        idx, conf, _ = scanner(d, ["skills"])
        if idx == {"design": "skills/design/SKILL.md"}:
            ok("identité « design » → %s" % idx["design"])
        else:
            ko("index inattendu : %s" % idx)
        ok("aucun conflit") if not conf else ko("conflit inattendu : %s" % conf)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 2 ───────────────────────────────────────────────────────────────────────
def cas_2():
    print("\n2. <slug>.md SEUL → NON canonique, signalé, jamais indexé en silence")
    d = scene({"skills/design/design.md": FM % ("design", "design")})
    try:
        idx, conf, _ = scanner(d, ["skills"])
        if idx == {}:
            ok("rien d'indexé — la forme non canonique ne devient pas la référence")
        else:
            ko("indexé alors qu'il n'est pas canonique : %s" % idx)
        if conf and "aucun canonique" in conf[0][3]:
            ok("signalé explicitement : « %s »" % conf[0][3])
        else:
            ko("silence sur une fiche non canonique : %s" % conf)
        slug, canonique, motif = identite("skills/design/design.md")
        if slug == "design" and not canonique:
            ok("l'identité est reconnue (« %s ») mais la représentation est refusée" % slug)
        else:
            ko("identité mal jugée : %s %s %s" % (slug, canonique, motif))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 3 ───────────────────────────────────────────────────────────────────────
def cas_3():
    print("\n3. SKILL.md + <slug>.md → DOUBLON détecté, une seule identité")
    d = scene({"skills/design/SKILL.md": FM % ("design", "design"),
               "skills/design/design.md": FM % ("design", "design")})
    try:
        idx, conf, _ = scanner(d, ["skills"])
        if list(idx) == ["design"] and idx["design"] == "skills/design/SKILL.md":
            ok("une seule identité, et c'est le canonique qui gagne")
        else:
            ko("index : %s" % idx)
        if len(conf) == 1 and conf[0][2] == "skills/design/design.md":
            ok("le concurrent est nommé : %s" % conf[0][3])
        else:
            ko("doublon non détecté : %s" % conf)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── 4 ───────────────────────────────────────────────────────────────────────
def cas_4():
    # ⚠️ Ce cas attendait le nombre 24, écrit en dur le 2026-08-27. Un compte gelé ment
    # au premier skill ajouté — c'est le défaut de A7 (une carte qui annonce « les 20
    # familles » quel que soit le tronc), déplacé dans un banc. L'invariant VRAI n'est
    # pas « 24 » : c'est « une identité par SKILL.md, jamais deux ». Il se mesure sur le
    # disque et vaut sur n'importe quel tronc.
    attendus = sorted(os.path.basename(os.path.dirname(p))
                      for p in glob.glob(os.path.join(BRAIN, "skills", "*", "SKILL.md")))
    print("\n4. LES %d SKILLS RÉELS → %d identités, pas %d"
          % (len(attendus), len(attendus), 2 * len(attendus)))
    idx, conf, ign = scanner(BRAIN, ["skills"])
    if sorted(idx) == attendus:
        ok("%d identités logiques, une par SKILL.md posé à la racine de son dossier"
           % len(idx))
    else:
        manque = [x for x in attendus if x not in idx]
        en_trop = [x for x in idx if x not in attendus]
        ko("%d identités au lieu de %d — manquantes %s, en trop %s"
           % (len(idx), len(attendus), manque, en_trop))
    if all(p.endswith("/SKILL.md") for p in idx.values()):
        ok("toutes pointent vers un SKILL.md canonique")
    else:
        ko("certains pointent ailleurs : %s"
           % [p for p in idx.values() if not p.endswith("/SKILL.md")])
    conteneurs = [m for _, m in ign if "conteneur" in (m or "")]
    print("     (%d fichier(s) écartés parce qu'ils vivent SOUS un conteneur,"
          " pas dans un skill)" % len(conteneurs))
    doublons = [c for c in conf if c[2].endswith("/" + c[0] + ".md")]
    print("     (%d doublon(s) <slug>.md présents et signalés, non supprimés ici)"
          % len(doublons))
    if any("outillage" in m for _, m in ign):
        ok("les .venv / node_modules sont élagués, pas indexés")
    else:
        print("     (aucun dossier d'outillage rencontré)")


# ── 5 ───────────────────────────────────────────────────────────────────────
def cas_5():
    print("\n5. AUCUN SKILL.md RENOMMÉ → Claude Code peut toujours charger")
    manquants, sans_fm, conteneurs = [], [], []
    for d in sorted(os.listdir(os.path.join(BRAIN, "skills"))):
        dossier = os.path.join(BRAIN, "skills", d)
        if not os.path.isdir(dossier) or d.startswith("_"):
            continue
        p = os.path.join(dossier, "SKILL.md")
        if not os.path.exists(p):
            # Un dossier sans SKILL.md qui en contient PLUS BAS n'est pas un skill
            # amputé : c'est un CONTENEUR — le miroir `synced/` en est un, avec ses
            # 57 skills rangés sous un identifiant de compte. Le confondre avec un skill
            # cassé faisait rougir ce banc pour une raison fausse.
            if glob.glob(os.path.join(dossier, "*", "*", "SKILL.md")):
                conteneurs.append(d)
            else:
                manquants.append(d)
            continue
        txt = open(p, encoding="utf-8").read(400)
        if not txt.startswith("---") or "name:" not in txt or "description:" not in txt:
            sans_fm.append(d)
    total = len(manquants) + len(sans_fm) + len([1 for d in sorted(os.listdir(
        os.path.join(BRAIN, "skills"))) if os.path.isdir(os.path.join(BRAIN, "skills", d))
        and not d.startswith("_") and os.path.exists(
            os.path.join(BRAIN, "skills", d, "SKILL.md"))])
    if not manquants:
        ok("%d dossiers sur %d portent leur SKILL.md — le nom exigé par Claude Code"
           % (total - len(manquants), total))
    else:
        ko("SKILL.md manquant pour : %s" % manquants)
    if conteneurs:
        print("     (%d conteneur(s) mis de côté, ce ne sont pas des skills : %s)"
              % (len(conteneurs), ", ".join(conteneurs)))
    if not sans_fm:
        ok("toutes portent name + description dans leur frontmatter")
    else:
        ko("frontmatter incomplet : %s" % sans_fm)
    if chemin_canonique("skills", "design") == "skills/design/SKILL.md":
        ok("la règle inverse tient : chemin_canonique('skills','design') = %s"
           % chemin_canonique("skills", "design"))
    else:
        ko("chemin_canonique faux : %s" % chemin_canonique("skills", "design"))


# ── 6 ───────────────────────────────────────────────────────────────────────
def cas_6():
    print("\n6. [[design]] RÉSOUT vers skills/design/SKILL.md")
    idx, _, _ = scanner(BRAIN, ["projects", "lessons", "life", "meta", "skills"])
    for lien in ("design", "ship", "skill-forge", "a11y"):
        cible = idx.get(lien)
        if cible == "skills/%s/SKILL.md" % lien:
            ok("[[%s]] → %s" % (lien, cible))
        else:
            ko("[[%s]] résout vers %s" % (lien, cible))
    # et le résolveur de la CARTE, qui est un autre consommateur
    sys.path.insert(0, os.path.join(BRAIN, "tools", "cartes"))
    try:
        import reconcilier
        fiches = reconcilier.index_fiches(BRAIN)
        if fiches.get("design", "").endswith("skills/design/SKILL.md"):
            ok("le réconciliateur de la carte résout aussi [[design]]")
        else:
            ko("la carte ne résout pas [[design]] : %s" % fiches.get("design"))
    except Exception as e:
        ko("réconciliateur : %s" % e)


# ── 7 ───────────────────────────────────────────────────────────────────────
def cas_7():
    print("\n7. DOCTOR — aucun faux vert dû à LINKED_DIRS")
    import brain_doctor
    if "skills" in brain_doctor.LINKED_DIRS:
        ok("skills est bien dans LINKED_DIRS (donc réellement contrôlé)")
    else:
        ko("skills hors LINKED_DIRS — il ne serait pas contrôlé du tout")
    # SABOTAGE : un skill au frontmatter cassé doit faire rougir le doctor. Sans ce
    # contraste, « skills dans LINKED_DIRS » serait une déclaration sans effet.
    victime = os.path.join(BRAIN, "skills", "a11y", "SKILL.md")
    origine = open(victime, encoding="utf-8").read()
    try:
        open(victime, "w", encoding="utf-8").write(
            origine.replace("name: a11y", "name: PAS-LE-BON-SLUG", 1))
        r = subprocess.run([sys.executable, os.path.join(BRAIN, "hooks", "brain_doctor.py")],
                           capture_output=True, text=True, timeout=180)
        # ⚠️ La première version acceptait « ou "a11y" apparaît quelque part ». Or
        # `a11y` figure DÉJÀ dans la liste des doublons : l'assertion serait passée
        # même sans aucune détection. On exige la ligne exacte.
        attendu = "skills/a11y/SKILL.md : name='PAS-LE-BON-SLUG' ≠ identité 'a11y'"
        if attendu in r.stdout:
            ok("sabotage détecté, au bon endroit : « %s »" % attendu)
        else:
            ko("SABOTAGE INVISIBLE — le doctor ne contrôle pas réellement les skills")
    finally:
        open(victime, "w", encoding="utf-8").write(origine)
    r = subprocess.run([sys.executable, os.path.join(BRAIN, "hooks", "brain_doctor.py")],
                       capture_output=True, text=True, timeout=180)
    if "PAS-LE-BON-SLUG" not in r.stdout:
        ok("le fichier saboté est restauré, le doctor ne le signale plus")
    else:
        ko("restauration ratée — le tronc reste saboté")


def main():
    print("=" * 78)
    print("IDENTITÉ DES SKILLS — SKILL.md physique, <slug> logique")
    print("=" * 78)
    for f in (cas_1, cas_2, cas_3, cas_4, cas_5, cas_6, cas_7):
        try:
            f()
        except Exception as e:
            ko("%s a levé : %s" % (f.__name__, e))
    print("\n" + "-" * 78)
    if fails:
        print("ROUGE — %d échec(s) :" % len(fails))
        for f in fails:
            print("   · %s" % f)
        return 1
    print("VERT — un SKILL.md physique s'indexe sous son identité logique.")
    print("  Les doublons <slug>.md sont DÉTECTÉS, pas supprimés : c'est une décision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
