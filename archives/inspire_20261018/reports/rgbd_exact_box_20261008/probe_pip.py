import socket
hosts = ["download.pytorch.org", "pypi.org", "mirrors.aliyun.com", "files.pythonhosted.org"]
for host in hosts:
    s = socket.socket()
    s.settimeout(8)
    try:
        s.connect((host, 443))
        print(host, "OK")
    except Exception as exc:
        print(host, "FAIL", type(exc).__name__, exc)
    finally:
        s.close()
