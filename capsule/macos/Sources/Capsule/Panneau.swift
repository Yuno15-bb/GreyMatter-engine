// THE PANEL that drops under the pill, native: a port of `ilot.html?panneau`, of the large orb
// `orbe.html?ilot` and of the panel part of `ilot.js`, macOS only.
// Every size is the Electron page's, in px; the page was zoomed to 0.75, so here px × ECHELLE = points.
// The sizes follow Apple's HIG for Live Activities.
import AppKit

let ECHELLE: CGFloat = 0.75
let PANNEAU_W: CGFloat = (408 * ECHELLE).rounded()
/// Filming the pill alone: the panel does not open by itself.
let PANNEAU_REPLIE = ENV["CAPSULE_PASTILLE_SEULE"] == "1"
struct Textes { let repos, dernier, etape, etapes, fini, par: String }
let TXT = Textes(repos: "Idle", dernier: "last run", etape: "step", etapes: "steps", fini: TXT_FINI, par: "by")

func mmss(_ s: TimeInterval) -> String { let t = max(0, Int(s.rounded(.down))); return "\(t / 60):" + String(format: "%02d", t % 60) }
/// A note slug reads as words; free text passes as is.
func lisible(_ d: String) -> String {
    d.range(of: "^[a-z0-9][a-z0-9-]*$", options: .regularExpression) != nil ? d.replacingOccurrences(of: "-", with: " ") : d
}
func couleur(_ c: RGB8, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat(c.r) / 255, green: CGFloat(c.g) / 255, blue: CGFloat(c.b) / 255, alpha: a)
}

// ── ONE TEXT OF THE PAGE ────────────────────────────────────────────────────
let OPSZ_CSS = ENV["CAPSULE_OPSZ"] != "0"
struct Style {
    var taille: CGFloat, graisse: NSFont.Weight, couleur: NSColor = .white, kern: CGFloat = 0, chiffres = false
    func police(_ k: CGFloat = 1) -> NSFont {
        let f = chiffres ? NSFont.monospacedDigitSystemFont(ofSize: taille * k, weight: graisse) : NSFont.systemFont(ofSize: taille * k, weight: graisse)
        // Chromium takes the optical size from the CSS size, BEFORE the 0.75 zoom: "GreyMatter" is 122 screen
        // px there; 126 here without this setting, 117 at pixel size (measured 2026-09-27).
        guard OPSZ_CSS else { return f }
        let d = f.fontDescriptor.addingAttributes([NSFontDescriptor.AttributeName("NSCTFontOpticalSizeAttribute"): taille])
        return NSFont(descriptor: d, size: taille * k) ?? f
    }
    var monte: CGFloat { police(ECHELLE).ascender / ECHELLE }
    var descend: CGFloat { -police(ECHELLE).descender / ECHELLE }
    /// Measured at the real size in points: the optical size (SF Text under 20 pt, SF Display
    /// above) changes the advance, and Chromium picks from points, not pixels.
    func largeur(_ t: String) -> CGFloat {
        CGFloat(CTLineGetTypographicBounds(CTLineCreateWithAttributedString(chaine(t, ECHELLE)), nil, nil, nil)) / ECHELLE
    }
    func chaine(_ t: String, _ k: CGFloat = 1) -> NSAttributedString {
        NSAttributedString(string: t, attributes: [.font: police(k), .foregroundColor: couleur, .kern: kern * k])
    }
}

/// A text rendered to an image ONCE per change, never on every frame. The shadows (text-shadow)
/// are painted alone first, the text on top, as the browser does.
final class Texte: NSView {
    override var isFlipped: Bool { true }
    private var image: NSImage?
    private var cle = ""
    private(set) var largeurPx: CGFloat = 0

