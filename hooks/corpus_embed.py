#!/usr/bin/env python3
"""corpus_embed — embeddings + clustering of the COLD LAYER.

Pipeline (corpus_import → THIS SCRIPT → selective distillation):
  corpus/cold/**/*.md  →  model2vec embeddings  →  cosine KMeans  →  corpus/CLUSTERS.md (themes)

The SAME model as brain_embed.py → the cold corpus and the warm notes share the SAME
vector space (so a note can later be traced back to its source conversations). No dependency
beyond the venv (numpy + model2vec, NO sklearn): cosine KMeans reimplemented in numpy.

Outputs (all under corpus/, gitignored, local only):
  • state/corpus_embeddings.npz / .json  → vectors + metadata (rel, source, title), reusable
  • state/corpus_clusters.json           → assignation cluster par conversation
  • corpus/CLUSTERS.md                    → a READABLE report: per cluster = size, source mix, key terms, sample titles.

Usage (dans le venv ~/.c-brain/trunk/.venv) :
  corpus_embed.py [--k N] [--body-cap N]   # build : embeddings + clusters + rapport (k auto ≈ sqrt(n/2))
  corpus_embed.py query [-k N] "..."       # semantic search over the corpus (a channel separate from the notes)
"""
import os, re, sys, json, glob, argparse, datetime
import numpy as np
from model2vec import StaticModel

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
COLD = os.path.join(BRAIN, "corpus", "cold")
NPZ = os.path.join(BRAIN, "state", "corpus_embeddings.npz")
META = os.path.join(BRAIN, "state", "corpus_embeddings.json")
CLUST = os.path.join(BRAIN, "state", "corpus_clusters.json")
REPORT = os.path.join(BRAIN, "corpus", "CLUSTERS.md")
MODEL = "minishlab/potion-base-8M"          # IDENTICAL to brain_embed.py

# BILINGUAL by necessity: this list filters YOUR conversations, not this codebase.
# Keeping the French stop words is what stops "de", "que", "pour" from dominating
# every cluster of a French corpus. Add your own language here.
STOP = set("""au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me
même mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton
tu un une vos votre vous c d j l m n s t y est sont être ai as a avons avez ont fait faire plus moins
si comme tout tous cette ça cela donc alors aussi très peu bien encore the a an and are as at be by for
from has have i in is it its of on or that this to was were will with you your we my me he she they them
do does did not no yes can could would should will just like get got make made how what when where why
who which there here then than so up out about into over also their our""".split())
# Accented letters are part of the class on purpose: without them, "problème"
# would tokenize as "probl" + "me" and every French term would be shredded.
# i18n-ok: this class describes the USER's words, not this codebase.
WORD = re.compile(r"[a-zàâäéèêëïîôöùûüç]{3,}", re.I)


def parse_cold(fp):
    """→ (source, title, body_text). Strips front matter + role icons."""
    raw = open(fp, encoding="utf-8").read()
    source, title = "?", os.path.basename(fp)
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            fm, body = raw[3:end], raw[end + 4:]
            for line in fm.splitlines():
                if line.startswith("corpus_source:"):
                    source = line.split(":", 1)[1].strip()
                elif line.startswith("title:"):
                    try:
                        title = json.loads(line.split(":", 1)[1].strip())
                    except Exception:
                        title = line.split(":", 1)[1].strip().strip('"')
    body = re.sub(r"^#+ .*$", "", body, flags=re.M)          # markdown headings / roles
    body = re.sub(r"```.*?```", " ", body, flags=re.S)         # code blocks = thematic noise
    return source, title, body.strip()


def embed_text(title, body, cap):
    # title weighted ×3 (a strong thematic signal) + a bounded body excerpt (model2vec averages tokens)
    return ((title + ". ") * 3) + body[:cap]


def kmeans_cosine(X, k, iters=40, seed=0):
    """KMeans on L2-normalized vectors (cosine distance = euclidean). Pure numpy, deterministic."""
    rng = np.random.default_rng(seed)
    # init k-means++ (cosine)
    n = len(X)
    centers = [X[rng.integers(n)]]
    for _ in range(k - 1):
        d = 1 - (X @ np.array(centers).T).max(axis=1)         # distance au centre le + proche
        d = np.clip(d, 0, None); p = d / (d.sum() + 1e-12)
        centers.append(X[rng.choice(n, p=p)])
    C = np.array(centers)
    assign = np.zeros(n, dtype=int)
    for _ in range(iters):
        sim = X @ C.T
        new = sim.argmax(axis=1)
        if (new == assign).all():
            break
        assign = new
        for j in range(k):
            m = X[assign == j]
            if len(m):
                v = m.sum(axis=0); C[j] = v / (np.linalg.norm(v) + 1e-9)
    return assign, C


