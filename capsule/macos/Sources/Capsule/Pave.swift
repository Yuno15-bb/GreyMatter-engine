// THE CODE BLOCK that scrolls inside the panel's large orb: a port of `orbe.html?ilot`
// (#pave, lireFlux, lignesAgent, tournerPave) and of the theme from `ilot.js` (themeEnCours).
// Terminal green, 18 slots, shadow rather than outline, fallback on the agent's own file.
import AppKit

let FLUX = (NSHomeDirectory() as NSString).appendingPathComponent(".claude/companion/sessions")
/// The trunk: `CAPSULE_BRAIN` (set by hooks/auto_maintain.py and install.sh, which know the trunk), otherwise
/// the folder holding `capsule/` found by walking up from the executable, otherwise ~/.greymatter/trunk.
/// `CAPSULE_STATUT_HOME` (benches) comes first. Without this, an install whose trunk lives elsewhere
/// read a status that does not exist.
let TRONC: String = {
    let env = ProcessInfo.processInfo.environment, fm = FileManager.default
    if let h = env["CAPSULE_STATUT_HOME"] { return (h as NSString).appendingPathComponent("claude-brain") }
    if let b = env["CAPSULE_BRAIN"], !b.isEmpty { return b }
    var u = Bundle.main.executableURL?.resolvingSymlinksInPath().deletingLastPathComponent()
    while let d = u, d.path != "/" {
        let parent = d.deletingLastPathComponent()
        if d.lastPathComponent == "capsule", fm.fileExists(atPath: parent.appendingPathComponent("state").path) { return parent.path }
        u = parent
    }
    return (NSHomeDirectory() as NSString).appendingPathComponent(".greymatter/trunk")
}()
private let LARGEUR = 19, GARDE = 90, FENTES = 18
private let RAYON_TXT: CGFloat = 37

struct LigneCode: Hashable { let t: String; let c: String }

/// The companion `.jsonl` written most recently; `nil` if it has not moved for 180 s
/// (unless `sansAge`). The most recently WRITTEN one wins: only the working session matters.
func fichierActif(sansAge: Bool = false) -> (chemin: String, date: Date)? {
    guard let noms = try? FileManager.default.contentsOfDirectory(atPath: FLUX) else { return nil }
    var best: (String, Date)?
    for n in noms where n.hasSuffix(".jsonl") {
        let p = (FLUX as NSString).appendingPathComponent(n)
        if let d = (try? FileManager.default.attributesOfItem(atPath: p))?[.modificationDate] as? Date,
           best == nil || d > best!.1 { best = (p, d) }
    }
    guard let b = best, sansAge || Date().timeIntervalSince(b.1) < 180 else { return nil }
    return b
}

/// The last `n` bytes of a file, as lines.
private func finDeFichier(_ p: String, octets: Int) -> [Substring] {
    guard let h = FileHandle(forReadingAtPath: p) else { return [] }
    defer { try? h.close() }
    let taille = (try? h.seekToEnd()) ?? 0
    try? h.seek(toOffset: taille > UInt64(octets) ? taille - UInt64(octets) : 0)
    let d = (try? h.readToEnd()) ?? Data()
    return String(decoding: d, as: UTF8.self).split(separator: "\n", omittingEmptySubsequences: false)
}

// ── THE THEME (ilot.js themeEnCours): the project of the last file written ───
private var themeVu = (f: "", t: Date.distantPast, theme: "")
func themeEnCours() -> String {
    guard let (f, t) = fichierActif(sansAge: true) else { return "" }
    if f == themeVu.f && t == themeVu.t { return themeVu.theme }
    var theme = ""
    for l in finDeFichier(f, octets: 65536).reversed() {
        guard let j = try? JSONSerialization.jsonObject(with: Data(l.utf8)) as? [String: Any],
              j["type"] as? String == "diff", let p = j["project"] as? String, !p.isEmpty else { continue }
        theme = p.replacingOccurrences(of: "[-_]+", with: " ", options: .regularExpression); break
    }
    themeVu = (f, t, theme)
    return theme
}