    /// `x` (left edge, or centre if `centre`) and `ligneDeBase` in page px, in the page's coordinates.
    func poser(_ t: String, _ s: Style, x: CGFloat, ligneDeBase: CGFloat,
               ombres: [(CGFloat, NSColor)] = [], largeurMax: CGFloat? = nil, centre: Bool = false) {
        let retina = window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2
        let k = ECHELLE * retina, e = ECHELLE
        // the line is set at its size in POINTS, then the context is scaled up: same optical size as Chromium
        var ligne = CTLineCreateWithAttributedString(s.chaine(t, e))
        var w = CGFloat(CTLineGetTypographicBounds(ligne, nil, nil, nil)) / e
        if let m = largeurMax, w > m,
           let coupe = CTLineCreateTruncatedLine(ligne, Double(m * e), .end, CTLineCreateWithAttributedString(s.chaine("…", e))) {
            ligne = coupe; w = CGFloat(CTLineGetTypographicBounds(ligne, nil, nil, nil)) / e
        }
        largeurPx = w
        let marge = ceil((ombres.map { $0.0 }.max() ?? 0) * 1.6) + 1
        let asc = s.monte, desc = s.descend
        let gauche = x - (centre ? w / 2 : 0) - marge
        frame = NSRect(x: gauche * ECHELLE, y: (ligneDeBase - asc - marge) * ECHELLE,
                       width: (w + 2 * marge) * ECHELLE, height: (asc + desc + 2 * marge) * ECHELLE)
        let c = "\(t)|\(s.taille)|\(s.couleur)|\(s.kern)|\(ombres.map { "\($0.0)\($0.1)" })|\(w)"
        if c == cle { return }
        cle = c
        let W = Int(((w + 2 * marge) * k).rounded(.up)), H = Int(((asc + desc + 2 * marge) * k).rounded(.up))
        guard W > 0, H > 0, let ctx = CGContext(data: nil, width: W, height: H, bitsPerComponent: 8, bytesPerRow: 0,
                                                space: CGColorSpace(name: CGColorSpace.sRGB)!,
                                                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return }
        ctx.scaleBy(x: retina, y: retina)
        let base = CGPoint(x: marge * e, y: (marge + desc) * e)
        let loin = CGFloat(4 * W)
        for (flou, c) in ombres.reversed() {
            ctx.saveGState()
            ctx.setShadow(offset: CGSize(width: loin, height: 0), blur: flou * k, color: c.cgColor)
            ctx.textPosition = CGPoint(x: base.x - loin / retina, y: base.y)   // the shadow shifts in pixels, the text in points
            CTLineDraw(ligne, ctx)
            ctx.restoreGState()
        }
        ctx.textPosition = base
        CTLineDraw(ligne, ctx)
        if let cg = ctx.makeImage() { image = NSImage(cgImage: cg, size: frame.size) }
        needsDisplay = true
    }
    override func draw(_ r: NSRect) {
        image?.draw(in: bounds, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
    }
}

/// The page: y pointing down, like HTML. Layers added to it by hand are too.
final class Page: NSView { override var isFlipped: Bool { true } }

/// A window's slide (ilot.js glisser): 260 ms, 1 − (1 − k)³, one step every 16 ms.
/// A target that changes on the way (the panel's height) joins the slide in progress.
enum Glisse {
    private static var minuteurs: [ObjectIdentifier: Timer] = [:]
    private(set) static var cibles: [ObjectIdentifier: NSRect] = [:]
    static func enCours(_ w: NSWindow) -> Bool { minuteurs[ObjectIdentifier(w)] != nil }
    static func changerCible(_ w: NSWindow, _ c: NSRect) { cibles[ObjectIdentifier(w)] = c }
    static func glisser(_ w: NSWindow, vers cible: NSRect, duree: Double = 0.26) {
        let id = ObjectIdentifier(w)
        minuteurs[id]?.invalidate()
        cibles[id] = cible
        let de = w.frame, t0 = CACurrentMediaTime()
        let pas: (Timer?) -> Void = { m in
            let k = min(1, (CACurrentMediaTime() - t0) / duree), e = CGFloat(1 - pow(1 - k, 3))
            let c = cibles[id] ?? cible
            func m_(_ a: CGFloat, _ b: CGFloat) -> CGFloat { (a + (b - a) * e).rounded() }
            // in AppKit, y is the bottom: the TOP slides, as setBounds did
            let haut = m_(de.maxY, c.maxY), h = m_(de.height, c.height)
            w.setFrame(NSRect(x: m_(de.minX, c.minX), y: haut - h, width: m_(de.width, c.width), height: h), display: true)
            if k >= 1 { m?.invalidate(); minuteurs[id] = nil; cibles[id] = nil }
        }
        let m = Timer(timeInterval: 0.016, repeats: true) { pas($0) }
        RunLoop.main.add(m, forMode: .common)
        minuteurs[id] = m
        pas(nil)
    }
}

final class Panneau {
    let fen: NSPanel
    let orbe: Orbe
    let pave: Pave
    private let page = Page()
    private let titre = Texte(), vaisseau = Texte(), grand = Texte(), sous = Texte()
    private let points = [Texte(), Texte(), Texte()]
    private var noms: [Texte] = []
    private let piste = CALayer(), rail = CAShapeLayer(), plein = CALayer()
    private var arrets: [CALayer] = [], arretIci: CALayer?
    private var hPage: CGFloat = 138
    private var cle = ""
    private var course: Course?
    private var minuteurs: [Timer] = []
    private var phasePoints = 0
    private var yPoints: CGFloat = 0
    private let reduit = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    var visible: Bool { fen.isVisible }
    var auClic: (() -> Void)? { didSet { (fen.contentView as? Cliquable)?.clic = auClic } }

