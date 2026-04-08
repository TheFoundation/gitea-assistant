#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gitea Repository Manager v0.0
==============================
Grapical Linux-application to manage gitea repositories
within organizations and personal account with a token
Usge:   python3 gitea_manager.py
Depends: git ,  pip install requests tk
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import json
import os
import subprocess
import threading
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# ---------------------------------------------------------------------------
# Globale Konstanten
# ---------------------------------------------------------------------------
CONFIG_DIR  = Path.home() / ".config" / "gitea-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"
CLONE_ZIEL  = Path("/home/guest/code")

GITIGNORE_TEMPLATES = [
    "", "Python", "Node", "Go", "Java", "Rust",
    "C", "C++", "Ruby", "PHP", "Swift", "Kotlin", "Dart", "Unity",
]
LIZENZEN = [
    "", "MIT", "Apache-2.0", "GPL-3.0", "LGPL-3.0",
    "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "AGPL-3.0",
]

C = {
    "bg":       "#1e1e2e",
    "bg2":      "#2a2a3e",
    "bg3":      "#313145",
    "accent":   "#89b4fa",
    "accent2":  "#cba6f7",
    "success":  "#a6e3a1",
    "warning":  "#f9e2af",
    "danger":   "#f38ba8",
    "fg":       "#cdd6f4",
    "fg_dim":   "#6c7086",
    "border":   "#45475a",
    "tag_priv": "#f38ba8",
    "tag_pub":  "#a6e3a1",
    "term_bg":  "#0d0d1a",
    "term_fg":  "#d0d0d0",
}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def lade_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def speichere_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def format_datum(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso_str or "-"


def http_fehler_text(exc):
    code = exc.response.status_code if exc.response is not None else "?"
    texte = {
        401: "Authentifizierung fehlgeschlagen.\nAPI-Token pruefen.",
        403: "Zugriff verweigert.\nFehlende Berechtigungen.",
        404: "Ressource nicht gefunden.\nURL oder Name pruefen.",
        409: "Konflikt - Repository existiert moeglicherweise bereits.",
        422: "Ungueltige Eingabe.\nBitte alle Felder pruefen.",
    }
    return texte.get(code, "HTTP-Fehler {}: {}".format(code, exc))


# ---------------------------------------------------------------------------
# Gitea API-Client
# ---------------------------------------------------------------------------
class GiteaClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.token    = token
        self.session  = requests.Session()
        self.session.headers.update({
            "Authorization": "token " + token,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        })

    def _get(self, path, params=None):
        url  = self.base_url + "/api/v1" + path
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path, payload):
        url  = self.base_url + "/api/v1" + path
        resp = self.session.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path):
        url  = self.base_url + "/api/v1" + path
        resp = self.session.delete(url, timeout=10)
        resp.raise_for_status()

    def test_connection(self):
        return self._get("/user")

    def get_orgs(self):
        return self._get("/user/orgs", {"limit": 50})

    def get_repos(self, org):
        repos, page = [], 1
        while True:
            batch = self._get("/orgs/" + org + "/repos",
                              {"limit": 50, "page": page})
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 50:
                break
            page += 1
        return repos

    def create_repo(self, org, payload):
        return self._post("/orgs/" + org + "/repos", payload)

    def delete_repo(self, org, repo):
        self._delete("/repos/" + org + "/" + repo)


