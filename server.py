#!/usr/bin/env python3
import base64, hashlib, json, os, socket, ssl, sys, threading, time, plistlib

BASE = os.path.dirname(os.path.abspath(__file__))
PORT_TLS, PORT_HTTP, PORT_PTR = 8443, 8080, 9000
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_ptr = None
_ptr_lock = threading.Lock()
clients = set()
screen = None          # [x0, y0, w, h] as reported by pointerd
last_pos = [0.0, 0.0]

def ptr_reader(sock):
    global screen
    buf = b""
    try:
        while True:
            d = sock.recv(4096)
            if not d: break
            buf += d
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip(): continue
                try: obj = json.loads(line)
                except Exception: continue
                if "screen" in obj:
                    screen = [float(v) for v in obj["screen"]]
                    print(f"[screen] {screen}", flush=True)
    except Exception:
        pass

def ptr_send(obj):
    global _ptr
    line = (json.dumps(obj) + "\n").encode()
    with _ptr_lock:
        for _ in range(2):
            try:
                if _ptr is None:
                    _ptr = socket.create_connection(("127.0.0.1", PORT_PTR), timeout=2)
                    _ptr.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    _ptr.settimeout(None)
                    threading.Thread(target=ptr_reader, args=(_ptr,), daemon=True).start()
                _ptr.sendall(line)
                return
            except Exception:
                try: _ptr.close()
                except Exception: pass
                _ptr = None

class Reader:
    def __init__(self, sock):
        self.s = sock
        self.buf = b""
    def need(self, n):
        while len(self.buf) < n:
            d = self.s.recv(65536)
            if not d: raise ConnectionError("eof")
            self.buf += d
        out, self.buf = self.buf[:n], self.buf[n:]
        return out
    def until(self, sep):
        while sep not in self.buf:
            d = self.s.recv(65536)
            if not d: raise ConnectionError("eof")
            self.buf += d
        i = self.buf.index(sep) + len(sep)
        out, self.buf = self.buf[:i], self.buf[i:]
        return out

def ws_frame(opcode, payload):
    if isinstance(payload, str): payload = payload.encode()
    n = len(payload)
    h = bytes([0x80 | opcode])
    if n < 126: h += bytes([n])
    elif n <= 0xFFFF: h += bytes([126]) + n.to_bytes(2, "big")
    else: h += bytes([127]) + n.to_bytes(8, "big")
    return h + payload

def serve_static(r, path):
    name = "index.html" if path in ("/", "") else path.lstrip("/")
    fp = os.path.join(BASE, "web", name)
    if not os.path.isfile(fp):
        r.s.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        return
    data = open(fp, "rb").read()
    mime = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8",
            "css": "text/css; charset=utf-8"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
    hdr = (f"HTTP/1.1 200 OK\r\nContent-Type: {mime}\r\nContent-Length: {len(data)}\r\n"
           "Cache-Control: no-store\r\nConnection: close\r\n\r\n").encode()
    r.s.sendall(hdr + data)

def handle_tls(sock, addr):
    try:
        sock.settimeout(10)
        r = Reader(sock)
        head = r.until(b"\r\n\r\n")
        text = head.decode("latin1")
        if not text:
            return
        lines = text.split("\r\n")
        req = lines[0].split(" ")
        path = req[1] if len(req) > 1 else "/"
        hdrs = {}
        for ln in lines[1:]:
            if ": " in ln:
                k, v = ln.split(": ", 1)
                hdrs[k.lower()] = v
        sock.settimeout(None)

        if path.startswith("/ws") and hdrs.get("upgrade", "").lower() == "websocket":
            key = hdrs.get("sec-websocket-key", "")
            acc = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
            sock.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                          "Connection: Upgrade\r\nSec-WebSocket-Accept: " + acc + "\r\n\r\n").encode())
            clients.add(sock)
            mot.paused = False          # 新客户端接入即视为恢复，避免刷新后状态错位
            mot.ready = False
            print(f"[ws] connected {addr} (total {len(clients)}) paused=False", flush=True)
            ptr_send({"cmd": "sync"})
            sock.sendall(ws_frame(0x1, json.dumps(
                {"state": {"fov": mot.fov, "ix": mot.invert_x, "iy": mot.invert_y}})))
            while True:
                b0 = r.need(2)
                op = b0[0] & 0x0F
                masked = b0[1] & 0x80
                n = b0[1] & 0x7F
                if n == 126: n = int.from_bytes(r.need(2), "big")
                elif n == 127: n = int.from_bytes(r.need(8), "big")
                mk = r.need(4) if masked else b""
                payload = bytearray(r.need(n))
                if masked:
                    for i in range(n): payload[i] ^= mk[i % 4]
                if op == 0x8:
                    break
                if op == 0x9:
                    sock.sendall(ws_frame(0xA, bytes(payload))); continue
                if op == 0x1:
                    handle_msg(bytes(payload), sock)
        else:
            serve_static(r, path)
    except Exception as e:
        print(f"[ws] {addr} end: {type(e).__name__} {e}", flush=True)
    finally:
        clients.discard(sock)
        try: sock.close()
        except Exception: pass

