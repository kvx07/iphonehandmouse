#!/bin/zsh
pkill -f "pointerd$" 2>/dev/null; pkill -f "server.py" 2>/dev/null
print "stopped"