def top_terms(docs_tokens, idx, global_df, n_docs, topn=8):
    """Salient terms of a cluster: local frequency weighted by global rarity (light TF·IDF)."""
    from collections import Counter
    c = Counter()
    for i in idx:
        c.update(set(docs_tokens[i]))                          # presence per document (not raw counts)
    out = []
    for w, df_local in c.most_common(60):
        idf = np.log(n_docs / (1 + global_df.get(w, 1)))
        out.append((w, (df_local / len(idx)) * idf))
    out.sort(key=lambda x: -x[1])
    return [w for w, _ in out[:topn]]


def cmd_query(k, q):
    """Semantic search over the cold corpus — a channel SEPARATE from the notes (it does NOT pollute
    brain_recall: thousands of raw conversations would drown the curated notes)."""
    if not os.path.exists(NPZ):
        print("No index — run corpus_embed.py (build) first", file=sys.stderr); return
    meta = json.load(open(META, encoding="utf-8"))
    X = np.load(NPZ)["v"].astype(np.float64)
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    qv = np.asarray(StaticModel.from_pretrained(meta.get("model", MODEL)).encode([q]), dtype=np.float64)[0]
    qv = qv / (np.linalg.norm(qv) + 1e-9)
    sims = X @ qv
    for i in np.argsort(-sims)[:k]:
        print(f"  {sims[i]:.3f}  [{meta['sources'][i]:7}] {meta['titles'][i][:72]}")
        print(f"         {meta['rels'][i]}")


def build(a):
    files = sorted(glob.glob(os.path.join(COLD, "**", "*.md"), recursive=True))
    if not files:
        print("No cold conversation — run corpus_import.py first", file=sys.stderr); sys.exit(0)

    rels, sources, titles, texts, tokens = [], [], [], [], []
    from collections import Counter
    global_df = Counter()
    for fp in files:
        src, title, body = parse_cold(fp)
        rels.append(os.path.relpath(fp, BRAIN)); sources.append(src); titles.append(title)
        texts.append(embed_text(title, body, a.body_cap))
        tk = [w.lower() for w in WORD.findall(title + " " + body[:a.body_cap]) if w.lower() not in STOP]
        tokens.append(tk); global_df.update(set(tk))

    n = len(files)
    k = a.k or max(12, int((n / 2) ** 0.5))
    print(f"🧮 {n} conversations → embeddings (model {MODEL})…")
    model = StaticModel.from_pretrained(MODEL)
    X = np.asarray(model.encode(texts), dtype=np.float64)
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    print(f"🔗 KMeans cosinus k={k}…")
    assign, C = kmeans_cosine(X, k)

    # sorties machine
    os.makedirs(os.path.dirname(NPZ), exist_ok=True)
    np.savez_compressed(NPZ, v=X.astype(np.float32))
    json.dump({"model": MODEL, "rels": rels, "sources": sources, "titles": titles},
              open(META, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"k": k, "assign": assign.tolist(), "rels": rels},
              open(CLUST, "w", encoding="utf-8"), ensure_ascii=False)

    # readable report: clusters sorted by size
    order = sorted(range(k), key=lambda j: -(assign == j).sum())
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# 🗺️ Cold corpus — {k} thematic clusters",
         "",
         f"> {n} conversations ({sources.count('claude')} Claude · {sources.count('chatgpt')} ChatGPT) · "
         f"generated {now} · model {MODEL}.",
         "> The cold layer, lossless. Distillation into warm notes stays separate and selective.",
         ""]
    for rank, j in enumerate(order, 1):
        idx = [i for i in range(n) if assign[i] == j]
        if not idx:
            continue
        nc = sum(1 for i in idx if sources[i] == "claude")
        ng = sum(1 for i in idx if sources[i] == "chatgpt")
        terms = ", ".join(top_terms(tokens, idx, global_df, n))
        sim = X[idx] @ C[j]
        repr_idx = [idx[t] for t in np.argsort(-sim)[:3]]
        L.append(f"## {rank}. ({len(idx)} convs · {nc}C/{ng}G) — {terms}")
        for i in repr_idx:
            L.append(f"- {titles[i][:80]}  ·  *{sources[i]}*")
        L.append("")
    open(REPORT, "w", encoding="utf-8").write("\n".join(L))

    print(f"✅ {k} clusters · rapport → {os.path.relpath(REPORT, BRAIN)} · vecteurs → {os.path.relpath(NPZ, BRAIN)}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "query":
        a = sys.argv[2:]; k = 8
        if "-k" in a:
            i = a.index("-k"); k = int(a[i + 1]); del a[i:i + 2]
        cmd_query(k, " ".join(a)); return
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=0, help="nb clusters (0 = auto ≈ sqrt(n/2))")
    ap.add_argument("--body-cap", type=int, default=4000)
    build(ap.parse_args())


if __name__ == "__main__":
    main()
    sys.exit(0)
