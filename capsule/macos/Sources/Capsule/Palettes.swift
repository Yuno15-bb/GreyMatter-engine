// MEANING: a faithful port of `orbe/palettes.js`, `orbe/couleur.js` and `orbe/mecaniques.js`.
// The reasons behind each value live there and are not copied here.
import Foundation

enum Mecanique: Float { case houle = 0, balayage, plaques, ebullition, ondeDeChoc, cellules, vortex, respiration, interference, eclats }

// ── OKLCh → sRGB, with a real gamut check (couleur.js) ──────────────────────
private let M: [[Double]] = [
    [+4.0767416621, -3.3077115913, +0.2309699292],
    [-1.2684380046, +2.6097574011, -0.3413193965],
    [-0.0041960863, -0.7034186147, +1.7076147010],
]

private func versLineaire(_ L: Double, _ C: Double, _ hDeg: Double) -> [Double] {
    let h = hDeg * .pi / 180, a = C * cos(h), b = C * sin(h)
    let l = pow(L + 0.3963377774 * a + 0.2158037573 * b, 3)
    let m = pow(L - 0.1055613458 * a - 0.0638541728 * b, 3)
    let s = pow(L - 0.0894841775 * a - 1.2914855480 * b, 3)
    return M.map { $0[0] * l + $0[1] * m + $0[2] * s }
}

private func tenable(_ L: Double, _ C: Double, _ h: Double, marge: Double = 0.001) -> Bool {
    versLineaire(L, C, h).allSatisfy { $0 >= -marge && $0 <= 1 + marge }
}

private func gamma(_ u0: Double) -> Int {
    let u = min(1, max(0, u0))
    return Int(((u > 0.0031308 ? 1.055 * pow(u, 1 / 2.4) - 0.055 : 12.92 * u) * 255).rounded())
}

/// An 8-bit sRGB colour, like the `#rrggbb` that `hex()` returns on the JS side.
struct RGB8: Equatable { var r, g, b: Int }

func hex(_ L: Double, _ C: Double, _ h: Double) -> RGB8 {
    var c = C
    if !tenable(L, c, h) {
        var lo = 0.0, hi = C
        for _ in 0..<16 { let mid = (lo + hi) / 2; if tenable(L, mid, h) { lo = mid } else { hi = mid } }
        c = lo
    }
    let v = versLineaire(L, c, h).map(gamma)
    return RGB8(r: v[0], g: v[1], b: v[2])
}

func chromaMax(_ L: Double, _ h: Double) -> Double {
    var lo = 0.0, hi = 0.45
    for _ in 0..<18 { let mid = (lo + hi) / 2; if tenable(L, mid, h) { lo = mid } else { hi = mid } }
    return lo
}

// ── Families and states (palettes.js) ─────────────────────────────────────
struct Matiere { let disp, freq, speed: Double }
struct Famille { let nom: String; let meca: Mecanique; let teinte, chroma: Double; let lent, vif: Matiere }

let FAMILLES: [String: Famille] = [
    "repos": Famille(nom: "Idle", meca: .respiration, teinte: 288, chroma: 0.50,
                     lent: Matiere(disp: 0.085, freq: 0.55, speed: 0.42), vif: Matiere(disp: 0.100, freq: 0.65, speed: 0.52)),
    "inspection": Famille(nom: "Inspection", meca: .houle, teinte: 252, chroma: 0.85,
                          lent: Matiere(disp: 0.090, freq: 0.85, speed: 0.22), vif: Matiere(disp: 0.150, freq: 1.35, speed: 0.62)),
    "organisation": Famille(nom: "Organisation", meca: .balayage, teinte: 150, chroma: 0.85,
                            lent: Matiere(disp: 0.120, freq: 0.90, speed: 0.28), vif: Matiere(disp: 0.230, freq: 1.60, speed: 0.80)),
    "transformation": Famille(nom: "Transformation", meca: .vortex, teinte: 300, chroma: 0.85,
                              lent: Matiere(disp: 0.150, freq: 1.05, speed: 0.45), vif: Matiere(disp: 0.280, freq: 1.80, speed: 1.25)),
    "validation": Famille(nom: "Validation", meca: .eclats, teinte: 50, chroma: 0.90,
                          lent: Matiere(disp: 0.130, freq: 1.10, speed: 0.65), vif: Matiere(disp: 0.165, freq: 1.35, speed: 0.95)),
]

