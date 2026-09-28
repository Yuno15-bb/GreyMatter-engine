// THE PILL, native: a port of `ilot.js` + `ilot.html?pilule`, macOS only.
// It sits in the menu bar, shows which agent is working, and drops a panel on click.
//
// Run:        swift build -c release && .build/release/Capsule
// Bench:      CAPSULE_CADENCE=30 BANC_DUREE=15 .build/release/Capsule   (one JSON line, then exits)
// Snapshot:   .build/release/Capsule --image <state> <file.png>            (the orb alone, 4× larger)
// Check:      .build/release/Capsule --check    (what it reads, as one JSON line — no window)
// Panel:      .build/release/Capsule --panel-demo <state> <x> <y> [seconds=8]
import AppKit

let ENV = ProcessInfo.processInfo.environment
let STATUT = (TRONC as NSString).appendingPathComponent("state/status.json")
let REPOS_AVANT_FIN = 4.0, TERMINE_VISIBLE = 6.0
/// Filming mode: the code block in the panel shows a fixed, neutral sample instead of the live diff.
let TOURNAGE = ENV["CAPSULE_TOURNAGE"] == "1"
let TXT_FINI = "Done"
let TXT_REPOS = "idle"

// Same table as ilot.js and orbe.html — the session is TORRENS.
let VAISSEAUX = ["auditing": "NOSTROMO",
                 "mapping": "NARCISSUS", "filing": "NARCISSUS", "gardening": "NARCISSUS", "distilling": "NARCISSUS",
                 "challenging": "SULACO", "architecting": "SULACO", "archiving": "SULACO",
                 "synthesizing": "ANESIDORA",
                 "working": "TORRENS", "committing": "TORRENS", "correcting": "TORRENS"]

// Frame rates of the pill (orbe.html, ?seule): idle 1, working 30, transition 60;
// at rest the orb's clock runs ten times slower. CAPSULE_CADENCE forces all three (bench).
let IMPOSEE = ENV["CAPSULE_CADENCE"].flatMap(Double.init)
let CADENCE = (repos: IMPOSEE ?? 1, travail: IMPOSEE ?? 30, transition: IMPOSEE ?? 60)
let TEMPO_REPOS = IMPOSEE == nil ? 0.1 : 1.0

struct Station { let vaisseau: String; var etat: String }
struct Course {
    var t0 = Date(), fin: Date?, stations: [Station] = [], repos = false
    var detail = "", theme = ""
    /// The last run, kept as one line for whoever opens the panel at rest.
    var dernier: (n: Int, duree: TimeInterval)?
}

/// "Is the status still current?" has ONE definition, hooks/status_freshness.json, shared with
/// brain_status.py. Two windows on purpose: `ts` (refreshed by every tool call) says Claude is
/// still working; `activity_ts` (set only by whoever knows) says the LABEL still describes it.
/// A literal here would drift from the others — tests/capsule_liveness.py keeps it out.
let FRAICHEUR: (vie: Double, activite: Double) = {
    let p = (TRONC as NSString).appendingPathComponent("hooks/status_freshness.json")
    let j = (FileManager.default.contents(atPath: p)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
    return ((j?["liveness_stale_seconds"] as? Double) ?? 30, (j?["activity_stale_seconds"] as? Double) ?? 120)
}()

func lireStatut() -> (etat: String, detail: String) {
    guard let d = FileManager.default.contents(atPath: STATUT),
          let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return ("idle", "") }
    let now = Date().timeIntervalSince1970
    let vivant = now - ((j["ts"] as? Double) ?? 0) < FRAICHEUR.vie
    guard j["state"] as? String == "busy", vivant else { return ("idle", "") }
    // Still working, but a stale label would be a comfortable lie: past its window it says "working",
    // and the detail goes with it — the precise half is the one that misleads.
    let labelFrais = now - ((j["activity_ts"] as? Double) ?? 0) < FRAICHEUR.activite
    return (labelFrais ? ((j["activity"] as? String) ?? "working") : "working",
            labelFrais ? ((j["detail"] as? String) ?? "") : "")
}

