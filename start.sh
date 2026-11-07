#!/bin/zsh
cd -- "${0:A:h}"
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
[[ -f certs/server.crt ]] || { print "no certs — run ./gen-certs.sh first"; exit 1; }
[[ -x ./pointerd ]] || { print "no binaries — run ./build.sh first"; exit 1; }
pkill -f "pointerd$" 2>/dev/null; pkill -f "server.py" 2>/dev/null; sleep 0.4
nohup ./pointerd > pointerd.log 2>&1 &
sleep 1
nohup python3 server.py > server.log 2>&1 &
sleep 1
print "HandMouse 已启动"
print "  1) iPhone 装 CA: http://$IP:8080/ca.mobileconfig"
print "  2) iPhone 打开:  https://$IP:8443/"
print "  Mac 端辅助功能: systemsettings → 隐私与安全性 → 辅助功能"
