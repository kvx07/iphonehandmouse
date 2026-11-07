import Foundation
import Network
import CoreGraphics
import ApplicationServices

func log(_ s: String) { print(s); fflush(stdout) }

var lastX: CGFloat = -1, lastY: CGFloat = -1
func currentPoint() -> CGPoint {
    if lastX >= 0 { return CGPoint(x: lastX, y: lastY) }
    let p = CGEvent(source: nil)?.location ?? .zero
    lastX = p.x; lastY = p.y
    return p
}
func post(_ t: CGEventType, _ p: CGPoint) {
    CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .left)?
        .post(tap: .cghidEventTap)
}
func displayBounds() -> CGRect { CGDisplayBounds(CGMainDisplayID()) }

func moveBy(_ dx: CGFloat, _ dy: CGFloat) {
    guard abs(dx) > 0.005 || abs(dy) > 0.005 else { return }
    let cap: CGFloat = 90
    let mdx = min(max(dx, -cap), cap)
    let mdy = min(max(dy, -cap), cap)
    let p = currentPoint()
    let b = displayBounds()
    var np = CGPoint(x: p.x + mdx, y: p.y + mdy)
    np.x = min(max(np.x, b.minX + 1), b.maxX - 2)
    np.y = min(max(np.y, b.minY + 1), b.maxY - 2)
    CGWarpMouseCursorPosition(np)
    CGAssociateMouseAndMouseCursorPosition(1)
    post(.mouseMoved, np)
    lastX = np.x; lastY = np.y
}
func click(_ button: CGMouseButton) {
    let p = currentPoint()
    post(button == .left ? .leftMouseDown : .rightMouseDown, p)
    usleep(12000)
    post(button == .left ? .leftMouseUp : .rightMouseUp, p)
}
func warpTo(_ x: CGFloat, _ y: CGFloat) {
    let b = displayBounds()
    let p = CGPoint(x: min(max(x, b.minX + 1), b.maxX - 2),
                    y: min(max(y, b.minY + 1), b.maxY - 2))
    let cur = CGEvent(source: nil)?.location ?? currentPoint()
    guard abs(p.x - cur.x) > 0.12 || abs(p.y - cur.y) > 0.12 else { return }
    if let e = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
                       mouseCursorPosition: p, mouseButton: .left) {
        e.setIntegerValueField(.mouseEventDeltaX, value: Int64((p.x - cur.x).rounded()))
        e.setIntegerValueField(.mouseEventDeltaY, value: Int64((p.y - cur.y).rounded()))
        e.post(tap: .cghidEventTap)
    }
    lastX = p.x; lastY = p.y
}

func scroll(_ dy: Int32) {
    CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1,
            wheel1: dy, wheel2: 0, wheel3: 0)?.post(tap: .cghidEventTap)
}

final class Client {
    let c: NWConnection
    var buf = Data()
    var closed = false
    init(_ conn: NWConnection) {
        c = conn
        c.stateUpdateHandler = { [weak self] st in
            log("conn state \(st)")
            if case .ready = st {
                let b = displayBounds()
                let msg = "{\"screen\":[\"\(Int(b.minX))\",\"\(Int(b.minY))\",\"\(Int(b.width))\",\"\(Int(b.height))\"]}\n"
                self?.c.send(content: Data(msg.utf8), completion: .contentProcessed { _ in })
            }
            if case .failed(let e) = st { log("client failed \(e)"); self?.kill() }
            if case .cancelled = st { self?.kill() }
        }
        c.start(queue: .global(qos: .userInteractive))
        read()
    }
    func kill() { if !closed { closed = true; c.cancel() } }
    func read() {
        c.receive(minimumIncompleteLength: 1, maximumLength: 1 << 16) { [weak self] data, _, done, err in
            guard let self else { return }
            if let d = data, !d.isEmpty { self.buf.append(d); self.drain() }
            if done || err != nil { self.kill(); return }
            if !self.closed { self.read() }
        }
    }
    func drain() {
        log("drain buf=\(buf.count)")
        while let nl = buf.firstIndex(of: 0x0A) {
            let line = buf[buf.startIndex..<nl]
            buf.removeSubrange(buf.startIndex...nl)
            guard !line.isEmpty,
                  let obj = try? JSONSerialization.jsonObject(with: Data(line)) as? [String: Any] else { continue }
            if let dx = obj["dx"] as? Double, let dy = obj["dy"] as? Double {
                log("move dx=\(dx) dy=\(dy)")
                moveBy(CGFloat(dx), CGFloat(dy))
            }
            if let arr = obj["abs"] as? [Double], arr.count == 2 {
                warpTo(CGFloat(arr[0]), CGFloat(arr[1]))
            }
            if let cmd = obj["cmd"] as? String {
                switch cmd {
                case "click": click(.left)
                case "rclick": click(.right)
                case "scroll": if let v = obj["v"] as? Double { scroll(Int32(v)) }
                case "sync": let p = CGEvent(source: nil)?.location ?? .zero; lastX = p.x; lastY = p.y
                default: break
                }
            }
        }
    }
}

let tcpOpts = NWProtocolTCP.Options()
tcpOpts.noDelay = true
tcpOpts.connectionTimeout = 2
let params = NWParameters(tls: nil, tcp: tcpOpts)
params.allowLocalEndpointReuse = true
params.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: 9000)
let listener = try! NWListener(using: params)
var clients: [Client] = []
listener.newConnectionHandler = { conn in
    let cl = Client(conn)
    clients.append(cl)
    log("clients=\(clients.count)")
}
listener.stateUpdateHandler = { st in
    if case .ready = st { log("pointerd ready on 127.0.0.1:9000") }
    if case .failed(let e) = st { log("pointerd failed \(e)"); exit(1) }
}
listener.start(queue: .main)
let trusted = AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary)
log("Accessibility trusted: \(trusted)")
dispatchMain()
