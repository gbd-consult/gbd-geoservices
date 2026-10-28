#!/usr/bin/env bash
set -euo pipefail

# Erstellt per Vaultwarden/Bitwarden-API einen "Send" (One-Time-/Ephemeral-Secret)
# und gibt den Freigabe-Link aus.
#
# Sends werden clientseitig verschluesselt, bevor sie an den Server gehen.
# Deshalb nutzt dieses Script die offizielle Bitwarden-CLI ("bw"), die genau
# diese Verschluesselung korrekt implementiert, statt die Krypto von Hand
# gegen die REST-API nachzubauen.
#
# Der Text erreicht bw nur ueber stdin, als JSON fuer `bw send create`, nie als
# Argument: Argumente stehen fuer jeden Benutzer des Hosts in der Prozessliste
# (ps), solange bw laeuft. Das JSON baut python3, das den Text ebenfalls ueber
# stdin bekommt und das Send-Passwort ueber die Umgebung.

usage() {
  cat <<EOF
Verwendung: $(basename "$0") [Optionen] [TEXT]

Erstellt einen Vaultwarden-Send und gibt den Freigabe-Link aus.
TEXT kann als Argument oder ueber stdin uebergeben werden.

Mit --generate-key erzeugt das Script selbst einen API-Schluessel und sendet
ihn; es ist die einzige Stelle, an der Schluessel entstehen. Dann gibt es zwei
Zeilen aus, zuerst den Schluessel, dann den Link: fuer `manage.sh key-add`, das
den Schluessel registriert und nur den Link anzeigt.

Optionen:
  -s, --server URL       Vaultwarden-Server-URL (Standard: \$VAULTWARDEN_SERVER)
  -n, --name NAME        Name des Sends
  -d, --days N           Tage bis zur automatischen Loeschung (Standard: 7)
  -a, --max-access N     Maximale Anzahl an Zugriffen
      --password PASS    Zusaetzliches Passwort zum Oeffnen des Sends
      --hidden           Text beim Oeffnen zunaechst verbergen
      --logout           Nach Ausfuehrung komplett ausloggen (statt nur zu sperren)
      --generate-key     API-Schluessel erzeugen und senden; gibt Schluessel und Link aus
  -h, --help             Diese Hilfe anzeigen

Authentifizierung (fuer nicht-interaktive Nutzung per Umgebungsvariablen):
  VAULTWARDEN_SERVER              Server-URL, z.B. https://vault.example.com
  BW_CLIENTID, BW_CLIENTSECRET    API-Key-Login (empfohlen fuer Automatisierung,
                                  siehe Vaultwarden/Bitwarden Kontoeinstellungen)
  BW_PASSWORD                     Master-Passwort zum Entsperren des Tresors

Sind diese Variablen nicht gesetzt, fragt das Script interaktiv danach.

Beispiele:
  $(basename "$0") "mein geheimer Text"
  echo "geheim" | $(basename "$0") -n "API-Key" -d 1 -a 1
  VAULTWARDEN_SERVER=https://vault.example.com $(basename "$0") "secret"
EOF
}

SERVER="${VAULTWARDEN_SERVER:-}"
NAME=""
DAYS="7"
MAX_ACCESS=""
SEND_PASSWORD=""
HIDDEN="false"
DO_LOGOUT="false"
GENERATE_KEY="false"
TEXT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--server) SERVER="$2"; shift 2 ;;
    -n|--name) NAME="$2"; shift 2 ;;
    -d|--days) DAYS="$2"; shift 2 ;;
    -a|--max-access) MAX_ACCESS="$2"; shift 2 ;;
    --password) SEND_PASSWORD="$2"; shift 2 ;;
    --hidden) HIDDEN="true"; shift ;;
    --logout) DO_LOGOUT="true"; shift ;;
    --generate-key) GENERATE_KEY="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    *) TEXT="$1"; shift ;;
  esac
done

if [[ "$GENERATE_KEY" == "true" ]]; then
  if [[ -n "$TEXT" ]]; then
    echo "Fehler: --generate-key erzeugt den Text selbst; keinen TEXT angeben." >&2
    exit 1
  fi
  # 256 Zufallsbits, URL-sicher ohne Padding: der Schluessel reist auch als ?key=.
  TEXT="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n')"
fi

if [[ -z "$TEXT" ]]; then
  if [[ ! -t 0 ]]; then
    TEXT="$(cat)"
  fi
fi

if [[ -z "$TEXT" ]]; then
  echo "Fehler: Kein Text angegeben (Argument oder stdin erforderlich)." >&2
  usage
  exit 1
fi

command -v bw >/dev/null 2>&1 || {
  echo "Fehler: Die Bitwarden-CLI 'bw' ist nicht installiert (https://bitwarden.com/help/cli/)." >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || {
  echo "Fehler: python3 ist nicht installiert." >&2
  exit 1
}

if [[ -z "$SERVER" ]]; then
  echo "Fehler: Kein Vaultwarden-Server angegeben (--server oder VAULTWARDEN_SERVER)." >&2
  exit 1
fi

bw config server "$SERVER" >/dev/null

STATUS="$(bw status | sed -n 's/.*"status":"\([a-z]*\)".*/\1/p')"

if [[ "$STATUS" == "unauthenticated" ]]; then
  if [[ -n "${BW_CLIENTID:-}" && -n "${BW_CLIENTSECRET:-}" ]]; then
    bw login --apikey >/dev/null
  else
    # Auf stderr: wer die Ausgabe abfaengt (manage.sh), sieht die Abfrage trotzdem.
    bw login >&2
  fi
  STATUS="locked"
fi

if [[ "$STATUS" == "locked" ]]; then
  if [[ -n "${BW_PASSWORD:-}" ]]; then
    export BW_SESSION="$(bw unlock --passwordenv BW_PASSWORD --raw)"
  else
    export BW_SESSION="$(bw unlock --raw)"
  fi
fi

bw sync >/dev/null

# Die Vorlage von bw selbst, damit das JSON die Felder hat, die diese bw-Version erwartet.
TEMPLATE="$(bw send template send.text)"

SEND_JSON="$(printf '%s' "$TEXT" | SEND_PASSWORD="$SEND_PASSWORD" python3 -c '
import datetime, json, os, sys
template, name, days, max_access, hidden = sys.argv[1:6]
send = json.loads(template)
send["name"] = name or "Send"
send["text"] = {"text": sys.stdin.read(), "hidden": hidden == "true"}
deletion = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=int(days))
send["deletionDate"] = deletion.strftime("%Y-%m-%dT%H:%M:%S.000Z")
send["maxAccessCount"] = int(max_access) if max_access else None
send["password"] = os.environ.get("SEND_PASSWORD") or None
print(json.dumps(send))
' "$TEMPLATE" "$NAME" "$DAYS" "$MAX_ACCESS" "$HIDDEN")"

LINK="$(printf '%s' "$SEND_JSON" | bw encode | bw send create \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["accessUrl"])')"

if [[ "$DO_LOGOUT" == "true" ]]; then
  bw logout >/dev/null 2>&1 || true
else
  bw lock >/dev/null 2>&1 || true
fi

[[ "$GENERATE_KEY" == "true" ]] && echo "$TEXT"
echo "$LINK"