private func classe(_ l: String) -> String {
    if l.hasPrefix("@@") { return "tete" }
    if l.hasPrefix("+") { return "plus" }
    if l.hasPrefix("-") { return "moins" }
    return ""
}

// ── THE FALLBACK: the file THIS agent runs (SOURCE_AGENT) ─────────────────────
private let SOURCE_AGENT = [
    "distilling": "agents/narcissus.md", "gardening": "agents/narcissus.md",
    "filing": "agents/narcissus.md", "correcting": "agents/narcissus.md",
    "mapping": "agents/narcissus.md", "architecting": "agents/sulaco.md",
    "challenging": "agents/sulaco.md", "archiving": "agents/sulaco.md",
    "synthesizing": "agents/anesidora.md", "auditing": "hooks/brain_upkeep.py",
    "committing": "hooks/auto_maintain.py", "working": "hooks/auto_maintain.py"]
private var cacheAgent: [String: [LigneCode]] = [:]
private func lignesAgent(_ etat: String) -> [LigneCode] {
    guard let rel = SOURCE_AGENT[etat] else { return [] }
    if let c = cacheAgent[rel] { return c }
    let brut = (try? String(contentsOfFile: (TRONC as NSString).appendingPathComponent(rel), encoding: .utf8)) ?? ""
    let l = brut.components(separatedBy: "\n")
        .map { $0.replacingOccurrences(of: "\t", with: "  ").trimmingCharacters(in: .whitespaces) }
        .filter { $0.count > 2 && $0.range(of: "^[-`#*_|>=:\\s]+$", options: .regularExpression) == nil }
        .prefix(400).map { LigneCode(t: String($0.prefix(LARGEUR)), c: "") }
    cacheAgent[rel] = Array(l)
    return cacheAgent[rel]!
}

// ── FILMING: a fixed, neutral sample (PAVE_TOURNAGE) ──────────────────────────
private let PAVE_TOURNAGE = [
    "synthesizing": """
── notes/digest.ts
+ export async function weeklyDigest(notes) {
+   const themes = groupBy(notes, n => n.topic);
+   for (const [topic, items] of themes) {
+     const links = items.flatMap(n => n.links);
+     if (links.length < 2) continue;
+     digest.push({ topic, summary: merge(items) });
+   }
-   return notes.map(n => n.title);
+   return rank(digest, { by: 'reuse' });
+ }
  const merge = items => items
    .map(n => n.lesson)
    .filter(Boolean)
    .join('\\n');
+ // cross-project patterns only
+ const rank = (xs, o) => xs.sort(score(o));
""",
    "autre": """
── src/index/graph.ts
+ export function mapLayout(nodes, edges) {
+   const seen = new Set();
+   for (const e of edges) {
+     if (!seen.has(e.from)) place(e.from);
+     link(e.from, e.to, e.weight);
+   }
-   return nodes;
+   return settle(nodes, { steps: 120 });
+ }
  function place(id) {
    seen.add(id);
    grid.put(id, nearestFree(id));
  }
+ // commit: 3 files changed
+ git.add(['graph.ts', 'layout.ts']);
+ git.commit('map layout: stable seeds');
"""]
private func paveTournage(_ etat: String) -> [LigneCode] {
    PAVE_TOURNAGE[PAVE_TOURNAGE[etat] != nil ? etat : "autre"]!.components(separatedBy: "\n")
        .map { LigneCode(t: String($0.prefix(LARGEUR)), c: $0.hasPrefix("──") ? "tete" : classe($0)) }
}

/// The block: a 78 px disc of the page, 18 slots laid on latitudes of the sphere.
/// Coordinates are those of the orb's page (150 px), y pointing UP (layer not flipped).
final class Pave {
    let calque = CALayer()
    private var fentes: [CALayer] = []
    private(set) var lignes: [LigneCode] = []
    private var images: [LigneCode: CGImage] = [:]
    private var defilement = 0.0
    private var fluxFichier: String?, fluxTaille: UInt64 = 0
    private(set) var montre = false
    private let px: CGFloat            // screen pixels per page px
    let reduit = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion

