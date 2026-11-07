#!/bin/zsh
set -euo pipefail
cd -- "${0:A:h}"
IP="${1:-$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)}"
[[ -n "$IP" ]] || { print "no LAN address; pass one: ./gen-certs.sh 192.168.1.20"; exit 1; }
mkdir -p certs && cd certs

openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout ca.key -out ca.crt -subj "/CN=HandMouse Local CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null

openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr \
  -subj "/CN=$IP" 2>/dev/null

printf "subjectAltName=IP:%s,IP:127.0.0.1,DNS:localhost\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n" "$IP" > san.ext

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days 825 -sha256 -out server.crt -extfile san.ext 2>/dev/null

openssl x509 -in ca.crt -outform der -out ca.der 2>/dev/null

print "certs written for $IP"
print "iPhone: http://$IP:8080/ca.mobileconfig"