func cpu() -> Double {
    var u = rusage(); getrusage(RUSAGE_SELF, &u)
    return Double(u.ru_utime.tv_sec + u.ru_stime.tv_sec) + Double(u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1e6
}
func memoireMo() -> Double {
    var info = task_vm_info_data_t(), n = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
    let r = withUnsafeMutablePointer(to: &info) { $0.withMemoryRebound(to: integer_t.self, capacity: Int(n)) { task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &n) } }
    return r == KERN_SUCCESS ? Double(info.phys_footprint) / 1_048_576 : -1
}

/// The pill's background, BEHIND the content: the newest glass the system has. macOS 26 and later:
/// Liquid Glass (radius h/2, tint #00000026). Before: the macOS blur, "hud" material.
/// `CAPSULE_VERRE=flou` forces the fallback, to look at it on a recent Mac.
/// ⚠ `NSGlassEffectView` exists only in the macOS 26 SDK (Swift 6.2 and later). Built with older
///   tools, the pill keeps the blur instead of refusing to build.
func verreLiquide() -> Bool {
    #if compiler(>=6.2)
    if #available(macOS 26, *) { return ENV["CAPSULE_VERRE"] != "flou" }
    #endif
    return false
}
func fondVerre(_ cadre: NSRect, rayon: CGFloat, teinte: Int = 0x26) -> NSView {
    #if compiler(>=6.2)
    if #available(macOS 26, *), verreLiquide() {
        let verre = NSGlassEffectView(frame: cadre)
        verre.autoresizingMask = [.width, .height]
        verre.cornerRadius = rayon
        verre.tintColor = NSColor(srgbRed: 0, green: 0, blue: 0, alpha: CGFloat(teinte) / 255)
        return verre
    }
    #endif
    let flou = NSVisualEffectView(frame: cadre)
    flou.autoresizingMask = [.width, .height]
    flou.material = .hudWindow; flou.blendingMode = .behindWindow; flou.state = .active
    flou.maskImage = NSImage(size: cadre.size, flipped: false) { r in
        NSColor.black.setFill(); NSBezierPath(roundedRect: r, xRadius: rayon, yRadius: rayon).fill(); return true
    }
    return flou
}

/// The whole pill answers the click without activating the app: the terminal keeps the focus.
final class Cliquable: NSView {
    var clic: (() -> Void)?
    override func hitTest(_ p: NSPoint) -> NSView? { frame.contains(p) ? self : nil }
    override func acceptsFirstMouse(for e: NSEvent?) -> Bool { true }
    override func mouseDown(with e: NSEvent) { clic?() }
}

final class Pastille: NSObject, NSApplicationDelegate {
    let H: CGFloat = 26
    var W: CGFloat = 86
    var item: NSStatusItem!
    var fen: NSPanel!
    var orbe: Orbe!
    var panneau: Panneau!
    var contenu: NSView!
    let texte = NSTextField(labelWithString: "")
    var course: Course?
    var attenteFin: Timer?, attenteEfface: Timer?
    var cible = reglage("idle"), cibleAtteinte: Reglage?, glisseur: Timer?
    var dernierEtatOrbe = "", occupe = false
    let reduit = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion

    func applicationDidFinishLaunching(_ n: Notification) {
        W = largeurFixe()
        // ── AN EMPTY STATUS ITEM HOLDS THE PLACE, THE PILL FLOATS OVER IT ──
        //    The pill must keep a FIXED place in the menu bar, whatever the other icons do. That place
        //    comes from `autosaveName`: macOS remembers where the item was ⌘-dragged, and when the bar
        //    is full it is the items further LEFT that go behind the « chevron.
        //    Drawn INSIDE the status item, the pill cost a whole core (measured 97-101 %): AppKit
        //    re-snapshots the button on every orb frame to copy it into the bar. So it stays a separate
        //    window, glued to the item's frame on every move.
        item = NSStatusBar.system.statusItem(withLength: W)
        item.autosaveName = "greymatter-pastille"
        item.button?.target = self; item.button?.action = #selector(basculerObjc)

        let racine = Cliquable(frame: NSRect(x: 0, y: 0, width: W, height: H))
        racine.clic = { [weak self] in self?.basculer() }
        racine.wantsLayer = true
        racine.addSubview(fondVerre(racine.bounds, rayon: H / 2))

        contenu = NSView(frame: racine.bounds)
        contenu.autoresizingMask = [.width, .height]
        contenu.wantsLayer = true
        contenu.layer!.cornerRadius = H / 2; contenu.layer!.masksToBounds = true
        // the light rim that holds the edge on a light background: inset 0 0 0 .5px rgba(255,255,255,.28)
        contenu.layer!.borderWidth = 0.5
        contenu.layer!.borderColor = NSColor(white: 1, alpha: 0.28).cgColor
        racine.addSubview(contenu)

        // The orb: a 20 pt disc, 3 pt from the edge, showing the centre of a 34 pt drawing.
        let mini = CALayer()
        mini.frame = CGRect(x: 3, y: 3, width: 20, height: 20)
        mini.cornerRadius = 10; mini.masksToBounds = true
        let echelle = NSScreen.screens.first?.backingScaleFactor ?? 2
        orbe = Orbe(cotePt: 34, echelle: echelle, depart: cible)
        orbe.couche.frame = CGRect(x: -7, y: -7, width: 34, height: 34)
        mini.addSublayer(orbe.couche)
        contenu.layer!.addSublayer(mini)

        texte.frame = NSRect(x: 30, y: 0, width: W - 30, height: H)
        texte.lineBreakMode = .byClipping
        contenu.addSubview(texte)

        fen = NSPanel(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                      styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        fen.isOpaque = false; fen.backgroundColor = .clear; fen.hasShadow = false
        fen.level = .screenSaver
        fen.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        fen.contentView = racine
        if let w = item.button?.window {
            NotificationCenter.default.addObserver(self, selector: #selector(poserObjc), name: NSWindow.didMoveNotification, object: w)
            NotificationCenter.default.addObserver(self, selector: #selector(poserObjc), name: NSWindow.didChangeOcclusionStateNotification, object: w)
        }
        panneau = Panneau(depart: cible)
        commencer(); auRepos()
        orbe.dessiner()
        poser()
        NotificationCenter.default.addObserver(self, selector: #selector(poserObjc), name: NSApplication.didChangeScreenParametersNotification, object: nil)
        // Safety net: the item's moves are followed by notification; this poll catches what it misses.
        Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.poser() }
        tic()
        Timer.scheduledTimer(withTimeInterval: 0.7, repeats: true) { [weak self] _ in self?.tic() }
        Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in self?.majCadence() }
        majCadence()
        // ── THE HEARTBEAT (ilot.js): hooks/auto_maintain.py takes a capsule that has not beaten for
        //    60 s for a zombie and restarts it. Between two runs the pill shows little, so the heartbeat
        //    proves that the loop runs, not that a window is visible.
        battement()
        Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.battement() }
        if let duree = ENV["BANC_DUREE"].flatMap(Double.init) { banc(duree) }
        // bench: panel opened on start (ilot.js, CAPSULE_ILOT_OUVRIR)
        if ENV["CAPSULE_ILOT_OUVRIR"] == "1" { DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [weak self] in self?.ouvrir() } }
    }

    func battement() {
        let ms = String(Int((Date().timeIntervalSince1970 * 1000).rounded()))
        try? ms.write(toFile: (TRONC as NSString).appendingPathComponent("state/capsule-alive"), atomically: true, encoding: .utf8)
    }