    init(pixelsParPx: CGFloat) {
        px = pixelsParPx
        calque.frame = CGRect(x: 36, y: 36, width: 78, height: 78)
        calque.cornerRadius = 39; calque.masksToBounds = true
        calque.opacity = 0
        // the text fades towards the edge: radial-gradient(circle at 50% 46%, #000 22%, .68 46%, transparent 66%).
        // "circle" with no size = to the farthest corner: 57.4 px from (39, 35.9).
        let masque = CAGradientLayer()
        masque.type = .radial
        masque.frame = calque.bounds
        let r = (39.0 * 39.0 + (78 - 35.88) * (78 - 35.88)).squareRoot() / 78
        masque.startPoint = CGPoint(x: 0.5, y: 0.54)                 // 46 % from the top, y pointing up
        masque.endPoint = CGPoint(x: 0.5 + r, y: 0.54 + r)
        masque.colors = [NSColor.black.cgColor, NSColor.black.cgColor, NSColor(white: 0, alpha: 0.68).cgColor, NSColor.clear.cgColor]
        masque.locations = [0, 0.22, 0.46, 0.66]
        calque.mask = masque
        for _ in 0..<FENTES {
            let f = CALayer()
            f.bounds = CGRect(x: 0, y: 0, width: 78, height: 7.6)
            f.contentsGravity = .resize
            f.actions = ["contents": NSNull(), "transform": NSNull(), "opacity": NSNull(), "position": NSNull()]
            calque.addSublayer(f); fentes.append(f)
        }
    }

    /// Re-reads the stream (lireFlux): returns `true` if the lines changed.
    @discardableResult func lireFlux(_ etat: String) -> Bool {
        if TOURNAGE { let l = paveTournage(etat); if l == lignes { return false }; lignes = l; images = [:]; return true }
        var f = fichierActif()
        if f == nil && lignesAgent(etat).isEmpty { f = fichierActif(sansAge: true) }
        guard let (chemin, _) = f else {
            let repli = lignesAgent(etat)
            if repli == lignes { return false }
            lignes = repli; fluxFichier = nil; fluxTaille = 0
            return true
        }
        let taille = ((try? FileManager.default.attributesOfItem(atPath: chemin))?[.size] as? NSNumber)?.uint64Value ?? 0
        if chemin == fluxFichier && taille == fluxTaille { return false }
        fluxFichier = chemin; fluxTaille = taille
        // orbe.html read the whole file and kept its last 40 lines: only the end is read here.
        var out: [LigneCode] = []
        for ligne in finDeFichier(chemin, octets: 1 << 20).suffix(40) {
            guard let j = try? JSONSerialization.jsonObject(with: Data(ligne.utf8)) as? [String: Any],
                  j["type"] as? String == "diff", let diff = j["diff"] as? [String] else { continue }
            out.append(LigneCode(t: "── " + ((j["rel"] as? String) ?? (j["file"] as? String) ?? "?"), c: "tete"))
            for d in diff {
                var t = d.replacingOccurrences(of: "\t", with: "  ")
                t = t.replacingOccurrences(of: "\\s+$", with: "", options: .regularExpression)
                t = t.replacingOccurrences(of: "^([+-]?) {2,}", with: "$1 ", options: .regularExpression)
                if t.isEmpty { continue }
                out.append(LigneCode(t: String(t.prefix(LARGEUR)), c: classe(t)))
            }
        }
        lignes = Array(out.suffix(GARDE))
        if images.count > 400 { images = [:] }
        return true
    }

