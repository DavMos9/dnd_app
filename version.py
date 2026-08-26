"""
Versione dell'applicazione — singola fonte di verità.

Aggiornare `APP_VERSION` prima di ogni rilascio, poi creare il tag git
corrispondente. La CI riscrive comunque questo file dal tag
(`.github/actions/inject-version`), quindi il valore committato conta solo per
l'esecuzione da sorgente: se qui resta un numero vecchio, `python main.py`
dichiara una versione più bassa di quella reale e il controllo aggiornamenti
annuncerebbe un aggiornamento inesistente. Per questo `core.update_checker`
disattiva il controllo quando gira da un checkout di sviluppo
(`is_dev_checkout()`) e un test asserisce che questo valore e
`pyproject.toml [project].version` coincidano.

Questo modulo NON importa nulla del progetto: ci si può importare sopra da
qualunque livello (inclusa la CI, che lo carica con `sys.path.insert(0, '.')`
per riusare `compute_build_number()` invece di riscrivere la formula in YAML).
"""

APP_VERSION = "0.3.7"
GITHUB_REPO = "DavMos9/dnd_app"  # owner/repo su GitHub

#: Prima versione firmata con la chiave di rilascio permanente.
#:
#: Fino alla versione precedente l'APK Android era firmato con il keystore di
#: DEBUG, rigenerato su ogni runner della CI: ogni release aveva una firma
#: diversa e Android rifiutava l'aggiornamento in loco
#: (INSTALL_FAILED_UPDATE_INCOMPATIBLE), obbligando a disinstallare e
#: reinstallare — con la perdita del database, `app_settings` incluso, quindi
#: anche del `device_id`. Da questa versione in avanti la firma è stabile e gli
#: aggiornamenti Android avvengono in loco.
#:
#: Attraversare questa soglia richiede UNA disinstallazione manuale: è il caso
#: che `core.update_checker.UpdateInfo.requires_reinstall` segnala, per mostrare
#: il flusso di backup guidato invece del normale download in-app. Vedi
#: RELEASE.md, sezione "Migrazione alla firma di rilascio".
FIRST_SIGNED_VERSION = "0.3.0"


def parse_version(version_str: str) -> tuple[int, ...]:
    """
    Converte '1.2.3' o 'v1.2.3' in (1, 2, 3) per confronto ordinale.

    Restituisce `(0,)` su qualunque input non numerico, così un confronto con
    una versione malformata non solleva mai: chi chiama vede semplicemente la
    versione più bassa possibile. Tollera un suffisso di pre-release
    ('0.2.16-rc1' → (0, 2, 16)) perché i tag di prova della firma lo usano.
    """
    # Ordine importante: prima gli spazi, poi il prefisso "v". Al contrario,
    # "  v0.2.15 " non perderebbe la "v" (lstrip si fermerebbe allo spazio
    # iniziale) e finirebbe in int("v0").
    clean = version_str.strip().lstrip("vV")
    clean = clean.split("-", 1)[0].split("+", 1)[0]
    try:
        return tuple(int(x) for x in clean.split("."))
    except ValueError:
        return (0,)


def compute_build_number(tag_or_version: str) -> int:
    """
    versionCode Android monotono derivato dal tag: major*1_000_000 +
    minor*1_000 + patch.

        v0.1.15 → 1_015      v0.2.15 → 2_015      v0.3.0 → 3_000
        v1.0.0  → 1_000_000

    Serve perché `pyproject.toml` aveva `build_number = 1` HARDCODED e la CI non
    lo iniettava: ogni APK mai rilasciato porta versionCode 1. Qualunque valore
    prodotto qui è > 1, quindi nessuna installazione esistente vede un
    downgrade. Monotono finché minor e patch restano < 1000.

    Il valore torna 0 su un tag malformato: la CI lo scriverebbe in
    `pyproject.toml` e la build Android fallirebbe rumorosamente (versionCode 0
    è minore di quello installato), che è preferibile a un numero inventato.
    """
    parts = parse_version(tag_or_version)
    if parts == (0,):
        return 0
    padded = (list(parts) + [0, 0, 0])[:3]
    major, minor, patch = padded
    return major * 1_000_000 + minor * 1_000 + patch