    // ── THE TEXT: name (800, tracking 0.8) + action (600, at 62 %) — ilot.html ──
    func attribue(_ nom: String, _ act: String, fini: Bool) -> NSAttributedString {
        let s = NSMutableAttributedString()
        let (r, g, b) = melangeOklab(cible.c1, 0.55, cible.c2)
        let couleurNom = fini ? NSColor.white : NSColor(srgbRed: r, green: g, blue: b, alpha: 1)
        let espace: CGFloat = fini ? 0 : 0.8
        s.append(NSAttributedString(string: nom, attributes: [
            .font: NSFont.systemFont(ofSize: 12, weight: .heavy), .foregroundColor: couleurNom, .kern: espace]))
        if !act.isEmpty {
            // margin-left: 5px — the space goes after the name's last letter
            if s.length > 0 { s.addAttribute(.kern, value: espace + 5, range: NSRange(location: s.length - 1, length: 1)) }
            s.append(NSAttributedString(string: act, attributes: [
                .font: NSFont.systemFont(ofSize: 12, weight: .semibold), .foregroundColor: NSColor(white: 1, alpha: 0.62)]))
        }
        return s
    }
    /// The width no longer follows the text (it made the neighbouring icons jump): it is the width of
    /// the longest possible label, measured once. 3 + 20 + 7 + text + 11, clamped to 60…240.
    func largeurFixe() -> CGFloat {
        var paires = VAISSEAUX.map { ($0.value, $0.key) }
        paires += [(TXT_FINI, ""), ("GreyMatter", TXT_REPOS)]
        let m = paires.map { attribue($0.0, $0.1, fini: false).size().width }.max() ?? 0
        return max(60, min(240, ceil(3 + 20 + 7 + m + 11)))
    }
    var texteVoulu = "", motsVoulus: String?, fondu = 0
    /// The text changes with a fade (ilot.html `.txt.efface`): out in 0.14 s moving down 2 pt,
    /// replaced, then back 40 ms later. A mere colour change does not go through the fade.
    func textePilule(_ nom: String, _ act: String, fini: Bool) {
        let mots = nom + "|" + act + "|" + (fini ? "1" : "0")
        let cle = mots + "\(cible.c1)\(cible.c2)"
        if cle == texteVoulu { return }
        texteVoulu = cle
        let poserTexte = { [weak self] in
            guard let s = self else { return }
            s.texte.attributedStringValue = s.attribue(nom, act, fini: fini)
            s.texte.sizeToFit()
            s.texte.frame.origin = NSPoint(x: 30, y: ((s.H - s.texte.frame.height) / 2).rounded())
        }
        let premier = motsVoulus == nil
        let memesMots = motsVoulus == mots
        motsVoulus = mots
        if premier || memesMots || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            fondu += 1; texte.alphaValue = 1; poserTexte(); return
        }
        fondu += 1
        let ce = fondu
        NSAnimationContext.runAnimationGroup({ c in
            c.duration = 0.14; c.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            texte.animator().alphaValue = 0
            texte.animator().setFrameOrigin(NSPoint(x: 30, y: texte.frame.origin.y - 2))
        }, completionHandler: { [weak self] in
            guard let s = self, s.fondu == ce else { return }
            poserTexte()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.04) {
                guard s.fondu == ce else { return }
                NSAnimationContext.runAnimationGroup { c in
                    c.duration = 0.14; c.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                    s.texte.animator().alphaValue = 1
                }
            }
        })
    }

    // ── PLACING the pill over its reserved slot ───────────────────────────────
    @objc func poserObjc() { poser() }
    func poser() {
        guard let w = item.button?.window, w.frame.width > 0 else { return }
        let t = w.frame
        // ONE FIXED PLACE: no narrower form near the notch. Changing width shifted every neighbouring
        // icon. macOS never puts an item under the notch: when the bar is full it moves items behind
        // «, and the remembered position decides which ones go.
        let cadre = NSRect(x: (t.midX - W / 2).rounded(), y: (t.midY - H / 2).rounded(), width: W, height: H)
        let montree = w.occlusionState.contains(.visible) && !derriereChevron(t)
        if fen.frame != cadre { fen.setFrame(cadre, display: false) }
        if montree != fen.isVisible { montree ? fen.orderFrontRegardless() : fen.orderOut(nil) }
        panneau.suivre(place: t)
    }
    @objc func basculerObjc() { basculer() }
    /// ── HIDDEN BY macOS? When the bar is full, macOS 27 moves the item behind «, "Show hidden menu
    ///    bar items". The app is not told: its frame, `isVisible` and `occlusionState` stay those of a
    ///    shown item (measured, shown and hidden side by side). The only trace: a hidden item sits
    ///    UNDER the « chevron, which a shown item never overlaps. The chevron is the only button of
    ///    MenuBarAgent's bar (the others are AXMenuBarItem), whatever the system language. Without
    ///    Accessibility access we cannot tell: we show, and the fixed place does the rest.
    func derriereChevron(_ t: NSRect) -> Bool {
        guard AXIsProcessTrusted(),
              let agent = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.MenuBarAgent").first
        else { return false }
        func attr(_ e: AXUIElement, _ a: String) -> AnyObject? {
            var r: AnyObject?; return AXUIElementCopyAttributeValue(e, a as CFString, &r) == .success ? r : nil
        }
        guard let barre = attr(AXUIElementCreateApplication(agent.processIdentifier), "AXExtrasMenuBar"),
              let enfants = attr(barre as! AXUIElement, "AXChildren") as? [AXUIElement] else { return false }
        for e in enfants where attr(e, "AXRole") as? String == "AXButton" {
            var p = CGPoint.zero, z = CGSize.zero
            guard let pv = attr(e, "AXPosition"), let zv = attr(e, "AXSize"),
                  AXValueGetValue(pv as! AXValue, .cgPoint, &p), AXValueGetValue(zv as! AXValue, .cgSize, &z) else { continue }
            if t.minX < p.x + z.width && p.x < t.maxX { return true }
        }
        return false
    }

    // ── THE PANEL (ilot.js basculerPanneau, ouvrirPanneau, fermerPanneau) ──
    /// Unfolded and persistent: only a click on the pill folds it back.
    func basculer() { panneau.visible ? fermer() : ouvrir() }
    func ouvrir() {
        guard !panneau.visible, let t = item.button?.window?.frame else { return }
        if let c = course { panneau.peindre(c) }
        panneau.ouvrir(place: t)
        contenu.layer!.backgroundColor = NSColor(white: 1, alpha: 0.12).cgColor
        lirePave(); majCadence()
    }
    func fermer() {
        guard panneau.visible else { return }
        panneau.fermer()
        contenu.layer!.backgroundColor = nil
    }
    /// The code block only makes sense while something works (orbe.html: `if (occupe) pave.vu`).
    func lirePave() {
        guard panneau.visible else { return }
        // lireFlux answers "the lines CHANGED", not "there are lines": passed to montrer, it hid
        // the block on the second tick of an unchanged diff (orbe.html shows it while busy).
        panneau.pave.lireFlux(dernierEtatOrbe)
        panneau.pave.montrer(occupe)
    }

    // ── THE CURRENT RUN (ilot.js: tic, commencer, auRepos) ───────────────────
    func commencer() { course = Course() }
    /// At rest: the pill stays, the panel folds, the last run is kept as one line.
    func auRepos() {
        fermer()
        var d = course?.dernier
        if let c = course, !c.stations.isEmpty { d = (c.stations.count, (c.fin ?? Date()).timeIntervalSince(c.t0)) }
        course = Course(fin: Date(), repos: true, dernier: d); peindre()
    }

    func tic() {
        let (etat, detail) = lireStatut()
        if etat != "idle" {
            attenteFin?.invalidate(); attenteFin = nil
            attenteEfface?.invalidate(); attenteEfface = nil
            if course == nil || course!.fin != nil { commencer() }
            let vaisseau = VAISSEAUX[etat] ?? "TORRENS"
            if let der = course!.stations.last, der.vaisseau == vaisseau { course!.stations[course!.stations.count - 1].etat = etat }
            else { course!.stations.append(Station(vaisseau: vaisseau, etat: etat)); if !PANNEAU_REPLIE { ouvrir() } }
            course!.detail = detail
            course!.theme = themeEnCours()
        } else if let c = course, c.fin == nil, attenteFin == nil {
            attenteFin = Timer.scheduledTimer(withTimeInterval: REPOS_AVANT_FIN, repeats: false) { [weak self] _ in
                guard let s = self, s.course != nil else { return }
                s.attenteFin = nil
                s.course!.fin = Date(); s.peindre()
                s.attenteEfface = Timer.scheduledTimer(withTimeInterval: TERMINE_VISIBLE, repeats: false) { [weak self] _ in self?.auRepos() }
            }
        }
        peindre()
    }

    func peindre() {
        guard let c = course else { return }
        let ici = c.stations.last, fini = c.fin != nil
        if c.repos { nouvelleCible("idle"); textePilule("GreyMatter", TXT_REPOS, fini: false) }
        else {
            nouvelleCible(fini ? "idle" : (ici?.etat ?? "working"))
            textePilule(fini ? TXT_FINI : (ici?.vaisseau ?? ""), fini ? "" : (ici?.etat ?? ""), fini: fini)
        }
        if panneau.visible { panneau.peindre(c) }
        // The orb follows THIS run (direOrbe + lire in orbe.html)
        let etatOrbe = (!fini && !c.repos) ? (ici?.etat ?? "working") : "idle"
        occupe = etatOrbe != "idle"
        if etatOrbe != dernierEtatOrbe {
            dernierEtatOrbe = etatOrbe
            if !reduit { let m = reglage(etatOrbe).meca; orbe.setMecanique(m); panneau.orbe.setMecanique(m) }
            majCadence()
        }
        lirePave()
    }

    /// The target colours and material; the glide runs at 30 Hz until it arrives, then stops.
    func nouvelleCible(_ etat: String) {
        let r = reglage(etat)
        if r == cible && glisseur != nil { return }
        cible = r
        if cibleAtteinte == r { return }
        glisseur?.invalidate()
        glisseur = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] m in
            guard let s = self else { return }
            let a = s.orbe.approcher(s.cible), b = s.panneau.orbe.approcher(s.cible)
            if a && b { s.cibleAtteinte = s.cible; m.invalidate(); s.glisseur = nil }
        }
    }

    func majCadence() {
        regler(orbe, fen.contentView!)
        // A folded panel draws for nobody: zero frames (orbe.html kept it at 1 fps).
        if panneau.visible { regler(panneau.orbe, panneau.fen.contentView!) } else { panneau.orbe.arreter() }
    }
    private func regler(_ o: Orbe, _ v: NSView) {
        if o.enTransition { o.tempo = 1; o.setCadence(CADENCE.transition, vue: v); return }
        o.tempo = occupe ? 1 : TEMPO_REPOS
        o.setCadence(occupe ? CADENCE.travail : CADENCE.repos, vue: v)
    }

    // ── BENCH: the same measurement as banc/conso.cjs, for this process ───────
    func banc(_ duree: Double) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            let c0 = cpu(), i0 = self.orbe.images, j0 = self.panneau.orbe.images, t0 = CACurrentMediaTime()
            DispatchQueue.main.asyncAfter(deadline: .now() + duree) {
                let dt = CACurrentMediaTime() - t0
                print(String(format: "{\"natif\":true,\"cadence_demandee\":%@,\"etat\":\"%@\",\"images_par_s\":%.1f,\"pastille_pct_coeur\":%.1f,\"memoire_mo\":%.0f,\"panneau_ouvert\":%@,\"panneau_images_par_s\":%.1f}",
                             IMPOSEE.map { String($0) } ?? "null", self.dernierEtatOrbe,
                             Double(self.orbe.images - i0) / dt, 100 * (cpu() - c0) / dt, memoireMo(),
                             self.panneau.visible ? "true" : "false", Double(self.panneau.orbe.images - j0) / dt))
                exit(0)
            }
        }
    }
}