    /// Shows or hides the block, with a 0.5 s fade (#pave.vu).
    func montrer(_ v: Bool) {
        let v = v && !lignes.isEmpty
        if v == montre { return }
        montre = v
        CATransaction.begin(); CATransaction.setAnimationDuration(0.5)
        CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(name: .default))
        calque.opacity = v ? 1 : 0
        CATransaction.commit()
        if v { tourner(0) }
    }

    /// tournerPave: the latitudes slide, not the block. y = R·sin θ, the line narrows by cos θ.
    func tourner(_ dt: Double) {
        guard montre, !lignes.isEmpty else { return }
        if !reduit { defilement += 1.25 * dt }
        let base = Int(defilement.rounded(.down)), frac = defilement - Double(base)
        CATransaction.begin(); CATransaction.setDisableActions(true)
        for k in 0..<FENTES {
            let th = (((Double(k) - frac) / Double(FENTES - 1)) - 0.5) * .pi * 0.97
            let y = RAYON_TXT * CGFloat(sin(th)), sx = CGFloat(cos(th))
            let l = lignes[(base + k) % lignes.count]
            let f = fentes[k]
            if let img = image(l), (f.contents as AnyObject?) !== img { f.contents = img }
            // CSS: translate(0, 37 + y) from the top, origin at the line's centre; here y points up.
            f.position = CGPoint(x: 39, y: 78 - (37 + y) - 3.8)
            f.transform = CATransform3DMakeScale(sx, 1, 1)
            f.opacity = Float(0.5 + 0.5 * pow(Double(sx), 0.9))
        }
        CATransaction.commit()
    }

    /// A line rendered once: monospace 600 at 6 px, centred in 78 × 7.6, with its three shadows.
    private func image(_ l: LigneCode) -> CGImage? {
        if let i = images[l] { return i }
        let W = Int((78 * px).rounded(.up)), H = Int((7.6 * px).rounded(.up))
        guard let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        let teinte: Int = ["plus": 0x9dffc4, "moins": 0x4fae76, "tete": 0xe6fff1][l.c] ?? 0x6dfaa2
        let font = NSFont.monospacedSystemFont(ofSize: 6 * px, weight: .semibold)
        let chaine = NSAttributedString(string: l.t, attributes: [
            .font: font, .kern: -0.05 * px, .foregroundColor: hexCouleur(teinte)])
        let ligne = CTLineCreateWithAttributedString(chaine)
        let w = CTLineGetTypographicBounds(ligne, nil, nil, nil)
        let asc = font.ascender, desc = -font.descender
        let x = (CGFloat(W) - CGFloat(w)) / 2
        let base = CGFloat(H) - ((7.6 * px - (asc + desc)) / 2 + asc)     // y pointing up
        // text-shadow: 0 0 1.5px rgba(0,22,12,.95), 0 0 4px rgba(0,30,16,.6), 0 1px 1px rgba(0,0,0,.55).
        // Shadows alone first (text drawn off canvas, its shadow brought back in), the last in the list at the bottom.
        let loin: CGFloat = 4 * CGFloat(W)
        for (dy, flou, c) in [(1.0, 1.0, NSColor(white: 0, alpha: 0.55)),
                              (0, 4, NSColor(srgbRed: 0, green: 30 / 255, blue: 16 / 255, alpha: 0.6)),
                              (0, 1.5, NSColor(srgbRed: 0, green: 22 / 255, blue: 12 / 255, alpha: 0.95))] as [(CGFloat, CGFloat, NSColor)] {
            ctx.saveGState()
            ctx.setShadow(offset: CGSize(width: loin, height: -dy * px), blur: flou * px, color: c.cgColor)
            ctx.textPosition = CGPoint(x: x - loin, y: base)
            CTLineDraw(ligne, ctx)
            ctx.restoreGState()
        }
        ctx.textPosition = CGPoint(x: x, y: base)
        CTLineDraw(ligne, ctx)
        let i = ctx.makeImage()
        images[l] = i
        return i
    }
}

func hexCouleur(_ v: Int, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255, blue: CGFloat(v & 255) / 255, alpha: a)
}
