import sys
import socket

def run_server(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', port))
    print(f"UDP echo server listening on port {port}", flush=True)
    while True:
        data, addr = sock.recvfrom(1024)
        sock.sendto(data, addr)
        print(f"echoed per client: {data.decode(errors='ignore')}", flush=True)

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    run_server(port)