let args = CommandLine.arguments
if args.count >= 2 && args[1] == "--check" {
    // The binary answers, and says what it would show — tests/capsule_runtime.py reads this line.
    let (etat, detail) = lireStatut()
    let o: [String: Any] = ["trunk": TRONC, "state": etat, "detail": detail,
                            "liveness_s": FRAICHEUR.vie, "activity_s": FRAICHEUR.activite]
    let d = try! JSONSerialization.data(withJSONObject: o, options: [.sortedKeys])
    print(String(data: d, encoding: .utf8)!)
    exit(0)
}
if args.count >= 4 && args[1] == "--image" {
    // The orb alone, off screen, 4× larger than in the pill, after a 1.5 s fade into the state.
    let r = reglage(args[2])
    let o = Orbe(cotePt: 136, echelle: 2, depart: r)
    o.setMecanique(r.meca)
    guard let img = o.instantane(avance: 1.5),
          let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: args[3]) as CFURL, "public.png" as CFString, 1, nil)
    else { print("render failed"); exit(1) }
    CGImageDestinationAddImage(dest, img, nil); CGImageDestinationFinalize(dest)
    print("written:", args[3]); exit(0)
}

/// Bench: the panel alone, placed at (x, y) with a simulated run, to be captured
/// at the same spot as a reference.
final class DemoPanneau: NSObject, NSApplicationDelegate {
    let scenario: String, x: CGFloat, y: CGFloat, duree: Double
    var p: Panneau!
    init(_ s: String, _ x: CGFloat, _ y: CGFloat, _ d: Double) { scenario = s; self.x = x; self.y = y; duree = d }
    func course() -> Course {
        let t = Date()
        let st = [Station(vaisseau: "NARCISSUS", etat: "gardening"), Station(vaisseau: "TORRENS", etat: "working")]
        var c = Course(t0: t.addingTimeInterval(-83), stations: scenario == "un" ? [st[0]] : st, detail: "project-tree-format")
        if scenario == "fini" { c.fin = t.addingTimeInterval(-1) }
        if scenario == "repos" { c = Course(fin: t, repos: true, dernier: (2, 83)) }
        return c
    }
    func applicationDidFinishLaunching(_ n: Notification) {
        let c = course()
        let etat = (c.fin == nil) ? (c.stations.last?.etat ?? "idle") : "idle"
        let r = reglage(etat)
        p = Panneau(depart: r)
        p.poseImposee = CGPoint(x: x, y: y)
        p.orbe.setMecanique(r.meca)
        p.peindre(c)
        p.ouvrir(place: .zero)
        p.orbe.tempo = etat == "idle" ? TEMPO_REPOS : 1
        p.orbe.setCadence(etat == "idle" ? CADENCE.repos : CADENCE.travail, vue: p.fen.contentView!)
        if etat != "idle" { p.pave.lireFlux(etat); p.pave.montrer(true) }
        Timer.scheduledTimer(withTimeInterval: 0.7, repeats: true) { [weak self] _ in guard let s = self else { return }; s.p.peindre(s.course()) }
        print("ready", p.fen.frame)
        DispatchQueue.main.asyncAfter(deadline: .now() + duree) { exit(0) }
    }
}

