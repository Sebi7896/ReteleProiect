import socket
import threading

def receiver(sock, flags):
    """
    Thread care primește mesaje de la server.
    Dacă primește BEGIN_EDIT ... END_EDIT, strânge conținutul.
    Dacă primește GRANTED <fisier>, afișează mesajul imediat.
    Dacă primește mesaje normale, le afișează cu prefixul [SERVER]:
    Exceptie pentru read, afișăm doar conținutul.
    """
    buffer_edit = []
    in_edit = False

    try:
        while flags['running']:
            data = sock.recv(4096).decode()
            if not data:
                print("\n[CLIENT]: Conexiunea a fost închisă de server.")
                flags['running'] = False
                break

            lines = data.splitlines()
            for line in lines:
                line_strip = line.strip()

                # Detectam OK dupa login
                if line_strip == "OK":
                    flags['logged_in'] = True
                    print(f"\n[SERVER]: {line_strip}")
                    print("> ", end="", flush=True)
                    continue

                # Gestionare mesaj edit
                if in_edit:
                    if line_strip == "END_EDIT":
                        print("\n[SERVER]: Conținutul fisierului pentru editare:\n" + "="*30)
                        print("\n".join(buffer_edit))
                        print("="*30)
                        flags['edit_content'] = "\n".join(buffer_edit)
                        flags['edit_ready'] = True
                        in_edit = False
                        buffer_edit = []
                    else:
                        buffer_edit.append(line)
                    continue

                if "FILE_BEGIN" in line_strip:
                    file_bytes = b""

                    # Continuăm să citim până găsim FILE_END
                    while True:
                        chunk = sock.recv(4096)
                        if b"FILE_END" in chunk:
                            chunk = chunk.replace(b"FILE_END", b"")
                            file_bytes += chunk
                            break
                        file_bytes += chunk

                    filename = input("[CLIENT]: Salvează fișierul cu numele: ").strip()
                    try:
                        with open(filename, "wb") as f:
                            f.write(file_bytes)
                        print(f"[CLIENT]: Fișierul a fost salvat ca '{filename}'.")
                    except Exception as ex:
                        print(f"[CLIENT]: Eroare la salvarea fișierului: {ex}")
                    print("> ", end="", flush=True)
                    continue


                # Dacă începe conținutul de edit
                if line_strip == "BEGIN_EDIT":
                    in_edit = True
                    buffer_edit = []
                    continue

                # Mesaj automat GRANTED
                if line_strip.startswith("GRANTED "):
                    fname = line_strip[8:]
                    print(f"\n[SERVER]: Ai primit lock pentru fișierul '{fname}'! Poți să îl editezi acum.")
                    flags['granted_files'].add(fname)
                    continue

                # Dacă mesajul începe cu ERROR în contextul edit (flag edit_ready=False)
                if line_strip.startswith("ERROR") and not flags['edit_ready']:
                    # Eroare primita când încercam edit, o afisam
                    print(f"\n[SERVER]: {line_strip}")
                    # Nu schimbam starea edit_ready, deci main nu asteapta sa editeze
                    continue

                # Dacă mesajul e răspuns la comanda read (presupunem că vine fără prefix special)
                # Vom verifica dacă așteptăm output read (flag read_mode)
                if flags.get('read_mode', False):
                    # Afișăm conținutul raw, fără prefix și fără prompt
                    print(line)
                    continue

                # Alte mesaje normale
                print(f"\n[SERVER]: {line}")
                print("> ", end="", flush=True)

    except Exception as e:
        print(f"\n[CLIENT]: Eroare in thread receiver: {e}")
        flags['running'] = False


def input_multiline():
    """
    Citeste input multi-linie, terminat cu :wq pe o linie separata.
    """
    print("[CLIENT]: Scrie continutul fisierului. Termina cu ':wq' pe o linie noua.")
    lines = []
    while True:
        line = input()
        if line.strip() == ":wq":
            break
        lines.append(line)
    return "\n".join(lines)