let ETATS: [String: (String, Double)] = [
    "idle": ("repos", 0.0),
    "mapping": ("inspection", 0.10), "auditing": ("inspection", 0.40),
    "architecting": ("inspection", 0.70), "challenging": ("inspection", 1.00),
    "filing": ("organisation", 0.10), "archiving": ("organisation", 0.40),
    "gardening": ("organisation", 0.70), "correcting": ("organisation", 1.00),
    "working": ("transformation", 0.15), "distilling": ("transformation", 0.60),
    "synthesizing": ("transformation", 1.00),
    "committing": ("validation", 1.00),
]

struct Reglage: Equatable {
    var c1, c2, c3, rim: RGB8
    var rimI, disp, freq, speed: Double
    var meca: Mecanique
}

private func entre(_ a: Double, _ b: Double, _ k: Double) -> Double { a + (b - a) * k }

func reglage(_ etat: String) -> Reglage {
    let (nomFam, niv) = ETATS[etat] ?? ETATS["idle"]!
    let f = FAMILLES[nomFam]!
    let nivCouleur = max(niv, 0.50)
    // nuancier(teinte, part, niv)
    let part = f.chroma * (0.72 + 0.28 * nivCouleur)
    let L = 0.74 - 0.20 * nivCouleur
    let vivacite = chromaMax(L, f.teinte) * part
    return Reglage(
        c1: hex(min(0.97, L + 0.30), vivacite * 0.45, f.teinte),
        c2: hex(L, vivacite, f.teinte),
        c3: hex(0.10 + 0.06 * (1 - nivCouleur), vivacite * 0.55, f.teinte),
        rim: hex(0.97, vivacite * 0.35, f.teinte),
        rimI: 1.05 + 0.35 * nivCouleur,
        disp: entre(f.lent.disp, f.vif.disp, niv),
        freq: entre(f.lent.freq, f.vif.freq, niv),
        speed: entre(f.lent.speed, f.vif.speed, niv),
        meca: f.meca)
}

// ── The name's colour: color-mix(in oklab, c1 55%, c2) (ilot.html) ──────────
private func lin(_ c: Int) -> Double { let u = Double(c) / 255; return u <= 0.04045 ? u / 12.92 : pow((u + 0.055) / 1.055, 2.4) }

private func oklab(_ c: RGB8) -> (Double, Double, Double) {
    let r = lin(c.r), g = lin(c.g), b = lin(c.b)
    let l = cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    let m = cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    let s = cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)
}

/// The mix in OKLab, returned as sRGB 0…1.
func melangeOklab(_ a: RGB8, _ pa: Double, _ b: RGB8) -> (Double, Double, Double) {
    let x = oklab(a), y = oklab(b), k = pa
    let L = x.0 * k + y.0 * (1 - k), A = x.1 * k + y.1 * (1 - k), B = x.2 * k + y.2 * (1 - k)
    let l = pow(L + 0.3963377774 * A + 0.2158037573 * B, 3)
    let m = pow(L - 0.1055613458 * A - 0.0638541728 * B, 3)
    let s = pow(L - 0.0894841775 * A - 1.2914855480 * B, 3)
    let v = M.map { $0[0] * l + $0[1] * m + $0[2] * s }.map { Double(gamma($0)) / 255 }
    return (v[0], v[1], v[2])
}

/// Three.js r160 (ColorManagement on): `new THREE.Color('#hex')` stores the colour as LINEAR, and the
/// orb's ShaderMaterial writes it as is, with no conversion back. For the native orb to show the same
/// colours on screen, the uniforms receive the same linear value.
func lineaire(_ c: RGB8) -> SIMD3<Float> { SIMD3(Float(lin(c.r)), Float(lin(c.g)), Float(lin(c.b))) }