let app = NSApplication.shared
// `--panneau-demo` is the French trunk's spelling, kept so its benches still drive this build.
if args.count >= 5 && ["--panel-demo", "--panneau-demo"].contains(args[1]) {
    app.setActivationPolicy(.accessory)
    let d = DemoPanneau(args[2], CGFloat(Double(args[3]) ?? 600), CGFloat(Double(args[4]) ?? 300), args.count > 5 ? Double(args[5]) ?? 8 : 8)
    app.delegate = d
    app.run()
}
// ⚠ ONE PILL ONLY (ilot.js, requestSingleInstanceLock): two pills once sat side by side.
//   A kernel lock on a file: it drops by itself when the process dies, even when killed.
//   Benches (BANC_DUREE, CAPSULE_STATUT_HOME) run next to the real pill and are exempt.
if ENV["BANC_DUREE"] == nil && ENV["CAPSULE_STATUT_HOME"] == nil {
    let verrou = open((TRONC as NSString).appendingPathComponent("state/capsule-natif.lock"), O_CREAT | O_RDWR, 0o644)
    if verrou >= 0 && flock(verrou, LOCK_EX | LOCK_NB) != 0 { exit(0) }
}
app.setActivationPolicy(.accessory)
let delegue = Pastille()
app.delegate = delegue
app.run()
