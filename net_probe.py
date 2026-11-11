import socket, time

HOSTS = ["api-m.sandbox.paypal.com", "api.trychannel3.com",
         "generativelanguage.googleapis.com"]

for host in HOSTS:
    for fam, name in ((socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")):
        try:
            infos = socket.getaddrinfo(host, 443, fam, socket.SOCK_STREAM)
        except socket.gaierror:
            print(f"{host:36s} {name}  no address")
            continue
        ok, times = 0, []
        for _ in range(5):
            s = socket.socket(fam, socket.SOCK_STREAM)
            s.settimeout(5)
            t = time.time()
            try:
                s.connect(infos[0][4])
                ok += 1
                times.append(time.time() - t)
            except Exception:
                pass
            finally:
                s.close()
        avg = f"{sum(times) / len(times):.2f}s avg" if times else "-"
        print(f"{host:36s} {name}  {ok}/5 connected  {avg}")