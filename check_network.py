import socket

for host in ["generativelanguage.googleapis.com",
             "api.trychannel3.com",
             "api-m.sandbox.paypal.com",
             "cdn.jsdelivr.net"]:
    try:
        ip = socket.getaddrinfo(host, 443)[0][4][0]
        print("OK  ", host, ip)
    except socket.gaierror as e:
        print("FAIL", host, e)