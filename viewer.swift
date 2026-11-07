import Cocoa
import WebKit

let base = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    .appendingPathComponent("web/index.html")
let URL_STR = CommandLine.arguments.count > 1 ? CommandLine.arguments[1]
    : base.absoluteString + "?mirror=1&plain=1"

final class Trust: NSObject, WKNavigationDelegate {
    func webView(_ webView: WKWebView,
                 didReceive challenge: URLAuthenticationChallenge,
                 completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        if let trust = challenge.protectionSpace.serverTrust {
            completionHandler(.useCredential, URLCredential(trust: trust))
        } else {
            completionHandler(.performDefaultHandling, nil)
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)

let W: CGFloat = 430, H: CGFloat = 920
let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                   styleMask: [.titled, .closable, .resizable, .miniaturizable],
                   backing: .buffered, defer: false)
win.title = "iPhoneHandMouse 演示"
win.backgroundColor = .black
win.appearance = NSAppearance(named: .darkAqua)

let cfg = WKWebViewConfiguration()
cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
let wv = WKWebView(frame: win.contentView!.bounds, configuration: cfg)
wv.autoresizingMask = [.width, .height]
wv.setValue(false, forKey: "drawsBackground")
let trust = Trust()
wv.navigationDelegate = trust
win.contentView!.addSubview(wv)

if let url = URL(string: URL_STR) {
    if url.isFileURL {
        wv.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
    } else {
        wv.load(URLRequest(url: url))
    }
}

win.center()
win.makeKeyAndOrderFront(nil)
NSApp.activate(ignoringOtherApps: true)

// ESC 关闭
NSEvent.addLocalMonitorForEvents(matching: .keyDown) { e in
    if e.keyCode == 53 { NSApp.terminate(nil); return nil }
    return e
}

app.run()