    // The page's styles (ilot.html)
    private let sTitre = Style(taille: 15, graisse: .bold, kern: -0.1)
    private let sPoint = Style(taille: 19, graisse: .heavy)
    private let sGrand = Style(taille: 17, graisse: .bold, chiffres: true)
    private let sSous = Style(taille: 13, graisse: .semibold)
    private let sNom = Style(taille: 10, graisse: .bold, kern: 0.8)

    init(depart: Reglage) {
        let echelle = NSScreen.screens.first?.backingScaleFactor ?? 2
        let h0 = ceil(138 * ECHELLE)
        fen = NSPanel(contentRect: NSRect(x: 0, y: 0, width: PANNEAU_W, height: h0),
                      styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        fen.isOpaque = false; fen.backgroundColor = .clear
        // On glass, no window shadow: it cost WindowServer about 11 % of a core (measured 2026-09-25).
        fen.hasShadow = !verreLiquide()
        fen.level = .screenSaver
        fen.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        fen.isReleasedWhenClosed = false
        fen.hidesOnDeactivate = false

        // The whole panel answers the click: before, only a click on the pill closed it.
        let racine = Cliquable(frame: NSRect(x: 0, y: 0, width: PANNEAU_W, height: h0))
        racine.wantsLayer = true
        racine.addSubview(fondVerre(racine.bounds, rayon: (24 * ECHELLE).rounded(), teinte: 0x1a))
        page.frame = racine.bounds; page.autoresizingMask = [.width, .height]
        page.wantsLayer = true
        page.layer!.cornerRadius = 24 * ECHELLE
        page.layer!.borderWidth = 0.5 * ECHELLE                          // inset 0 0 0 .5px rgba(255,255,255,.28)
        page.layer!.borderColor = NSColor(white: 1, alpha: 0.28).cgColor
        racine.addSubview(page)

        // ── the header: the logo and "GreyMatter" ──
        let logo = NSImageView(frame: NSRect(x: 14 * ECHELLE, y: 14 * ECHELLE, width: 22 * ECHELLE, height: 22 * ECHELLE))
        logo.image = NSImage(contentsOfFile: dossierCapsule().appendingPathComponent("assets/gmtr-128.png").path)
        logo.imageScaling = .scaleProportionallyUpOrDown
        logo.wantsLayer = true; logo.layer!.cornerRadius = 6 * ECHELLE; logo.layer!.masksToBounds = true
        page.addSubview(logo)
        for t in [titre, vaisseau, grand, sous] + points { page.addSubview(t) }
        grand.alphaValue = 0.55; sous.alphaValue = 0.62
        let hTitre = sTitre.monte + sTitre.descend
        titre.poser("GreyMatter", sTitre, x: 14 + 22 + 7, ligneDeBase: 14 + (22 - hTitre) / 2 + sTitre.monte)

        // ── the track ──
        piste.isHidden = true
        rail.strokeColor = NSColor(white: 1, alpha: 0.22).cgColor
        rail.lineWidth = 3 * ECHELLE; rail.lineCap = .round
        rail.lineDashPattern = [0, NSNumber(value: Double(6 * ECHELLE))]
        rail.fillColor = nil
        plein.backgroundColor = NSColor(white: 1, alpha: 0.9).cgColor
        plein.cornerRadius = 2 * ECHELLE
        piste.addSublayer(rail); piste.addSublayer(plein)
        page.layer!.addSublayer(piste)

        // ── the large orb: 150 page px scaled to 0.9, pinned top right (right 2, top 2) ──
        let cote = 150 * 0.9 * ECHELLE
        let zone = NSView(frame: NSRect(x: (408 - 2) * ECHELLE - cote, y: 2 * ECHELLE, width: cote, height: cote))
        zone.wantsLayer = true
        orbe = Orbe(cotePt: cote, echelle: echelle, depart: depart)
        orbe.couche.frame = zone.bounds
        zone.layer!.addSublayer(orbe.couche)
        pave = Pave(pixelsParPx: 0.9 * ECHELLE * echelle)
        let repere = CALayer()
        repere.bounds = CGRect(x: 0, y: 0, width: 150, height: 150)
        repere.position = CGPoint(x: cote / 2, y: cote / 2)
        repere.transform = CATransform3DMakeScale(0.9 * ECHELLE, 0.9 * ECHELLE, 1)
        repere.addSublayer(pave.calque)
        zone.layer!.addSublayer(repere)
        page.addSubview(zone)
        orbe.surImage = { [weak self] dt in self?.pave.tourner(dt) }

        fen.contentView = racine
    }

    // ── OPEN, CLOSE, FOLLOW (ilot.js) ───────────────────────────────────────
    /// The panel aligns on the RIGHT edge of the reserved slot, the only one that does not move.
    /// Bench: the top-left corner is forced, in screen coordinates counted from the TOP (Electron's).
    var poseImposee: CGPoint?
    private func cadre(_ place: NSRect) -> NSRect {
        let ecran = NSScreen.screens.first!.frame
        let barre = max(24, ecran.maxY - NSScreen.screens.first!.visibleFrame.maxY)
        var x = (place.maxX - PANNEAU_W).rounded()
        x = max(ecran.minX + 8, min(x, ecran.maxX - PANNEAU_W - 8))
        let h = ceil(max(138, min(160, hPage)) * ECHELLE)
        if let p = poseImposee { return NSRect(x: p.x, y: ecran.maxY - p.y - h, width: PANNEAU_W, height: h) }
        return NSRect(x: x, y: ecran.maxY - barre - 3 - h, width: PANNEAU_W, height: h)
    }
    func ouvrir(place: NSRect) {
        if visible { return }
        fen.setFrame(cadre(place), display: false)
        fen.orderFrontRegardless()                       // without taking focus: the terminal keeps it
        tomber()
        minuteurs = [Timer(timeInterval: 0.25, repeats: true) { [weak self] _ in self?.chrono() }]
        if !reduit { minuteurs.append(Timer(timeInterval: 0.34, repeats: true) { [weak self] _ in self?.sauterPoints() }) }
        minuteurs.forEach { RunLoop.main.add($0, forMode: .common) }
        chrono()
    }
    func fermer() {
        if !visible { return }
        fen.orderOut(nil)
        minuteurs.forEach { $0.invalidate() }; minuteurs = []
        orbe.arreter()
    }
    func suivre(place: NSRect) {
        guard visible else { return }
        let c = cadre(place)
        if c.minX != fen.frame.minX { Glisse.glisser(fen, vers: c) }
    }
    /// The drop on opening: 0.42 s, cubic-bezier(.2, 1.3, .4, 1), from (opacity 0, −8 px, 0.96) to rest.
    private func tomber() {
        guard !reduit, let l = page.layer else { return }
        let w = page.bounds.width, h = page.bounds.height
        // the layer's origin is bottom left; the scale happens around the top centre
        var t = CATransform3DMakeTranslation(-w / 2, -h, 0)
        t = CATransform3DConcat(t, CATransform3DMakeScale(0.96, 0.96, 1))
        t = CATransform3DConcat(t, CATransform3DMakeTranslation(w / 2, h + 8 * ECHELLE, 0))
        let tr = CABasicAnimation(keyPath: "transform"); tr.fromValue = t; tr.toValue = CATransform3DIdentity
        let op = CABasicAnimation(keyPath: "opacity"); op.fromValue = 0; op.toValue = 1
        let g = CAAnimationGroup(); g.animations = [tr, op]; g.duration = 0.42
        g.timingFunction = CAMediaTimingFunction(controlPoints: 0.2, 1.3, 0.4, 1)
        l.add(g, forKey: "tombe")
    }

    // ── THE CLOCK AND THE DOTS ───────────────────────────────────────────────
    private var xGrand: CGFloat = 0, baseLigne: CGFloat = 0
    func chrono() {
        guard let c = course, visible, !c.repos else { return }
        let t = mmss((c.fin ?? Date()).timeIntervalSince(c.t0))
        grand.poser(t, sGrand, x: xGrand, ligneDeBase: baseLigne)
    }
    private func sauterPoints() {
        guard let c = course, visible, c.fin == nil else { return }
        phasePoints = (phasePoints + 1) % 4
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.17
            ctx.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            for (i, p) in points.enumerated() {
                p.animator().setFrameOrigin(NSPoint(x: p.frame.minX, y: yPoints - (i == phasePoints ? 2.5 * ECHELLE : 0)))
            }
        }
        if let a = arretIci {
            CATransaction.begin(); CATransaction.setAnimationDuration(0.6)
            CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(name: .easeInEaseOut))
            a.transform = phasePoints < 2 ? CATransform3DMakeScale(1.18, 1.18, 1) : CATransform3DIdentity
            CATransaction.commit()
        }
    }

