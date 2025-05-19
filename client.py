# semaphore_client.py
import socket
import threading
import sys
nrAutentificariPosibile = 3

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

    authenticated = False
    nrIncercari = 0
    while not authenticated:
        print("\n1. LOGIN")
        print("2. REGISTER")
        opt = input("Alege [1/2]: ").strip()

        if opt == "1":
            username = input("Utilizator: ").strip()
            password = input("Parolă: ").strip()
            s.send(f"LOGIN {username} {password}\n".encode())
            response = s.recv(1024).decode().strip()
            print("[SERVER]:", response)
            if response == "OK":
                authenticated = True
            nrIncercari = nrIncercari + 1
            if nrIncercari == 3:
                 print("Numar maxim de incercari depasit..")
                 s.close()
                 sys.exit(1)

        elif opt == "2":
            username = input("Nume nou utilizator: ").strip()
            password = input("Parolă: ").strip()
            s.send(f"REGISTER {username} {password}\n".encode())
            response = s.recv(1024).decode().strip()
            print("[SERVER]:", response)
            if response == "REGISTERED":
                print("[CLIENT]: Acum te poți loga.")
        else:
            print("[CLIENT]: Opțiune invalidă.")

    print("""
Autentificare reușită!
Comenzi disponibile:
- ACQUIRE <semafor>
- RELEASE <semafor>
- STATUS <semafor>
- LIST
- QUIT
""")

    threading.Thread(target=listen_server, args=(s,), daemon=True).start()

    while True:
        try:
            cmd = input("> ").strip()
            if not cmd:
                continue
            s.send((cmd + "\n").encode())

            if cmd.upper().startswith("QUIT"):
                break

        except KeyboardInterrupt:
            print("\n[CLIENT]: Deconectare forțată.")
            break

    s.close()

if __name__ == "__main__":
    main()