def main():
    s = socket.socket()
    s.connect(("localhost", 5000))

    flags = {
        'running': True,
        'logged_in': False,
        'edit_ready': False,
        'edit_content': "",
        'granted_files': set(),
        'read_mode': False,
    }

    # Pornim thread-ul care primește mesaje de la server
    threading.Thread(target=receiver, args=(s, flags), daemon=True).start()

    import time
    # Login / Register
    while not flags['logged_in'] and flags['running']:
        print("\n1. LOGIN\n2. REGISTER")
        opt = input("Alege [1/2]: ").strip()
        if opt == "1":
            user = input("User: ").strip()
            passwd = input("Parola: ").strip()
            s.send(f"LOGIN {user} {passwd}\n".encode())
        elif opt == "2":
            user = input("User nou: ").strip()
            passwd = input("Parola: ").strip()
            s.send(f"REGISTER {user} {passwd}\n".encode())
        else:
            print("Optiune invalida")
            continue
        time.sleep(0.5)  # asteptam raspunsul de la server

    if not flags['logged_in']:
        print("[CLIENT]: Nu s-a putut autentifica. Inchid.")
        s.close()
        return

    print("""
    Comenzi disponibile:

    Autentificare:
    - login
    - register

    Fișiere:
    - create <fisier>         → creează fișier
    - get <fisier>            → cere lock pe fișier
    - release <fisier>        → eliberează lock
    - edit <fisier>           → editează fișierul (necesită lock)
    - delete <fisier>         → șterge fișierul (necesită lock)
    - read <fisier>           → citește conținutul fișierului
    - download <fisier>       → descarcă fișierul local   # <- adăugat

    Listări:
    - list                    → afișează starea lock-urilor
    - listfiles               → afișează fișierele existente

    Altele:
    - help                    → afișează comenzi disponibile
    - quit                    → deconectare
    """)

    # Loop comenzi
    while flags['running']:
        cmd = input("> ").strip()
        if not cmd:
            continue

        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if action == "edit":
            if not arg:
                print("[CLIENT]: Trebuie sa specifici un fisier.")
                continue
            if arg not in flags['granted_files']:
                print(f"[CLIENT]: Nu ai lock pe fisierul '{arg}'. Foloseste 'get {arg}' pentru a cere lock.")
                continue

            s.send((cmd + "\n").encode())

            # Așteptăm răspunsul (care trebuie să fie BEGIN_EDIT ... END_EDIT)
            while not flags['edit_ready']:
                if not flags['running']:
                    break
            if not flags['running']:
                break

            # Dacă edit_ready e True, înseamnă că am primit conținutul pt edit
            # Altfel (de ex, dacă am primit error) nu intrăm aici

            print("[CLIENT]: Continut curent fisier:")
            print("="*30)
            print(flags['edit_content'])
            print("="*30)

            new_content = input_multiline()

            s.send(new_content.encode())

            flags['edit_ready'] = False

        elif action == "read":
            if not arg:
                print("[CLIENT]: Trebuie sa specifici un fisier.")
                continue

            flags['read_mode'] = True
            s.send((cmd + "\n").encode())

            # Așteptăm puțin să primim outputul
            # Outputul va fi afișat direct în thread-ul receiver fără prefix sau prompt

            # De când s-a terminat comanda read, read_mode se va reseta
            # Cum știm când se termină? Dacă serverul trimite tot conținutul și apoi prompt
            # Pentru simplitate, punem timeout scurt aici
            import time
            time.sleep(0.5)
            flags['read_mode'] = False

        elif action == "help":
            print("""
            Comenzi disponibile:

            Autentificare:
            - login
            - register

            Fișiere:
            - create <fisier>         → creează fișier
            - get <fisier>            → cere lock pe fișier
            - release <fisier>        → eliberează lock
            - edit <fisier>           → editează fișierul (necesită lock)
            - delete <fisier>         → șterge fișierul (necesită lock)
            - read <fisier>           → citește conținutul fișierului
            - download <fisier>       → descarcă fișierul local   # <- adăugat

            Listări:
            - list                    → afișează starea lock-urilor
            - listfiles               → afișează fișierele existente

            Altele:
            - help                    → afișează comenzi disponibile
            - quit                    → deconectare
            """)

        else:
            s.send((cmd + "\n").encode())

            if action == "quit":
                flags['running'] = False
                break

    s.close()
    print("[CLIENT]: Conexiune inchisa.")


if __name__ == "__main__":
    main()