    // ── PAINT (ilot.html peindre, panel side) ────────────────────────────────
    func peindre(_ c: Course) {
        course = c
        let st = c.stations, ici = st.last, fini = c.fin != nil, repos = c.repos
        let detail = lisible(c.detail).isEmpty ? c.theme : lisible(c.detail)
        let n = st.count
        let nouvelle = "\(st.map { $0.vaisseau + $0.etat })|\(fini)|\(repos)|\(detail)|\(c.dernier.map { "\($0.n)-\(Int($0.duree))" } ?? "")"
        if nouvelle == cle { return chrono() }
        cle = nouvelle

        let r = reglage(repos || fini ? "idle" : (ici?.etat ?? "idle"))
        let (mr, mg, mb) = melangeOklab(r.c1, 0.55, r.c2)
        let blanc = fini || repos
        let sV = Style(taille: 19, graisse: .heavy, couleur: blanc ? .white : NSColor(srgbRed: mr, green: mg, blue: mb, alpha: 1),
                       kern: blanc ? 0 : 1.4)
        let ombres: [(CGFloat, NSColor)] = blanc ? [] : [(6, couleur(r.c2, 0.82)), (17, couleur(r.c2, 0.52))]
        let nomV = repos ? TXT.repos : (fini ? TXT.fini : (ici?.vaisseau ?? ""))

        // The line: aligned on the baseline; .vaisseau has a 23 px line height.
        let demi = (23 - (sV.monte + sV.descend)) / 2
        var dessus = demi + sV.monte, dessous = 23 - demi - sV.monte
        if !fini { dessus = max(dessus, sPoint.monte); dessous = max(dessous, sPoint.descend) }
        if !repos { dessus = max(dessus, sGrand.monte); dessous = max(dessous, sGrand.descend) }
        let haut: CGFloat = 14 + 22 + 8
        baseLigne = haut + dessus
        vaisseau.poser(nomV, sV, x: 14, ligneDeBase: baseLigne, ombres: ombres)
        let wV = sV.largeur(nomV)
        let x0 = 14 + wV + 8 - 6, avance = sPoint.largeur(".")
        for (i, p) in points.enumerated() {
            p.isHidden = fini
            p.poser(".", sPoint, x: x0 + CGFloat(i) * avance, ligneDeBase: baseLigne)
        }
        yPoints = points[0].frame.minY
        xGrand = fini ? 14 + wV + 8 : x0 + 3 * avance + 8
        grand.isHidden = repos
        chrono()

        let hautSous = haut + dessus + dessous + 1
        let texteSous: String
        if repos {
            texteSous = c.dernier.map { TXT.dernier + " · " + ($0.n > 1 ? "\($0.n) " + TXT.etapes : "1 " + TXT.etape) + " · " + mmss($0.duree) } ?? ""
        } else if fini {
            texteSous = n > 1 ? "\(n) " + TXT.etapes : TXT.par + " " + (ici?.vaisseau ?? "")
        } else {
            texteSous = ici.map { detail.isEmpty ? $0.etat : $0.etat + " · " + detail } ?? ""
        }
        sous.poser(texteSous, sSous, x: 14, ligneDeBase: hautSous + (17 - (sSous.monte + sSous.descend)) / 2 + sSous.monte,
                   largeurMax: 408 - 28 - 128)

        // ── the track, from the first step ──
        let etapes = !repos && n >= 1
        let hautPiste = hautSous + 17 + 12
        noms.forEach { $0.removeFromSuperview() }; noms = []
        arrets.forEach { $0.removeFromSuperlayer() }; arrets = []; arretIci = nil
        piste.isHidden = !etapes
        if etapes { dessinerPiste(st, fini: fini, haut: hautPiste) }

        hPage = etapes ? hautPiste + 34 + 14 : hautSous + 17 + 14
        let h = ceil(max(138, min(160, hPage)) * ECHELLE)
        if fen.frame.height != h {
            let f = fen.frame, c = NSRect(x: f.minX, y: f.maxY - h, width: f.width, height: h)
            if Glisse.enCours(fen) { var g = Glisse.cibles[ObjectIdentifier(fen)] ?? c; g.origin.y = g.maxY - h; g.size.height = h; Glisse.changerCible(fen, g) }
            else { fen.setFrame(c, display: true) }
        }
    }