# ---------------------------------------------------------------------------
# Konfigurationsdialog
# ---------------------------------------------------------------------------
class KonfigDialog(tk.Toplevel):
    def __init__(self, parent, cfg, callback):
        super().__init__(parent)
        self.title("Verbindungseinstellungen")
        self.resizable(False, False)
        self.configure(bg=C["bg2"])
        self.callback = callback
        self.grab_set()
        self._baue_ui(cfg)
        self.protocol("WM_DELETE_WINDOW", self._abbrechen)
        self._zentriere(parent)

    def _zentriere(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry("+{}+{}".format(x, y))

    def _baue_ui(self, cfg):
        pad = {"padx": 16, "pady": 8}

        tk.Label(self, text="  Gitea Verbindung konfigurieren",
                 font=("Monospace", 13, "bold"),
                 bg=C["bg2"], fg=C["accent"],
        ).grid(row=0, column=0, columnspan=2, pady=(16, 4), padx=16, sticky="w")

        tk.Label(self, text="Gitea-URL:",
                 bg=C["bg2"], fg=C["fg"], font=("Monospace", 10),
        ).grid(row=1, column=0, sticky="w", **pad)

        self.url_var = tk.StringVar(value=cfg.get("url", "https://"))
        tk.Entry(self, textvariable=self.url_var, width=44,
                 bg=C["bg3"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=("Monospace", 10),
        ).grid(row=1, column=1, **pad)

        tk.Label(self, text="API-Token:",
                 bg=C["bg2"], fg=C["fg"], font=("Monospace", 10),
        ).grid(row=2, column=0, sticky="w", **pad)

        self.token_var = tk.StringVar(value=cfg.get("token", ""))
        token_entry = tk.Entry(self, textvariable=self.token_var,
                               width=44, show="*",
                               bg=C["bg3"], fg=C["fg"],
                               insertbackground=C["fg"],
                               relief="flat", font=("Monospace", 10))
        token_entry.grid(row=2, column=1, **pad)

        self.zeige_var = tk.BooleanVar()
        tk.Checkbutton(self, text="Token anzeigen",
                       variable=self.zeige_var,
                       command=lambda: token_entry.config(
                           show="" if self.zeige_var.get() else "*"),
                       bg=C["bg2"], fg=C["fg_dim"],
                       selectcolor=C["bg3"], activebackground=C["bg2"],
                       font=("Monospace", 9),
        ).grid(row=3, column=1, sticky="w", padx=16)

        tk.Label(self,
                 text="Token: Gitea -> Einstellungen -> Anwendungen -> Token generieren",
                 bg=C["bg2"], fg=C["fg_dim"], font=("Monospace", 8),
        ).grid(row=4, column=0, columnspan=2, padx=16, pady=(0, 8), sticky="w")

        bf = tk.Frame(self, bg=C["bg2"])
        bf.grid(row=5, column=0, columnspan=2, pady=(4, 16), padx=16, sticky="e")

        tk.Button(bf, text="Abbrechen", command=self._abbrechen,
                  bg=C["bg3"], fg=C["fg_dim"],
                  activebackground=C["border"], relief="flat",
                  font=("Monospace", 10), padx=12, pady=4,
        ).pack(side="left", padx=(0, 8))

        tk.Button(bf, text="Verbinden & Speichern", command=self._speichern,
                  bg=C["accent"], fg=C["bg"],
                  activebackground=C["accent2"], relief="flat",
                  font=("Monospace", 10, "bold"), padx=12, pady=4,
        ).pack(side="left")

    def _speichern(self):
        url   = self.url_var.get().strip()
        token = self.token_var.get().strip()
        if not url or not token:
            messagebox.showwarning("Eingabe fehlt",
                                   "Bitte URL und Token angeben.", parent=self)
            return
        cfg = {"url": url, "token": token}
        speichere_config(cfg)
        self.destroy()
        self.callback(cfg)

    def _abbrechen(self):
        self.destroy()
        self.callback(None)


# ---------------------------------------------------------------------------
# Dialog: Neues Repository anlegen
# ---------------------------------------------------------------------------
class NeuesRepoDialog(tk.Toplevel):
    def __init__(self, parent, org, client, on_success):
        super().__init__(parent)
        self.title("Neues Repository in: " + org)
        self.resizable(False, False)
        self.configure(bg=C["bg2"])
        self.org        = org
        self.client     = client
        self.on_success = on_success
        self.grab_set()
        self._baue_ui()
        self._zentriere(parent)

    def _zentriere(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry("+{}+{}".format(x, y))

    def _lbl(self, parent, text, row, required=False):
        farbe  = C["danger"] if required else C["fg_dim"]
        suffix = " *" if required else ""
        tk.Label(parent, text=text + suffix,
                 bg=C["bg2"], fg=farbe, font=("Monospace", 9),
        ).grid(row=row, column=0, sticky="w", padx=12, pady=4)

    def _baue_ui(self):
        tk.Label(self, text="  Neues Repository - " + self.org,
                 font=("Monospace", 12, "bold"),
                 bg=C["bg2"], fg=C["accent"],
        ).pack(padx=16, pady=(14, 8), anchor="w")

        form = tk.Frame(self, bg=C["bg2"])
        form.pack(padx=16, fill="x")

        self._lbl(form, "Repository-Name", 0, required=True)
        self.name_var = tk.StringVar()
        tk.Entry(form, textvariable=self.name_var, width=38,
                 bg=C["bg3"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=("Monospace", 10),
        ).grid(row=0, column=1, padx=8, pady=4, sticky="w")

        self._lbl(form, "Beschreibung", 1)
        self.desc_var = tk.StringVar()
        tk.Entry(form, textvariable=self.desc_var, width=38,
                 bg=C["bg3"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=("Monospace", 10),
        ).grid(row=1, column=1, padx=8, pady=4, sticky="w")

        self._lbl(form, "Sichtbarkeit", 2)
        self.privat_var = tk.BooleanVar(value=False)
        vf = tk.Frame(form, bg=C["bg2"])
        vf.grid(row=2, column=1, padx=8, pady=4, sticky="w")
        for lbl, val in [("Public", False), ("Private", True)]:
            tk.Radiobutton(vf, text=lbl,
                           variable=self.privat_var, value=val,
                           bg=C["bg2"], fg=C["fg"], selectcolor=C["bg3"],
                           activebackground=C["bg2"],
                           font=("Monospace", 10),
            ).pack(side="left", padx=(0, 12))

        self._lbl(form, "Initialisieren", 3)
        self.init_var = tk.BooleanVar(value=True)
        tk.Checkbutton(form, text="README.md anlegen",
                       variable=self.init_var,
                       bg=C["bg2"], fg=C["fg"], selectcolor=C["bg3"],
                       activebackground=C["bg2"],
                       font=("Monospace", 10),
        ).grid(row=3, column=1, padx=8, pady=4, sticky="w")

        self._lbl(form, ".gitignore-Template", 4)
        self.gitignore_var = tk.StringVar(value="")
        ttk.Combobox(form, textvariable=self.gitignore_var,
                     values=GITIGNORE_TEMPLATES,
                     state="readonly", width=20,
                     font=("Monospace", 10),
        ).grid(row=4, column=1, padx=8, pady=4, sticky="w")

        self._lbl(form, "Lizenz", 5)
        self.lizenz_var = tk.StringVar(value="")
        ttk.Combobox(form, textvariable=self.lizenz_var,
                     values=LIZENZEN, state="readonly", width=20,
                     font=("Monospace", 10),
        ).grid(row=5, column=1, padx=8, pady=4, sticky="w")

        tk.Label(self, text="* Pflichtfeld",
                 bg=C["bg2"], fg=C["fg_dim"], font=("Monospace", 8),
        ).pack(anchor="w", padx=16)

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=16, pady=8)

        bf = tk.Frame(self, bg=C["bg2"])
        bf.pack(padx=16, pady=(0, 14), anchor="e")

        tk.Button(bf, text="Abbrechen", command=self.destroy,
                  bg=C["bg3"], fg=C["fg_dim"],
                  activebackground=C["border"], relief="flat",
                  font=("Monospace", 10), padx=12, pady=5,
        ).pack(side="left", padx=(0, 8))

        self.erstellen_btn = tk.Button(bf, text="Repository erstellen",
                  command=self._erstellen,
                  bg=C["success"], fg=C["bg"],
                  activebackground="#81d4a0", relief="flat",
                  font=("Monospace", 10, "bold"), padx=12, pady=5)
        self.erstellen_btn.pack(side="left")

    def _erstellen(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Pflichtfeld",
                                   "Bitte einen Repository-Namen eingeben.",
                                   parent=self)
            return

        payload = {
            "name":        name,
            "description": self.desc_var.get().strip(),
            "private":     self.privat_var.get(),
            "auto_init":   self.init_var.get(),
        }
        gi = self.gitignore_var.get().strip()
        lz = self.lizenz_var.get().strip()
        if gi:
            payload["gitignores"] = gi
        if lz:
            payload["license"] = lz

        self.erstellen_btn.config(state="disabled", text="Erstelle ...")

        def api_call():
            try:
                repo = self.client.create_repo(self.org, payload)
                self.after(0, lambda: self._erfolg(repo["full_name"]))
            except requests.HTTPError as e:
                msg = http_fehler_text(e)
                self.after(0, lambda: self._fehler(msg))
            except Exception as e:
                self.after(0, lambda: self._fehler(str(e)))

        threading.Thread(target=api_call, daemon=True).start()

    def _erfolg(self, full_name):
        messagebox.showinfo("Erfolgreich erstellt",
                            "Repository '{}' wurde angelegt.".format(full_name),
                            parent=self)
        self.destroy()
        self.on_success()

    def _fehler(self, msg):
        messagebox.showerror("Fehler beim Erstellen", msg, parent=self)
        self.erstellen_btn.config(state="normal", text="Repository erstellen")


# ---------------------------------------------------------------------------
# Clone-Dialog
# ---------------------------------------------------------------------------
class CloneDialog(tk.Toplevel):
    def __init__(self, parent, org, repo_name, clone_url, token):
        super().__init__(parent)
        self.title("Klonen: " + org + "/" + repo_name)
        self.resizable(True, True)
        self.minsize(640, 440)
        self.configure(bg=C["bg2"])
        self.grab_set()

        self.org       = org
        self.repo_name = repo_name
        self.clone_url = clone_url
        self.token     = token
        self.prozess   = None
        self._laufend  = False

        self._baue_ui()
        self.protocol("WM_DELETE_WINDOW", self._schliessen)
        self._zentriere(parent)

    def _zentriere(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry("+{}+{}".format(x, y))

    def _baue_url(self):
        proto = self.proto_var.get()
        base  = self.clone_url
        if proto == "HTTPS + Token":
            p = urlparse(base)
            return urlunparse(p._replace(netloc=self.token + "@" + p.netloc))
        elif proto == "SSH":
            p    = urlparse(base)
            pfad = p.path.lstrip("/")
            return "git@{}:{}".format(p.netloc, pfad)
        else:
            return base

    def _aktualisiere_vorschau(self, *_):
        url     = self._baue_url()
        anzeige = url.replace(self.token, "***") if self.token in url else url
        self.vorschau_var.set(anzeige)

    def _baue_ui(self):
        tk.Label(self, text="  Klonen: " + self.org + "/" + self.repo_name,
                 font=("Monospace", 12, "bold"),
                 bg=C["bg2"], fg=C["accent"],
        ).pack(padx=16, pady=(14, 8), anchor="w")

        opt = tk.Frame(self, bg=C["bg2"])
        opt.pack(fill="x", padx=16, pady=(0, 4))

        tk.Label(opt, text="Protokoll:",
                 bg=C["bg2"], fg=C["fg_dim"],
                 font=("Monospace", 9)).grid(row=0, column=0, sticky="w", padx=(0, 6))

        self.proto_var = tk.StringVar(value="HTTPS + Token")
        proto_cb = ttk.Combobox(opt, textvariable=self.proto_var,
                                values=["HTTPS + Token", "HTTPS anonym", "SSH"],
                                state="readonly", width=16, font=("Monospace", 9))
        proto_cb.grid(row=0, column=1, padx=(0, 20))
        proto_cb.bind("<<ComboboxSelected>>", self._aktualisiere_vorschau)

        tk.Label(opt, text="Zielverzeichnis:",
                 bg=C["bg2"], fg=C["fg_dim"],
                 font=("Monospace", 9)).grid(row=0, column=2, sticky="w", padx=(0, 6))

        self.ziel_var = tk.StringVar(value=str(CLONE_ZIEL))
        tk.Entry(opt, textvariable=self.ziel_var, width=28,
                 bg=C["bg3"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=("Monospace", 9),
        ).grid(row=0, column=3, padx=(0, 4))

        tk.Button(opt, text="...", command=self._verzeichnis_waehlen,
                  bg=C["bg3"], fg=C["accent"],
                  relief="flat", font=("Monospace", 9), padx=6,
        ).grid(row=0, column=4)

        vf = tk.Frame(self, bg=C["bg3"])
        vf.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(vf, text=" $ git clone ",
                 bg=C["bg3"], fg=C["fg_dim"], font=("Monospace", 9)).pack(side="left")
        self.vorschau_var = tk.StringVar()
        self._aktualisiere_vorschau()
        tk.Label(vf, textvariable=self.vorschau_var,
                 bg=C["bg3"], fg=C["warning"], font=("Monospace", 9)).pack(side="left")

        tf = tk.Frame(self, bg=C["bg"])
        tf.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        self.ausgabe = tk.Text(tf, bg=C["term_bg"], fg=C["term_fg"],
                               font=("Monospace", 9), relief="flat",
                               state="disabled", wrap="word", pady=6, padx=8)
        self.ausgabe.tag_configure("ok",   foreground=C["success"])
        self.ausgabe.tag_configure("err",  foreground=C["danger"])
        self.ausgabe.tag_configure("info", foreground=C["accent"])
        self.ausgabe.tag_configure("dim",  foreground=C["fg_dim"])

        sb = ttk.Scrollbar(tf, orient="vertical", command=self.ausgabe.yview)
        self.ausgabe.configure(yscrollcommand=sb.set)
        self.ausgabe.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._print("Bereit - " + self.org + "/" + self.repo_name + "\n", "info")
        self._print("Ziel:  " + str(CLONE_ZIEL) + "/" + self.repo_name + "\n", "dim")

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=16, pady=(0, 6))

        bf = tk.Frame(self, bg=C["bg2"])
        bf.pack(fill="x", padx=16, pady=(0, 14))

        self.abbruch_btn = tk.Button(bf, text="Abbrechen",
                                     command=self._schliessen,
                                     bg=C["bg3"], fg=C["fg_dim"],
                                     activebackground=C["border"], relief="flat",
                                     font=("Monospace", 10), padx=12, pady=5)
        self.abbruch_btn.pack(side="left")

        self.clone_btn = tk.Button(bf, text="  Jetzt klonen",
                                   command=self._starte_clone,
                                   bg=C["accent"], fg=C["bg"],
                                   activebackground=C["accent2"], relief="flat",
                                   font=("Monospace", 10, "bold"), padx=12, pady=5)
        self.clone_btn.pack(side="right")

    def _verzeichnis_waehlen(self):
        verz = filedialog.askdirectory(title="Zielverzeichnis waehlen",
                                       initialdir=self.ziel_var.get(), parent=self)
        if verz:
            self.ziel_var.set(verz)
            self._print("Ziel geaendert: " + verz + "\n", "dim")

    def _starte_clone(self):
        if self._laufend:
            return

        ziel_pfad = Path(self.ziel_var.get())
        try:
            ziel_pfad.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Fehler",
                                 "Verzeichnis konnte nicht erstellt werden:\n" + str(e),
                                 parent=self)
            return

        repo_pfad = ziel_pfad / self.repo_name
        if repo_pfad.exists():
            if not messagebox.askyesno("Verzeichnis existiert",
                                       "'" + str(repo_pfad) + "' existiert bereits.\n"
                                       "Trotzdem fortfahren?", parent=self):
                return

        clone_url = self._baue_url()
        self._laufend = True
        self.clone_btn.config(state="disabled", text="Klone ...")
        self.progress.start(12)
        self._print("\n$ git clone [url] " + self.repo_name + "\n", "info")

        def run():
            try:
                env  = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                proc = subprocess.Popen(
                    ["git", "clone", "--progress", clone_url, str(repo_pfad)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True, bufsize=1, env=env,
                )
                self.prozess = proc
                for zeile in proc.stdout:
                    self.after(0, lambda z=zeile: self._print(z))
                proc.wait()
                rc = proc.returncode
                self.after(0, lambda: self._fertig(rc, repo_pfad))
            except FileNotFoundError:
                self.after(0, lambda: self._fehler(
                    "git nicht gefunden.\nInstallation: sudo apt install git"))
            except Exception as e:
                self.after(0, lambda: self._fehler(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _fertig(self, rc, repo_pfad):
        self._laufend = False
        self.progress.stop()
        self.prozess  = None
        if rc == 0:
            self._print("\nErfolgreich geklont nach:\n  " + str(repo_pfad) + "\n", "ok")
            self.clone_btn.config(text="Fertig - Schliessen",
                                  bg=C["success"], fg=C["bg"],
                                  state="normal", command=self.destroy)
            self.abbruch_btn.config(text="Schliessen")
        else:
            self._print("\ngit clone fehlgeschlagen (Exit-Code " + str(rc) + ")\n", "err")
            self.clone_btn.config(state="normal", text="Erneut versuchen",
                                  bg=C["warning"], fg=C["bg"],
                                  command=self._starte_clone)

    def _fehler(self, msg):
        self._laufend = False
        self.progress.stop()
        self._print("\nFehler: " + msg + "\n", "err")
        self.clone_btn.config(state="normal", text="Erneut versuchen",
                              bg=C["warning"], fg=C["bg"],
                              command=self._starte_clone)

    def _print(self, text, tag=""):
        self.ausgabe.config(state="normal")
        self.ausgabe.insert("end", text, tag)
        self.ausgabe.see("end")
        self.ausgabe.config(state="disabled")

    def _schliessen(self):
        if self._laufend and self.prozess:
            if not messagebox.askyesno("Clone abbrechen?",
                                       "Clone laeuft noch. Wirklich abbrechen?",
                                       parent=self):
                return
            try:
                self.prozess.terminate()
            except Exception:
                pass
        self.destroy()


# ---------------------------------------------------------------------------
# Haupt-Applikation
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gitea Repository Manager")
        self.geometry("980x640")
        self.minsize(700, 480)
        self.configure(bg=C["bg"])

        # WICHTIG: self.cfg verwenden, NICHT self.config!
        # tk.Tk hat eine eingebaute Methode config() - ein gleichnamiges
        # Attribut wuerde diese ueberschreiben und den Start crashen.
        self.client = None
        self.cfg    = {}
        self.repos  = []

        self._style_setup()
        self._baue_menue()
        self._baue_fenster()

        saved = lade_config()
        if saved:
            self._verbinden(saved)
        else:
            self.after(100, self._oeffne_konfig_dialog)

    def _style_setup(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview",
                    background=C["bg2"], foreground=C["fg"],
                    fieldbackground=C["bg2"], borderwidth=0,
                    rowheight=26, font=("Monospace", 9))
        s.configure("Treeview.Heading",
                    background=C["bg3"], foreground=C["accent"],
                    borderwidth=0, font=("Monospace", 9, "bold"))
        s.map("Treeview",
              background=[("selected", C["bg3"])],
              foreground=[("selected", C["accent"])])
        s.configure("TCombobox",
                    fieldbackground=C["bg3"], background=C["bg3"],
                    foreground=C["fg"], selectbackground=C["bg3"],
                    selectforeground=C["fg"])
        s.configure("Vertical.TScrollbar",
                    background=C["bg3"], troughcolor=C["bg2"],
                    borderwidth=0, arrowsize=12)

    def _baue_menue(self):
        mbar = tk.Menu(self, bg=C["bg2"], fg=C["fg"],
                       activebackground=C["bg3"], activeforeground=C["accent"])

        dm = tk.Menu(mbar, tearoff=0, bg=C["bg2"], fg=C["fg"],
                     activebackground=C["bg3"], activeforeground=C["accent"])
        dm.add_command(label="Einstellungen", command=self._oeffne_konfig_dialog)
        dm.add_separator()
        dm.add_command(label="Beenden", command=self.destroy)
        mbar.add_cascade(label="Datei", menu=dm)

        hm = tk.Menu(mbar, tearoff=0, bg=C["bg2"], fg=C["fg"],
                     activebackground=C["bg3"], activeforeground=C["accent"])
        hm.add_command(label="Ueber...", command=self._zeige_ueber)
        mbar.add_cascade(label="Hilfe", menu=hm)

        # Explizit die tk.Tk-Methode aufrufen (nicht self.cfg):
        tk.Tk.config(self, menu=mbar)

    def _baue_fenster(self):
        hdr = tk.Frame(self, bg=C["bg2"], pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  Gitea Repository Manager",
                 font=("Monospace", 15, "bold"),
                 bg=C["bg2"], fg=C["accent"],
        ).pack(side="left", padx=10)
        self.status_lbl = tk.Label(hdr, text="Nicht verbunden",
                                   font=("Monospace", 9),
                                   bg=C["bg2"], fg=C["fg_dim"])
        self.status_lbl.pack(side="right", padx=16)
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        tb = tk.Frame(self, bg=C["bg"], pady=8)
        tb.pack(fill="x", padx=12)

        tk.Label(tb, text="Organisation:",
                 bg=C["bg"], fg=C["fg_dim"],
                 font=("Monospace", 10)).pack(side="left")

        self.org_var = tk.StringVar()
        self.org_cb  = ttk.Combobox(tb, textvariable=self.org_var,
                                     state="readonly", width=24, font=("Monospace", 10))
        self.org_cb.pack(side="left", padx=(4, 12))
        self.org_cb.bind("<<ComboboxSelected>>", lambda _: self._lade_repos())

        self.refresh_btn = self._tbtn(tb, "Aktualisieren",
                                      self._lade_repos, C["bg3"], C["accent"])
        self.neu_btn     = self._tbtn(tb, "+ Neues Repository",
                                      self._oeffne_neues_repo_dialog, C["accent"], C["bg"])
        self.clone_btn   = self._tbtn(tb, "Klonen",
                                      self._clone_repo, C["bg3"], C["accent2"])

        tk.Label(tb, text="Suche:", bg=C["bg"], fg=C["fg_dim"],
                 font=("Monospace", 10)).pack(side="right")
        self.suche_var = tk.StringVar()
        self.suche_var.trace_add("write", lambda *_: self._filter_repos())
        tk.Entry(tb, textvariable=self.suche_var, width=22,
                 bg=C["bg3"], fg=C["fg"], insertbackground=C["fg"],
                 relief="flat", font=("Monospace", 10),
        ).pack(side="right", padx=(0, 6))

        tbl = tk.Frame(self, bg=C["bg"])
        tbl.pack(fill="both", expand=True, padx=12, pady=(4, 0))

        cols = ("name", "beschreibung", "sichtbarkeit",
                "sprache", "sterne", "aktualisiert")
        self.tree = ttk.Treeview(tbl, columns=cols,
                                  show="headings", selectmode="browse")

        for col, heading, w, anchor in [
            ("name",         "Repository",    200, "w"),
            ("beschreibung", "Beschreibung",  260, "w"),
            ("sichtbarkeit", "Sichtbarkeit",   90, "center"),
            ("sprache",      "Sprache",        100, "center"),
            ("sterne",       "Sterne",          60, "center"),
            ("aktualisiert", "Aktualisiert",   140, "center"),
        ]:
            self.tree.heading(col, text=heading,
                              command=lambda c=col: self._sortiere(c))
            self.tree.column(col, width=w, anchor=anchor, minwidth=40)

        self.tree.tag_configure("private", foreground=C["tag_priv"])
        self.tree.tag_configure("public",  foreground=C["tag_pub"])

        sb = ttk.Scrollbar(tbl, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.ctx = tk.Menu(self, tearoff=0, bg=C["bg2"], fg=C["fg"],
                           activebackground=C["bg3"], activeforeground=C["accent"])
        self.ctx.add_command(label="Klonen",       command=self._clone_repo)
        self.ctx.add_separator()
        self.ctx.add_command(label="URL kopieren", command=self._kopiere_url)
        self.ctx.add_command(label="Loeschen",     command=self._loesche_repo)

        self.tree.bind("<Button-3>", self._zeige_ctx)
        self.tree.bind("<Double-1>", lambda _: self._clone_repo())

        self.statusbar = tk.Label(self, text="Bereit.", anchor="w",
                                  bg=C["bg3"], fg=C["fg_dim"],
                                  font=("Monospace", 8), padx=8)
        self.statusbar.pack(fill="x", side="bottom")
        self._ui_aktiv(False)

    def _tbtn(self, parent, text, cmd, bg, fg):
        b = tk.Button(parent, text=text, command=cmd,
                      bg=bg, fg=fg,
                      activebackground=C["accent2"], activeforeground=C["bg"],
                      relief="flat", font=("Monospace", 10, "bold"), padx=10, pady=4)
        b.pack(side="left", padx=4)
        return b

    def _ui_aktiv(self, aktiv):
        st = "normal" if aktiv else "disabled"
        for w in (self.org_cb, self.refresh_btn, self.neu_btn, self.clone_btn):
            w.config(state=st)

    def _sb(self, text):
        self.statusbar.config(text=text)

    def _verbinden(self, cfg):
        self.cfg    = cfg
        self.client = GiteaClient(cfg["url"], cfg["token"])
        self._sb("Verbinde ...")

        def check():
            try:
                user = self.client.test_connection()
                orgs = self.client.get_orgs()
                self.after(0, lambda: self._nach_verbindung(user, orgs))
            except requests.HTTPError as e:
                msg = http_fehler_text(e)
                self.after(0, lambda: self._verbindungsfehler(msg))
            except Exception as e:
                self.after(0, lambda: self._verbindungsfehler(str(e)))

        threading.Thread(target=check, daemon=True).start()

    def _nach_verbindung(self, user, orgs):
        login = user.get("login", "?")
        self.status_lbl.config(
            text="Verbunden als {} | {}".format(login, self.cfg["url"]),
            fg=C["success"])
        namen = [o["username"] for o in orgs]
        self.org_cb["values"] = namen
        if namen:
            self.org_cb.current(0)
        self._ui_aktiv(True)
        self._sb("{} Organisation(en) geladen.".format(len(namen)))
        self._lade_repos()

    def _verbindungsfehler(self, msg):
        self.status_lbl.config(text="Verbindungsfehler", fg=C["danger"])
        self._sb("Verbindung fehlgeschlagen.")
        messagebox.showerror("Verbindungsfehler", msg, parent=self)

    def _lade_repos(self):
        org = self.org_var.get()
        if not org or not self.client:
            return
        self._sb("Lade Repositories fuer '" + org + "' ...")
        self.refresh_btn.config(state="disabled")

        def fetch():
            try:
                repos = self.client.get_repos(org)
                self.after(0, lambda: self._zeige_repos(repos))
            except requests.HTTPError as e:
                msg = http_fehler_text(e)
                self.after(0, lambda: self._lade_fehler(msg))
            except Exception as e:
                self.after(0, lambda: self._lade_fehler(str(e)))

        threading.Thread(target=fetch, daemon=True).start()

    def _zeige_repos(self, repos):
        self.repos = repos
        self.refresh_btn.config(state="normal")
        self._filter_repos()
        self._sb("{} Repository(ies) gefunden.".format(len(repos)))

    def _filter_repos(self):
        suche = self.suche_var.get().lower()
        self.tree.delete(*self.tree.get_children())
        for r in self.repos:
            name = r.get("name", "")
            if suche and suche not in name.lower():
                continue
            privat = r.get("private", False)
            tag    = "private" if privat else "public"
            sicht  = "Private" if privat else "Public"
            self.tree.insert("", "end", iid=name,
                values=(
                    name,
                    r.get("description", "") or "-",
                    sicht,
                    r.get("language",    "") or "-",
                    r.get("stars_count", 0),
                    format_datum(r.get("updated", "")),
                ),
                tags=(tag,),
            )

    def _lade_fehler(self, msg):
        self.refresh_btn.config(state="normal")
        self._sb("Fehler beim Laden.")
        messagebox.showerror("Ladefehler", msg, parent=self)

    def _sortiere(self, spalte):
        items = [(self.tree.set(k, spalte), k)
                 for k in self.tree.get_children("")]
        items.sort()
        for idx, (_, k) in enumerate(items):
            self.tree.move(k, "", idx)

    def _zeige_ctx(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.ctx.post(event.x_root, event.y_root)

    def _kopiere_url(self):
        sel = self.tree.selection()
        if not sel:
            return
        url = "{}/{}/{}".format(
            self.cfg.get("url", "").rstrip("/"),
            self.org_var.get(), sel[0])
        self.clipboard_clear()
        self.clipboard_append(url)
        self._sb("URL kopiert: " + url)

    def _clone_repo(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Hinweis",
                                "Bitte zuerst ein Repository auswaehlen.",
                                parent=self)
            return
        repo_name = sel[0]
        org       = self.org_var.get()
        repo_data = next((r for r in self.repos if r.get("name") == repo_name), None)
        if repo_data:
            clone_url = repo_data.get("clone_url", "")
        else:
            clone_url = "{}/{}/{}.git".format(
                self.cfg.get("url", "").rstrip("/"), org, repo_name)
        CloneDialog(self, org, repo_name, clone_url, self.cfg.get("token", ""))

    def _loesche_repo(self):
        sel = self.tree.selection()
        if not sel:
            return
        repo_name = sel[0]
        org       = self.org_var.get()

        if not messagebox.askyesno("Repository loeschen",
                                   "Soll '{}/{}' dauerhaft geloescht werden?\n\n"
                                   "Diese Aktion ist NICHT rueckgaengig!".format(
                                       org, repo_name),
                                   icon="warning", parent=self):
            return

        eingabe = simpledialog.askstring("Bestaetigung",
                                         "Repository-Namen eintippen: '{}'".format(repo_name),
                                         parent=self)
        if eingabe != repo_name:
            messagebox.showinfo("Abgebrochen",
                                "Name stimmt nicht ueberein. Abgebrochen.")
            return

        def loeschen():
            try:
                self.client.delete_repo(org, repo_name)
                self.after(0, lambda: self._nach_loeschen(repo_name))
            except requests.HTTPError as e:
                msg = http_fehler_text(e)
                self.after(0, lambda: messagebox.showerror("Fehler", msg, parent=self))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Fehler", str(e), parent=self))

        threading.Thread(target=loeschen, daemon=True).start()

    def _nach_loeschen(self, repo_name):
        self._sb("Repository '{}' geloescht.".format(repo_name))
        self._lade_repos()

    def _oeffne_konfig_dialog(self):
        KonfigDialog(self, lade_config(), callback=self._konfig_callback)

    def _konfig_callback(self, cfg):
        if cfg:
            self._verbinden(cfg)

    def _oeffne_neues_repo_dialog(self):
        org = self.org_var.get()
        if not org:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Organisation auswaehlen.")
            return
        NeuesRepoDialog(self, org, self.client, on_success=self._lade_repos)

    def _zeige_ueber(self):
        messagebox.showinfo("Ueber",
                            "Gitea Repository Manager  v1.2\n\n"
                            "Abhaengigkeiten: Python 3.10+, requests\n"
                            "Systemvoraussetzung: git (sudo apt install git)",
                            parent=self)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
