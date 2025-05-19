# semaphore_server.py
import socket
import threading
import json
import os
import uuid
from datetime import datetime
from hashlib import sha256

DATA_FILE = "users.json"
PORT = 5000
HOST = 'localhost'

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# Load users from file or initialize
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        users = json.load(f)
else:
    users = {
        "sebi": sha256("1234".encode()).hexdigest(),
        "khaled": sha256("1234".encode()).hexdigest(),
        "robert": sha256("1234".encode()).hexdigest()
    }
    with open(DATA_FILE, "w") as f:
        json.dump(users, f)

semaphores = {}
clients = {}  # client_socket: {"id": uuid, "username": None}
lock = threading.Lock()

def is_authenticated(sock):
    return clients.get(sock, {}).get("username") is not None

def handle_client(client_socket, addr):
    client_id = str(uuid.uuid4())[:8]
    with lock:
        clients[client_socket] = {"id": client_id, "username": None}
    log(f"Conectat {client_id} de la {addr}")

    try:
        while True:
            data = client_socket.recv(1024).decode().strip()
            if not data:
                break

            parts = data.split()
            if not parts:
                continue

            command = parts[0].upper()

            if command == "REGISTER" and len(parts) == 3:
                username, password = parts[1], parts[2]
                hashed = sha256(password.encode()).hexdigest()
                with lock:
                    if username in users:
                        client_socket.send("ERROR: Utilizatorul exista deja\n".encode())
                    else:
                        users[username] = hashed
                        with open(DATA_FILE, "w") as f:
                            json.dump(users, f)
                        client_socket.send("REGISTERED\n".encode())
                        log(f"{username} inregistrat cu succes")
                continue

            if command == "LOGIN" and len(parts) == 3:
                username, password = parts[1], parts[2]
                hashed = sha256(password.encode()).hexdigest()
                with lock:
                    if users.get(username) == hashed:
                        clients[client_socket]["username"] = username
                        client_socket.send("OK\n".encode())
                        log(f"{username} autentificat cu succes ({client_id})")
                    else:
                        client_socket.send("FAIL\n".encode())
                        log(f"Esec autentificare pentru {username}")
                continue

            if not is_authenticated(client_socket):
                client_socket.send("ERROR: Trebuie sa te autentifici cu LOGIN\n".encode())
                continue

            sem_name = parts[1] if len(parts) > 1 else None
            username = clients[client_socket]["username"]

            with lock:
                if command == "ACQUIRE" and sem_name:
                    sem = semaphores.setdefault(sem_name, {"owner": None, "queue": []})
                    if sem["owner"] is None:
                        sem["owner"] = username
                        client_socket.send(f"GRANTED {sem_name}\n".encode())
                        log(f"{username} a obtinut {sem_name}")
                    else:
                        sem["queue"].append((client_socket, username, datetime.now()))
                        client_socket.send(f"WAITING {sem_name}\n".encode())

                elif command == "RELEASE" and sem_name:
                    sem = semaphores.get(sem_name)
                    if sem and sem["owner"] == username:
                        if sem["queue"]:
                            next_socket, next_user, _ = sem["queue"].pop(0)
                            sem["owner"] = next_user
                            try:
                                next_socket.send(f"GRANTED {sem_name}\n".encode())
                            except:
                                log(f"Eroare la notificarea clientului {next_user}")
                                sem["owner"] = None
                        else:
                            sem["owner"] = None
                        client_socket.send(f"RELEASED {sem_name}\n".encode())
                    else:
                        client_socket.send(f"ERROR Nu detii {sem_name}\n".encode())

                elif command == "STATUS" and sem_name:
                    sem = semaphores.get(sem_name)
                    if sem:
                        queue_names = [cid for _, cid, _ in sem["queue"]]
                        client_socket.send(f"{sem_name}: owner={sem['owner']}, queue={queue_names}\n".encode())
                    else:
                        client_socket.send(f"{sem_name} nu exista\n".encode())

                elif command == "LIST":
                    msg = "\n".join([
                        f"{name}: owner={info['owner']}, queue={[cid for _, cid, _ in info['queue']]}"
                        for name, info in semaphores.items()
                    ])
                    client_socket.send((msg or "Niciun semafor activ\n").encode())

                elif command == "QUIT":
                    break

                else:
                    client_socket.send("Comanda invalida\n".encode())

    finally:
        with lock:
            data = clients.pop(client_socket, {"id": "necunoscut", "username": "necunoscut"})
            for sem in semaphores.values():
                if sem["owner"] == data["username"]:
                    sem["owner"] = None
                sem["queue"] = [entry for entry in sem["queue"] if entry[1] != data["username"]]
        client_socket.close()
        log(f"{data['username']} ({data['id']}) s-a deconectat")

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    log(f"Server pornit pe {HOST}:{PORT}")

    while True:
        client_socket, addr = server.accept()
        threading.Thread(target=handle_client, args=(client_socket, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()