import math

class OneEuro:
    """Adaptive low-pass: heavy smoothing when still, fast when moving."""
    def __init__(self, mincutoff=4.2, beta=0.22, dcutoff=1.0):
        self.mincutoff = mincutoff
        self.beta = beta
        self.dcutoff = dcutoff
        self.xp = None
        self.dxp = 0.0
        self.tp = 0.0

    def alpha(self, cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self.xp is None:
            self.xp, self.tp = x, t
            return x
        dt = max(1e-4, t - self.tp)
        dx = (x - self.xp) / dt
        ad = self.alpha(self.dcutoff, dt)
        dxh = ad * dx + (1 - ad) * self.dxp
        cutoff = self.mincutoff + self.beta * abs(dxh)
        a = self.alpha(cutoff, dt)
        xh = a * x + (1 - a) * self.xp
        self.xp, self.dxp, self.tp = xh, dxh, t
        return xh

    def reset(self):
        self.xp = None
        self.dxp = 0.0


class Motion:
    """Laser-pointer mapping: tilt angle -> absolute screen position.

    Holding still keeps the cursor still (no integration drift), which is what
    stops the pointer from racing into a corner.
    """
    def __init__(self):
        self.ready = False
        self.b0 = self.g0 = 0.0
        self.fov = 42.0      # degrees of tilt from centre to screen edge
        self.dead = 0.9      # centre dead zone, degrees
        self.smooth = 0.28
        self.invert_x = False
        self.invert_y = False
        self.nx = self.ny = 0.0
        self.ltx = self.lty = 0.0
        self.paused = False

    def reset(self):
        self.ready = False
        self.nx = self.ny = 0.0
        self.ltx = self.lty = 0.0

    def store(self):
        try:
            st = json.load(open(os.path.join(BASE, ".handmouse.json")))
            self.fov = float(st.get("fov", 42))
            self.invert_x = bool(st.get("ix", False))
            self.invert_y = bool(st.get("iy", False))
        except Exception:
            pass

    def save(self):
        try:
            json.dump({"fov": self.fov, "ix": self.invert_x, "iy": self.invert_y},
                      open(os.path.join(BASE, ".handmouse.json"), "w"))
        except Exception:
            pass

    def feed(self, b, g, t=0.0):
        """b,g are already decoupled tilt angles in degrees (frontend rotation matrix)."""
        if not self.ready:
            self.b0, self.g0 = 0.0, 0.0
            self.ready = True
        if self.paused:
            return None
        half = max(6.0, self.fov / 2.0)
        dx = g - self.g0
        dy = b - self.b0
        if abs(dx) < self.dead: dx = 0.0
        if abs(dy) < self.dead: dy = 0.0
        tx = max(-1.0, min(1.0, dx / half))
        ty = max(-1.0, min(1.0, dy / half))
        if self.invert_x: tx = -tx
        if self.invert_y: ty = -ty
        # 三档自适应：手抖时几乎锁死，快速转动时完全跟手
        d = abs(tx - self.ltx) + abs(ty - self.lty)
        if d > 0.028:
            a = 0.93          # 快扫：几乎直通
        elif d > 0.011:
            a = 0.66          # 中速：跟手
        else:
            a = 0.07          # 手抖/静止：锁死
        self.ltx, self.lty = tx, ty
        self.nx = a * tx + (1 - a) * self.nx
        self.ny = a * ty + (1 - a) * self.ny
        return self.nx, self.ny

mot = Motion()
mot.store()

def handle_msg(raw, sock=None):
    try: obj = json.loads(raw)
    except Exception: return
    if "cmd" in obj:
        c = obj["cmd"]
        if c == "reset": mot.reset(); print("[recenter]", flush=True); return
        if c == "pause": mot.paused = True; print("[pause]", flush=True); return
        if c == "resume":
            mot.paused = False; mot.reset(); print("[resume]", flush=True); return
        if c == "fov": mot.fov = float(obj.get("v", 42)); mot.save(); return
        if c == "invx": mot.invert_x = not mot.invert_x; mot.save(); return
        if c == "invy": mot.invert_y = not mot.invert_y; mot.save(); return
        if c in ("click", "rclick", "scroll"):
            ptr_send(obj); return
        return
    if "tx" in obj and "ty" in obj:
        res = mot.feed(float(obj["ty"]), float(obj["tx"]), time.monotonic())
        if res is None:
            broadcast({"m": [mot.nx, mot.ny], "p": True}, sock)
            return
        tx, ty = res
        broadcast({"m": [tx, ty], "p": mot.paused}, sock)
        if screen is None: return
        x0, y0, w, h = screen
        mx = max(12.0, w * 0.02)
        my = max(12.0, h * 0.02)
        X = x0 + w / 2 + tx * (w / 2 - mx)
        Y = y0 + h / 2 - ty * (h / 2 - my)
        if abs(X - last_pos[0]) > 0.03 or abs(Y - last_pos[1]) > 0.03:
            ptr_send({"abs": [round(X, 2), round(Y, 2)]})
            last_pos[0], last_pos[1] = X, Y
            if os.environ.get("HM_DEBUG"):
                print(f"[map] in=({tx:+.2f},{ty:+.2f}) -> ({X:.0f},{Y:.0f})", flush=True)

def broadcast(obj, skip=None):
    data = ws_frame(0x1, json.dumps(obj))
    for c in list(clients):
        if c is skip: continue
        try:
            c.sendall(data)
        except Exception:
            clients.discard(c)

def serve_ca(sock):
    try:
        d = sock.recv(8192)
        if not d: return
        ca = open(os.path.join(BASE, "certs", "ca.crt"), "rb").read()
        profile = {
            "PayloadContent": [{
                "PayloadCertificateFileName": "handmouse-ca.crt",
                "PayloadContent": ca,
                "PayloadDescription": "HandMouse local CA",
                "PayloadDisplayName": "HandMouse CA",
                "PayloadIdentifier": "local.handmouse.ca",
                "PayloadType": "com.apple.security.root",
                "PayloadUUID": "8B1F0B2E-3C4D-4E5F-9A6B-1C2D3E4F5A6B",
                "PayloadVersion": 1,
            }],
            "PayloadDisplayName": "HandMouse CA",
            "PayloadIdentifier": "local.handmouse.profile",
            "PayloadRemovalDisallowed": False,
            "PayloadType": "Configuration",
            "PayloadUUID": "A1B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D",
            "PayloadVersion": 1,
        }
        body = plistlib.dumps(profile)
        hdr = ("HTTP/1.1 200 OK\r\nContent-Type: application/x-apple-aspen-config\r\n"
               f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
        sock.sendall(hdr + body)
    except Exception as e:
        print("ca server:", e, flush=True)
    finally:
        try: sock.close()
        except Exception: pass

def loop(port, handler, tls_ctx=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(16)
    print(f"listening :{port}{' (tls)' if tls_ctx else ''}", flush=True)
    while True:
        c, a = s.accept()
        try:
            c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        if tls_ctx:
            try:
                c = tls_ctx.wrap_socket(c, server_side=True)
            except Exception as e:
                print("tls fail", a, e, flush=True)
                c.close(); continue
        threading.Thread(target=handler, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(os.path.join(BASE, "certs", "server.crt"),
                        os.path.join(BASE, "certs", "server.key"))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ptr_send({"cmd": "sync"})   # warm the loopback so pointerd reports its screen size
    time.sleep(0.3)
    threading.Thread(target=loop, args=(PORT_HTTP, lambda s, a: serve_ca(s)), daemon=True).start()
    threading.Thread(target=loop, args=(8444, handle_tls), daemon=True).start()   # plain ws, loopback demo
    loop(PORT_TLS, handle_tls, ctx)
