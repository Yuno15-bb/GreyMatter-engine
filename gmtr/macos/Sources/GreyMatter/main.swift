// GreyMatter.app — the GMTR map on the desktop, in native macOS windows.
//
// WHAT IT REPRODUCES. The author's desktop app of 24/09 (an Electron shell,
// dropped on 27/09: 12.5 % of a core for an EMPTY page at 30 fps, measured for
// the capsule). Its layout is kept exactly, only the shell changes:
//   A — the START SQUARE: a borderless 320 x 160 glass plate, the boot intro
//       then the access code, over the trunk page "/";
//   B — the MAP: a fixed 1028 x 673 glass window, centred for real, opened
//       only once access is granted (the intro ends on location = '/carte/').
// Both share WebKit's default data store, so the cookie set by the code in A
// is valid in B. Each window lays its own costume (carre.css, carte.css) over
// the page at load: the served pages stay intact for a browser.
//
// The app starts the map server (gmtr/launch.sh, which asks for the access
// code on first launch) and stops it when it quits. Where the engine lives is
// written into Info.plist by install.sh (GMTRLaunch, GMTRPort): the binary
// carries no user path.

import AppKit
import WebKit

let info = Bundle.main.infoDictionary ?? [:]
let launchScript = info["GMTRLaunch"] as? String ?? ""
let port = info["GMTRPort"] as? String ?? "8767"
let base = URL(string: "http://127.0.0.1:\(port)/")!
let env = ProcessInfo.processInfo.environment
let costumes = URL(fileURLWithPath: launchScript).deletingLastPathComponent().appendingPathComponent("macos")

// Geometry of the 24/09 app, in points.
let squareSize = NSSize(width: 320, height: 160)
let mapSize = NSSize(width: 1028, height: 673)   // ONE size, not resizable: measured on the author's capture

// Test mode (see the test hook below): windows stay invisible on the user's screen.
let testing = env["GREYMATTER_SNAPSHOT"] != nil

/// A strip the user can drag the window by. The web view swallows every mouse
/// event, so the page's -webkit-app-region (an Electron-only property) does
/// nothing here: native strips carry that job instead.
final class DragStrip: NSView {
    override var mouseDownCanMoveWindow: Bool { true }
    override func mouseDown(with e: NSEvent) { window?.performDrag(with: e) }
}

/// The glass material behind a transparent web view: macOS's own blur.
func glass(_ frame: NSRect, radius: CGFloat) -> NSVisualEffectView {
    let v = NSVisualEffectView(frame: frame)
    v.material = .hudWindow
    v.blendingMode = .behindWindow
    v.state = .active
    v.autoresizingMask = [.width, .height]
    if radius > 0 { v.wantsLayer = true; v.layer?.cornerRadius = radius; v.layer?.masksToBounds = true }
    return v
}

