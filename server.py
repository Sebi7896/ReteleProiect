import socket
import threading
import os
import json
from hashlib import sha256

HOST, PORT = 'localhost', 5000
DATA_FILE = "users.json"
WORKSPACE = "workspace"

os.makedirs(WORKSPACE, exist_ok=True)

users = {}
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        users = json.load(f)

semaphores = {}
clients = {}
lock = threading.Lock()

def handle_client(sock, addr):
    clients[sock] = None
    try:
        while True:
            data = sock.recv(4096).decode()
            if not data:
                break

            lines = data.strip().split("\n")
            for line in lines:
                parts = line.strip().split(maxsplit=2)
                if not parts:
                    continue

                cmd = parts[0].upper()
                arg = parts[1] if len(parts) > 1 else None
                content = parts[2] if len(parts) > 2 else None
                user = clients[sock]

                with lock:
                    if cmd == "REGISTER" and len(parts) == 3:
                        if arg in users:
                            sock.send(b"ERROR: Utilizatorul exista\n")
                        else:
                            users[arg] = sha256(content.encode()).hexdigest()
                            with open(DATA_FILE, "w") as f:
                                json.dump(users, f)
                            sock.send(b"REGISTERED\n")

                    elif cmd == "LOGIN" and len(parts) == 3:
                        if users.get(arg) == sha256(content.encode()).hexdigest():
                            clients[sock] = arg
                            sock.send(b"OK\n")
                        else:
                            sock.send(b"FAIL\n")

                    elif not clients[sock]:
                        sock.send(b"ERROR: Trebuie sa te autentifici\n")

                    elif cmd == "CREATE" and arg:
                        path = os.path.join(WORKSPACE, arg)
                        if os.path.exists(path):
                            sock.send(b"ERROR: Fisierul exista deja\n")
                        else:
                            open(path, "w").close()
                            semaphores[arg] = {"owner": None, "queue": []}
                            sock.send(f"CREATED {arg}\n".encode())

                    elif cmd == "GET" and arg:
                        sem = semaphores.setdefault(arg, {"owner": None, "queue": []})
                        if sem["owner"] is None:
                            sem["owner"] = user
                            sock.send(f"GRANTED {arg}\n".encode())
                        else:
                            if not any(s == sock for s, _ in sem["queue"]):
                                sem["queue"].append((sock, user))
                            sock.send(f"WAITING {arg}\n".encode())

                    elif cmd == "RELEASE" and arg:
                        sem = semaphores.get(arg)
                        if sem and sem["owner"] == user:
                            if sem["queue"]:
                                next_sock, next_user = sem["queue"].pop(0)
                                sem["owner"] = next_user
                                try:
                                    next_sock.send(f"GRANTED {arg}\n".encode())
                                except:
                                    sem["owner"] = None
                            else:
                                sem["owner"] = None
                            sock.send(f"RELEASED {arg}\n".encode())
                        else:
                            sock.send(b"ERROR: Nu detii lock-ul\n")

                    elif cmd == "EDIT" and arg:
                        sem = semaphores.get(arg)
                        if not sem or sem["owner"] != user:
                            sock.send(b"ERROR: Nu ai lock-ul pe fisier\n")
                        else:
                            path = os.path.join(WORKSPACE, arg)
                            if not os.path.exists(path):
                                sock.send(b"ERROR: Fisier inexistent\n")
                            else:
                                with open(path) as f:
                                    old_content = f.read()
                                sock.send(f"BEGIN_EDIT\n{old_content}\nEND_EDIT\n".encode())
                                new_content = sock.recv(10000).decode()
                                with open(path, "w") as f:
                                    f.write(new_content)
                                sock.send(b"OK: Fisier salvat\n")

                    elif cmd == "READ" and arg:
                        path = os.path.join(WORKSPACE, arg)
                        if not os.path.exists(path):
                            sock.send(b"ERROR: Fisier inexistent\n")
                        else:
                            with open(path) as f:
                                content = f.read()
                            sock.send(content.encode())

                    elif cmd == "DELETE" and arg:
                        sem = semaphores.get(arg)
                        if sem and sem["owner"] == user:
                            os.remove(os.path.join(WORKSPACE, arg))
                            semaphores.pop(arg, None)
                            sock.send(b"DELETED\n")
                        else:
                            sock.send(b"ERROR: Nu ai lock-ul\n")

                    elif cmd == "DOWNLOAD" and arg:
                        path = os.path.join(WORKSPACE, arg)
                        if not os.path.exists(path):
                            sock.send(b"ERROR: Fisier inexistent\n")

                        else:
                            with open(path, "rb") as f:
                                content = f.read()

                            sock.sendall(b"FILE_BEGIN\n")
                            sock.sendall(content)
                            sock.sendall(b"\nFILE_END\n")

                    elif cmd == "LISTFILES":
                        files = os.listdir(WORKSPACE)
                        sock.send(("\n".join(files) or "Niciun fisier\n").encode())

                    elif cmd == "LIST":
                        output = "\n".join([f"{k}: {v['owner']}" for k, v in semaphores.items()])
                        sock.send((output or "Nimic\n").encode())

                    elif cmd == "QUIT":
                        sock.send(b"BYE\n")
                        return

                    else:
                        sock.send(b"Comanda necunoscuta\n")
    finally:
        user = clients.pop(sock, None)
        with lock:
            for sem in semaphores.values():
                if sem["owner"] == user:
                    sem["owner"] = None
                sem["queue"] = [x for x in sem["queue"] if x[1] != user]
        sock.close()

def main():
    srv = socket.socket()
    srv.bind((HOST, PORT))
    srv.listen()
    print(f"Serverul ruleaza pe {HOST}:{PORT}")
    while True:
        c, a = srv.accept()
        threading.Thread(target=handle_client, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    main()
