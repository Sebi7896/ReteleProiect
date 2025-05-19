import socket
import threading
from datetime import datetime
import uuid

# Structura semafoarelor: { "nume": { "owner": "id_client", "queue": [(client_socket, id_client, timestamp), ...] } }
semaphores = {}
clients = {}  # client_socket: client_id
lock = threading.Lock()

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def handle_client(client_socket, addr):
    client_id = str(uuid.uuid4())[:8] #uuid dat de catre noi fiecarui client
    with lock:
        clients[client_socket] = client_id
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
            sem_name = parts[1] if len(parts) > 1 else None

            with lock:
                if command == "ACQUIRE" and sem_name:
                    sem = semaphores.setdefault(sem_name, {"owner": None, "queue": []})
                    if sem["owner"] is None:
                        sem["owner"] = client_id
                        client_socket.send(f"GRANTED {sem_name}\n".encode())
                        log(f"{client_id} a obținut {sem_name}")
                    else:
                        sem["queue"].append((client_socket, client_id, datetime.now()))
                        client_socket.send(f"WAITING {sem_name}\n".encode())
                        log(f"{client_id} așteaptă pentru {sem_name}")

                elif command == "RELEASE" and sem_name:
                    sem = semaphores.get(sem_name)
                    if sem and sem["owner"] == client_id:
                        if sem["queue"]:
                            next_socket, next_id, _ = sem["queue"].pop(0)
                            sem["owner"] = next_id
                            try:
                                next_socket.send(f"GRANTED {sem_name}\n".encode())
                            except:
                                sem["owner"] = None
                                log(f"Eroare la notificarea {next_id}")
                        else:
                            sem["owner"] = None
                        client_socket.send(f"RELEASED {sem_name}\n".encode())
                    else:
                        client_socket.send(f"ERROR Nu deții {sem_name}\n".encode())

                elif command == "STATUS" and sem_name:
                    sem = semaphores.get(sem_name)
                    if sem:
                        queue_ids = [cid for _, cid, _ in sem["queue"]]
                        client_socket.send(f"{sem_name}: owner={sem['owner']}, queue={queue_ids}\n".encode())
                    else:
                        client_socket.send(f"{sem_name} nu există\n".encode())

                elif command == "LIST":
                    msg = "\n".join(
                        [f"{name}: owner={info['owner']}, queue={[cid for _, cid, _ in info['queue']]}"
                         for name, info in semaphores.items()]
                    )
                    client_socket.send((msg or "Niciun semafor activ\n").encode())

                elif command == "QUIT":
                    break

                else:
                    client_socket.send("Comandă invalidă\n".encode())

    finally:
        with lock:
            client_id = clients.pop(client_socket, "necunoscut")
            for sem in semaphores.values():
                if sem["owner"] == client_id:
                    sem["owner"] = None
                sem["queue"] = [entry for entry in sem["queue"] if entry[1] != client_id]
        client_socket.close()
        log(f"{client_id} s-a deconectat")

def start_server(host='localhost', port=5000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    log(f"Server pornit pe {host}:{port}")

    while True:
        client_socket, addr = server.accept()
        threading.Thread(target=handle_client, args=(client_socket, addr), daemon=True).start()

start_server()