    private func dessinerPiste(_ st: [Station], fini: Bool, haut: CGFloat) {
        let E = ECHELLE, n = st.count, places = CGFloat(n)
        CATransaction.begin(); CATransaction.setDisableActions(true)
        piste.frame = CGRect(x: 14 * E, y: haut * E, width: 252 * E, height: 34 * E)
        let ch = CGMutablePath(); ch.move(to: CGPoint(x: 8 * E, y: 7.5 * E)); ch.addLine(to: CGPoint(x: 244 * E, y: 7.5 * E))
        rail.path = ch
        CATransaction.commit()
        let pos = { (i: Int) -> CGFloat in 8 + 236 * CGFloat(i) / places }
        for (i, x) in st.enumerated() {
            let courant = !fini && i == n - 1
            let a = arret(teinte: couleur(reglage(x.etat).c2), lueur: courant, fin: false)
            a.position = CGPoint(x: pos(i) * E, y: 7.5 * E)
            piste.addSublayer(a); arrets.append(a)
            if courant { arretIci = a }
        }
        if fini {
            let f = arret(teinte: .white, lueur: false, fin: true)
            f.position = CGPoint(x: pos(n) * E, y: 7.5 * E)
            piste.addSublayer(f); arrets.append(f)
        }
        // Under 84 px apart, only the last step's name stays written (the names overlapped).
        let ecart = (252 - 16) / places
        for (i, x) in st.enumerated() where ecart >= 84 || i == n - 1 {
            let t = Texte(); page.addSubview(t); noms.append(t)
            t.alphaValue = (!fini && i == n - 1) ? 0.95 : 0.5
            let base = haut + 21 + sNom.monte
            if i == 0 { t.poser(x.vaisseau, sNom, x: 14 + pos(0) - 7.5, ligneDeBase: base) }
            else { t.poser(x.vaisseau, sNom, x: 14 + pos(i), ligneDeBase: base, centre: true) }
        }
        // the solid line: (100 % − 16) × (done ? n : n − 1) / n, over 0.8 s
        CATransaction.begin(); CATransaction.setAnimationDuration(0.8)
        CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(controlPoints: 0.3, 0.8, 0.3, 1))
        plein.frame = CGRect(x: 8 * E, y: 6 * E, width: 236 * E * CGFloat(fini ? n : n - 1) / places, height: 3 * E)
        CATransaction.commit()
    }

    /// A stop: a 15 px disc in the step's hue, a 2.5 px white ring,
    /// and for the current step a 10 px glow spread by 2. The finish is white, with its tick.
    private func arret(teinte: NSColor, lueur: Bool, fin: Bool) -> CALayer {
        let E = ECHELLE
        let a = CALayer(); a.bounds = CGRect(x: 0, y: 0, width: 15 * E, height: 15 * E)
        func rond(_ r: CGFloat, _ c: NSColor) -> CALayer {
            let l = CALayer(); l.frame = a.bounds.insetBy(dx: -r * E, dy: -r * E)
            l.cornerRadius = l.frame.width / 2; l.backgroundColor = c.cgColor; return l
        }
        if lueur {
            let g = rond(2, teinte)
            g.shadowColor = teinte.cgColor; g.shadowOpacity = 1; g.shadowRadius = 10 * E / 2; g.shadowOffset = .zero
            g.shadowPath = CGPath(ellipseIn: g.bounds, transform: nil)
            a.addSublayer(g)
        }
        a.addSublayer(rond(2.5, .white))
        a.addSublayer(rond(0, teinte))
        if fin {
            // <svg viewBox="0 0 10 10"> 9 × 9 px centred: M2 5.2 4.2 7.4 8 3, #111 stroke of 1.9
            let k = 0.9 * E, o = 3 * E
            let p = CGMutablePath()
            p.move(to: CGPoint(x: o + 2 * k, y: o + 5.2 * k)); p.addLine(to: CGPoint(x: o + 4.2 * k, y: o + 7.4 * k))
            p.addLine(to: CGPoint(x: o + 8 * k, y: o + 3 * k))
            let s = CAShapeLayer(); s.frame = a.bounds; s.path = p; s.fillColor = nil
            s.strokeColor = hexCouleur(0x111111).cgColor; s.lineWidth = 1.9 * k; s.lineCap = .round; s.lineJoin = .round
            a.addSublayer(s)
        }
        return a
    }
}

/// The `capsule/` folder (for `assets/`): walk up from the executable, otherwise <trunk>/capsule.
func dossierCapsule() -> URL {
    var u = Bundle.main.executableURL?.deletingLastPathComponent()
    while let d = u, d.path != "/" {
        if FileManager.default.fileExists(atPath: d.appendingPathComponent("assets/gmtr-128.png").path) { return d }
        u = d.deletingLastPathComponent()
    }
    return URL(fileURLWithPath: TRONC).appendingPathComponent("capsule")
}