/// Lays a costume over the page and names the shell, as the 24/09 app did:
/// the stylesheet first, then data-app (the intro re-reads its variables
/// when data-app changes).
func costumed(_ file: String, app: String) -> WKWebViewConfiguration {
    let css = (try? String(contentsOf: costumes.appendingPathComponent(file), encoding: .utf8)) ?? ""
    let data = try! JSONSerialization.data(withJSONObject: [css], options: [])
    let literal = String(decoding: data, as: UTF8.self)   // ["..."]: a safe JS string
    let js = """
        (() => { const s = document.createElement('style'); s.textContent = \(literal)[0];
          document.head.appendChild(s); document.documentElement.dataset.app = '\(app)'; })();
        """
    let conf = WKWebViewConfiguration()
    conf.websiteDataStore = .default()      // one cookie jar for both windows
    conf.userContentController.addUserScript(
        WKUserScript(source: js, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
    return conf
}

func transparentWeb(_ frame: NSRect, _ conf: WKWebViewConfiguration) -> WKWebView {
    let w = WKWebView(frame: frame, configuration: conf)
    w.autoresizingMask = [.width, .height]
    w.setValue(false, forKey: "drawsBackground")
    w.underPageBackgroundColor = .clear
    return w
}

final class App: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var square: NSWindow?
    var squareWeb: WKWebView?
    var map: NSWindow?
    var mapWeb: WKWebView?
    var server: Process?
    var serverLog = Data()
    var deadline = Date()

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenu()
        if !testing { NSApp.activate(ignoringOtherApps: true) }
        // A second double-click while the map is already served (by this app or
        // by launch.sh from a terminal) must show it, not start a second server
        // that would fail on the busy port.
        answers { up in
            if up { self.openSquare() } else { self.startServer() }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ note: Notification) {
        guard let s = server, s.isRunning else { return }
        s.terminate()
        s.waitUntilExit()
    }

    // MARK: A — the start square

    func openSquare() {
        let area = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        // Centred across, a little above the middle: 1/2.4 of the free height from the top.
        let origin = NSPoint(x: (area.minX + (area.width - squareSize.width) / 2).rounded(),
                             y: (area.maxY - (area.height - squareSize.height) / 2.4 - squareSize.height).rounded())
        let w = NSWindow(contentRect: NSRect(origin: origin, size: squareSize),
                         styleMask: [.borderless], backing: .buffered, defer: false)
        w.isOpaque = false
        w.backgroundColor = .clear
        w.hasShadow = true                  // macOS draws it from the alpha: it follows the rounded corners
        w.isReleasedWhenClosed = false
        let bounds = NSRect(origin: .zero, size: squareSize)
        let root = glass(bounds, radius: 12)
        let web = transparentWeb(bounds, costumed("carre.css", app: "carre"))
        web.navigationDelegate = self
        web.uiDelegate = self
        root.addSubview(web)
        // The whole plate moves the window, as in the 24/09 app; keys still
        // reach the page, which keeps its own code field focused.
        let strip = DragStrip(frame: bounds); strip.autoresizingMask = [.width, .height]
        root.addSubview(strip)
        w.contentView = root
        if testing { w.alphaValue = 0; w.ignoresMouseEvents = true }
        w.makeKeyAndOrderFront(nil)
        w.makeFirstResponder(web)
        square = w; squareWeb = web
        NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: w, queue: .main) { [weak self] _ in
            self?.square = nil; self?.squareWeb = nil
        }
        web.load(URLRequest(url: base))
    }

    // MARK: B — the map

    func openMap() {
        guard map == nil else { return }
        let area = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let size = NSSize(width: min(mapSize.width, area.width), height: min(mapSize.height, area.height))
        // Centred FOR REAL: the empty band above equals the one below.
        let origin = NSPoint(x: (area.minX + (area.width - size.width) / 2).rounded(),
                             y: (area.minY + (area.height - size.height) / 2).rounded())
        let w = NSWindow(contentRect: NSRect(origin: origin, size: size),
                         styleMask: [.titled, .closable, .miniaturizable, .fullSizeContentView],
                         backing: .buffered, defer: false)
        w.title = "GreyMatter"
        w.titlebarAppearsTransparent = true
        w.titleVisibility = .hidden
        w.tabbingMode = .disallowed
        w.collectionBehavior.insert(.fullScreenNone)
        w.isOpaque = false
        w.backgroundColor = .clear
        w.isReleasedWhenClosed = false
        let bounds = NSRect(origin: .zero, size: size)
        let root = glass(bounds, radius: 0)
        let web = transparentWeb(bounds, costumed("carte.css", app: "carte"))
        web.navigationDelegate = self
        web.uiDelegate = self
        root.addSubview(web)
        // The band above the map's header drags the window (the page's header
        // starts 40 pt down, so no control sits under this strip).
        let strip = DragStrip(frame: NSRect(x: 0, y: size.height - 36, width: size.width, height: 36))
        strip.autoresizingMask = [.width, .minYMargin]
        root.addSubview(strip)
        w.contentView = root
        if testing { w.alphaValue = 0; w.ignoresMouseEvents = true }
        map = w; mapWeb = web
        NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: w, queue: .main) { [weak self] _ in
            self?.map = nil; self?.mapWeb = nil
        }
        // Shown only once drawn (didFinish), then the square goes.
        web.load(URLRequest(url: base.appendingPathComponent("carte/")))
    }

    func buildMenu() {
        let bar = NSMenu()
        func menu(_ title: String, _ items: [NSMenuItem]) {
            let top = NSMenuItem(); let m = NSMenu(title: title)
            items.forEach(m.addItem); top.submenu = m; bar.addItem(top)
        }
        menu("GreyMatter", [
            NSMenuItem(title: "Hide GreyMatter", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h"),
            .separator(),
            NSMenuItem(title: "Quit GreyMatter", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"),
        ])
        // Edit carries the shortcuts: without it, ⌘V into the access-code field does nothing.
        menu("Edit", [
            NSMenuItem(title: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x"),
            NSMenuItem(title: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c"),
            NSMenuItem(title: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v"),
            NSMenuItem(title: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a"),
        ])
        menu("View", [NSMenuItem(title: "Reload Map", action: #selector(reload), keyEquivalent: "r")])
        menu("Window", [
            NSMenuItem(title: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m"),
            NSMenuItem(title: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w"),
        ])
        NSApp.mainMenu = bar
    }

    @objc func reload() { (mapWeb ?? squareWeb)?.reload() }

    // MARK: server

    func answers(_ done: @escaping (Bool) -> Void) {
        var req = URLRequest(url: base); req.timeoutInterval = 1
        URLSession.shared.dataTask(with: req) { _, resp, _ in
            DispatchQueue.main.async { done(resp != nil) }
        }.resume()
    }

    func startServer() {
        guard FileManager.default.isExecutableFile(atPath: launchScript) else {
            return fail("The map launcher is missing:\n\(launchScript)\n\nRe-run the GreyMatter installer.")
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [launchScript, port]
        var e = env
        // A Finder-launched app gets a minimal PATH: python3 has to be findable.
        e["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        e["GMTR_NO_BROWSER"] = "1"           // these windows ARE the browser
        p.environment = e
        let pipe = Pipe()
        p.standardOutput = pipe; p.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            DispatchQueue.main.async { self?.serverLog.append(d) }
        }
        p.terminationHandler = { [weak self] proc in
            DispatchQueue.main.async { self?.serverEnded(proc.terminationStatus) }
        }
        do { try p.run() } catch { return fail("Could not start the map server: \(error.localizedDescription)") }
        server = p
        // The trunk export runs before the server listens: seconds on a small
        // trunk, longer on a big one. Past two minutes something is wrong.
        deadline = Date().addingTimeInterval(120)
        poll()
    }

    func poll() {
        answers { up in
            if up { return self.openSquare() }
            guard self.server?.isRunning == true else { return }
            if Date() > self.deadline { return self.fail("The map server did not answer.\n\n" + self.tail()) }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.poll() }
        }
    }

    func serverEnded(_ status: Int32) {
        guard square == nil && map == nil else {  // served, then stopped under us
            return fail("The map server stopped (exit \(status)).\n\n" + tail())
        }
        // launch.sh exits 0 when the user cancels the access-code dialog.
        if status == 0 { NSApp.terminate(nil) } else { fail("The map could not start.\n\n" + tail()) }
    }

    func tail() -> String {
        let s = String(decoding: serverLog, as: UTF8.self)
        return s.split(separator: "\n").suffix(6).joined(separator: "\n")
    }

    func fail(_ text: String) {
        let a = NSAlert()
        a.messageText = "GreyMatter"
        a.informativeText = text
        a.alertStyle = .warning
        a.runModal()
        NSApp.terminate(nil)
    }

    // MARK: web

    func webView(_ w: WKWebView, didFinish nav: WKNavigation!) {
        if w === mapWeb, let m = map {
            if !m.isVisible {
                m.makeKeyAndOrderFront(nil)
                square?.close()                  // the square goes AFTER the map is up
            }
            if let shot = env["GREYMATTER_SNAPSHOT"] { snapshot(w, to: shot) }
        } else if w === squareWeb, testing {
            unlockForTest(w)
        }
    }

    func webView(_ w: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.allow) }
        // The intro ends with location = '/carte/': the map opens in ITS window.
        if w === squareWeb, url.host == "127.0.0.1", url.path.hasPrefix("/carte") {
            openMap()
            return decisionHandler(.cancel)
        }
        // Links that leave the map (a note's source, a doc) open in the user's browser.
        if url.host != "127.0.0.1", url.scheme?.hasPrefix("http") == true {
            NSWorkspace.shared.open(url)
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures f: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    // MARK: test hook
    //
    // A test cannot look at windows on the user's screen without stealing it.
    // GREYMATTER_SNAPSHOT=<file.png> keeps both windows invisible (alpha 0),
    // writes the square once its code field shows as <file>-square.png, types
    // GREYMATTER_TEST_CODE the way a user would, writes the map as <file>.png,
    // then quits, which also proves the server stops. The glass is the
    // window's material, not the page's: a snapshot shows the page over
    // transparency.

    func unlockForTest(_ w: WKWebView) {
        let js = """
            await new Promise(r => { const t = setInterval(() => { const c = document.getElementById('code');
              if (c && c.offsetParent) { clearInterval(t); r(); } }, 200); });
            await new Promise(r => setTimeout(r, 800));
            """
        w.callAsyncJavaScript(js, arguments: [:], in: nil, in: .page) { _ in
            let path = (env["GREYMATTER_SNAPSHOT"]! as NSString).deletingPathExtension + "-square.png"
            self.write(w, to: path) {
                guard let code = env["GREYMATTER_TEST_CODE"] else { return }
                w.callAsyncJavaScript("""
                    const c = document.getElementById('code'); c.value = code;
                    c.dispatchEvent(new Event('input'));
                    c.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}));
                    """, arguments: ["code": code], in: nil, in: .page) { _ in }
            }
        }
    }

    func snapshot(_ w: WKWebView, to path: String) {
        // The map settles for a few seconds before it is worth looking at.
        let wait = Double(env["GREYMATTER_SNAPSHOT_AFTER"] ?? "") ?? 12
        DispatchQueue.main.asyncAfter(deadline: .now() + wait) {
            self.write(w, to: path) { NSApp.terminate(nil) }
        }
    }

    func write(_ w: WKWebView, to path: String, then: @escaping () -> Void) {
        w.takeSnapshot(with: nil) { img, _ in
            if let img, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff) {
                try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
            }
            then()
        }
    }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(testing ? .accessory : .regular)
// A plain `kill` (or a logout script) must stop the server too, not orphan it
// on the port: route SIGTERM through the normal quit.
signal(SIGTERM, SIG_IGN)
let term = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
term.setEventHandler { NSApp.terminate(nil) }
term.resume()
app.run()
