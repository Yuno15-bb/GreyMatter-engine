// GreyMatter.app — the GMTR map in a native window.
//
// WHY NATIVE. The map used to open in the default browser: one more tab among
// forty, a lock screen that looked like any web page, and nothing in the Dock to
// say the server was running. Electron was never an option for it — 12.5 % of a
// core for an EMPTY page at 30 fps, measured on 2026-09-27 for the capsule. This
// app is the system's own WebKit in a plain AppKit window: it starts the map
// server (gmtr/launch.sh, which also asks for the access code on first launch),
// shows the map once the server answers, and stops the server when it quits.
//
// Where the engine lives is written into Info.plist by install.sh (GMTRLaunch,
// GMTRPort), so the binary itself carries no user path.

import AppKit
import WebKit

let info = Bundle.main.infoDictionary ?? [:]
let launchScript = info["GMTRLaunch"] as? String ?? ""
let port = info["GMTRPort"] as? String ?? "8767"
let home = URL(string: "http://127.0.0.1:\(port)/")!
let env = ProcessInfo.processInfo.environment

final class App: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var waitLabel: NSTextField!
    var server: Process?
    var serverLog = Data()
    var deadline = Date()

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenu()
        buildWindow()
        NSApp.activate(ignoringOtherApps: true)
        // A second double-click while the map is already served (by this app or
        // by launch.sh from a terminal) must show it, not start a second server
        // that would fail on the busy port.
        answers { up in
            if up { self.showMap() } else { self.startServer() }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ note: Notification) {
        guard let s = server, s.isRunning else { return }
        s.terminate()
        s.waitUntilExit()
    }

    // MARK: window

    func buildWindow() {
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let size = NSSize(width: min(1440, screen.width * 0.9), height: min(900, screen.height * 0.9))
        window = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.title = "GreyMatter"
        // The map runs under the title bar: content first, the bar floats on it.
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.tabbingMode = .disallowed
        window.backgroundColor = NSColor(red: 7/255, green: 7/255, blue: 11/255, alpha: 1)
        window.minSize = NSSize(width: 440, height: 480)
        window.center()
        window.setFrameAutosaveName("GreyMatterMap")

        let conf = WKWebViewConfiguration()
        conf.websiteDataStore = .default()   // the access-code cookie survives a relaunch
        web = WKWebView(frame: window.contentView!.bounds, configuration: conf)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        web.uiDelegate = self
        web.underPageBackgroundColor = window.backgroundColor
        web.setValue(false, forKey: "drawsBackground")
        web.isHidden = true
        window.contentView!.addSubview(web)

        waitLabel = NSTextField(labelWithString: "Opening your map…")
        waitLabel.textColor = NSColor(white: 1, alpha: 0.55)
        waitLabel.font = .systemFont(ofSize: 13)
        waitLabel.sizeToFit()
        waitLabel.frame.origin = NSPoint(x: (size.width - waitLabel.frame.width) / 2, y: size.height / 2)
        waitLabel.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        window.contentView!.addSubview(waitLabel)
        window.makeKeyAndOrderFront(nil)
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
        menu("View", [
            NSMenuItem(title: "Reload Map", action: #selector(reload), keyEquivalent: "r"),
            NSMenuItem(title: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f"),
        ])
        bar.items.last!.submenu!.items.last!.keyEquivalentModifierMask = [.command, .control]
        menu("Window", [
            NSMenuItem(title: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m"),
            NSMenuItem(title: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w"),
        ])
        NSApp.mainMenu = bar
    }

    @objc func reload() { web.reload() }

    // MARK: server

    func answers(_ done: @escaping (Bool) -> Void) {
        var req = URLRequest(url: home); req.timeoutInterval = 1
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
        var env = ProcessInfo.processInfo.environment
        // A Finder-launched app gets a minimal PATH: python3 has to be findable.
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        env["GMTR_NO_BROWSER"] = "1"         // this window IS the browser
        p.environment = env
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
            if up { return self.showMap() }
            guard self.server?.isRunning == true else { return }
            if Date() > self.deadline { return self.fail("The map server did not answer.\n\n" + self.tail()) }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.poll() }
        }
    }

    func serverEnded(_ status: Int32) {
        guard web.isHidden else {                // served, then stopped under us
            return fail("The map server stopped (exit \(status)).\n\n" + tail())
        }
        // launch.sh exits 0 when the user cancels the access-code dialog.
        if status == 0 { NSApp.terminate(nil) } else { fail("The map could not start.\n\n" + tail()) }
    }

    func tail() -> String {
        let s = String(decoding: serverLog, as: UTF8.self)
        return s.split(separator: "\n").suffix(6).joined(separator: "\n")
    }

    func showMap() {
        guard web.isHidden else { return }
        web.load(URLRequest(url: home))
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
        w.isHidden = false
        waitLabel.isHidden = true
        if let shot = env["GREYMATTER_SNAPSHOT"] { snapshot(w, to: shot) }
    }

    // TEST HOOK. A test cannot look at a window on the user's screen without
    // stealing it, so GREYMATTER_SNAPSHOT=<file.png> makes the app write what
    // this window draws, then quit (which also proves the server stops).
    // GREYMATTER_TEST_CODE unlocks first, the way a user typing the code would.
    var snapping = false
    func snapshot(_ w: WKWebView, to path: String) {
        guard !snapping else { return }
        snapping = true
        let after = Double(env["GREYMATTER_SNAPSHOT_AFTER"] ?? "") ?? 12
        let shoot = {
            DispatchQueue.main.asyncAfter(deadline: .now() + after) {
                w.takeSnapshot(with: nil) { img, _ in
                    if let img, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff) {
                        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
                    }
                    NSApp.terminate(nil)
                }
            }
        }
        guard let code = env["GREYMATTER_TEST_CODE"] else { return shoot() }
        // Wait for the lock field after the boot intro, then type and press Enter.
        let js = """
            await new Promise(r => { const t = setInterval(() => { const c = document.getElementById('code');
              if (c && c.offsetParent) { clearInterval(t); r(); } }, 200); });
            const c = document.getElementById('code'); c.value = code;
            c.dispatchEvent(new Event('input'));
            c.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}));
            """
        w.callAsyncJavaScript(js, arguments: ["code": code], in: nil, in: .page) { _ in shoot() }
    }

    // Links that leave the map (a note's source on GitHub, a doc) open in the
    // user's browser; the map itself stays in this window.
    func webView(_ w: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, url.host != "127.0.0.1", url.scheme?.hasPrefix("http") == true {
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
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.regular)
// A plain `kill` (or a logout script) must stop the server too, not orphan it
// on the port: route SIGTERM through the normal quit.
signal(SIGTERM, SIG_IGN)
let term = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
term.setEventHandler { NSApp.terminate(nil) }
term.resume()
app.run()
