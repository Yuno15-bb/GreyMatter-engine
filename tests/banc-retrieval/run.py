import sys, json, time, re, importlib.util, os, math
sys.path.insert(0,"hooks")
spec=importlib.util.spec_from_file_location("br","hooks/brain_recall.py")
br=importlib.util.module_from_spec(spec); sys.modules["br"]=br; spec.loader.exec_module(br)
CAS=json.load(open("tests/banc-retrieval/cas.json"))
base_tok = br.tokenize
RAW = br.load_corpus()          # tokens déjà calculés par le tokenizer courant

# --- V1 : desuffixation/deprefixation plus agressive
PREF=re.compile(r'^(des|de|re|ra)(?=[a-z]{5,})')
SUF=re.compile(r'(ements?|ations?|tions?|ages?|eurs?|euses?|ees?|es|s)$')
def tok_v1(txt):
    out=[]
    for t in base_tok(txt):
        t=PREF.sub('',t); t=SUF.sub('',t)
        if len(t)>2: out.append(t)
    return out
# --- V2 : alias etendus, construits sur 3 cibles SEULEMENT (3 autres = held-out)
VUES={"un-message-de-succes-explicite-peut-couvrir-un-mecanisme-en-echec","home-isole-n-est-pas-un-environnement-isole","glob-et-os-walk-ne-parcourent-pas-le-meme-arbre"}
AL2={r"\bcode de retour\b":"exit","\\bcode de sortie\\b":"exit","\\bnul\\b":"zero",
     r"\bbac a sable\b":"sandbox","\\bmachine hote\\b":"hote","\\bbinaires?\\b":"binaire",
     r"\blister\b":"parcour", r"\btotaux?\b":"compte", r"\bdossiers? caches?\b":"cache"}
def tok_v2(txt):
    t=txt.lower()
    for pat,rep in AL2.items(): t=re.sub(pat,rep,t)
    return base_tok(t)

def build(tokfn):
    docs=[]
    for d in RAW:
        d2=dict(d)
        if tokfn is not base_tok: d2["tokens"]=tokfn(" ".join(d["tokens"]))
        docs.append(d2)
    return br.BM25(docs)

def evaluate(idx, tokfn, label):
    t0=time.time(); lignes=[]
    for c in CAS:
        res=idx.classer(c["q"] if tokfn is base_tok else " ".join(tokfn(c["q"])), k=40)
        noms=[r["doc"]["name"] for r in res]
        cibles=c["t"] if isinstance(c["t"],list) else ([c["t"]] if c["t"] else [])
        rangs=[(noms.index(t)+1 if t in noms else None) for t in cibles]
        top1=res[0]["score"] if res else 0
        lignes.append({"c":c["c"],"t":cibles,"rangs":rangs,"top1":round(top1,2),"top1_nom":noms[0] if noms else None,
                       "cible_top":cibles[0] if cibles else None})
    return lignes, round((time.time()-t0)*1000/len(CAS),1)

def agg(l):
    p=[x for x in l if x["t"]]
    r3=sum(1 for x in p if any(r and r<=3 for r in x["rangs"]))
    r5=sum(1 for x in p if any(r and r<=5 for r in x["rangs"]))
    mrr=sum(1/min([r for r in x["rangs"] if r] or [99]) for x in p)/max(len(p),1)
    c7=[x for x in p if x["c"].startswith("C7")]
    c7ok=sum(1 for x in c7 if all(r and r<=5 for r in x["rangs"]))
    return r3,r5,round(mrr,3),len(p),c7ok,len(c7)

print(f"{'variante':<26}{'R@3':>7}{'R@5':>7}{'MRR':>8}{'C7 2/2':>9}{'ms/req':>9}")
print("-"*68)
resultats={}
for lab,tokfn in [("V0 moteur actuel",base_tok),("V1 desuffixation +",tok_v1),("V2 alias etendus",tok_v2)]:
    idx=build(tokfn); l,ms=evaluate(idx,tokfn,lab); resultats[lab]=l
    r3,r5,mrr,n,c7ok,c7n=agg(l)
    print(f"{lab:<26}{f'{r3}/{n}':>7}{f'{r5}/{n}':>7}{mrr:>8}{f'{c7ok}/{c7n}':>9}{ms:>9}")
json.dump(resultats, open("tests/banc-retrieval/resultats.json","w"), ensure_ascii=False)
