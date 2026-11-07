#!/bin/zsh
cd -- "${0:A:h}"
if ! lsof -nP -iTCP:8443 -sTCP:LISTEN >/dev/null 2>&1; then ./start.sh; sleep 1.2; fi
pkill -f "handmouse/viewer" 2>/dev/null
nohup ./viewer > viewer.log 2>&1 &
sleep 1
print "演示窗口已启动（ESC 关闭）"
