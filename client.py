import socket
import threading

def listen_server(sock):
    while True:
        try:
            msg = sock.recv(1024).decode()
            if not msg:
                break
            print("[SERVER]:", msg.strip())
        except:
            break

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 5000))

    threading.Thread(target=listen_server, args=(s,), daemon=True).start()

    print("Comenzi: ACQUIRE <nume>, RELEASE <nume>, STATUS <nume>, LIST, QUIT")

    while True:
        try:
            cmd = input("> ")
            s.send((cmd.strip() + "\n").encode())
            if cmd.upper().startswith("QUIT"):
                break
        except KeyboardInterrupt:
            break

    s.close()

if __name__ == "__main__":
    main()
