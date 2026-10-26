#!/bin/sh
#
# setup.sh -- prepare the server for the stack: once, as root.
#
#   sudo ./setup.sh
#
# deploy.sh copies it next to docker-compose.yml on the server. Run it once
# on a new server, and again when it changes; it overwrites what it wrote
# before.
#
# The services log to the host's syslog (docker-compose.yml, `logging:`),
# tagged with their container names. This writes:
#
#   /etc/rsyslog.d/30-gbd-geoservices-v03.conf
#       each container's lines into data/log/<service>.log (app.log,
#       postgres.log, pgbouncer.log, caddy.log) as `date | message`, and
#       not into /var/log/syslog as well: it sorts before 50-default.conf.
#   /etc/logrotate.d/gbd-geoservices-v03
#       rotates them daily and keeps two weeks.
#
# Without it the stack runs all the same, and its lines go to
# /var/log/syslog.
#
# rsyslog runs as syslog, so data/log is syslog's; the files are readable by
# everyone, so the operator can follow them without sudo. No key reaches
# them (DESIGN.md "Authentication"). Ubuntu ships the rsyslogd AppArmor
# profile disabled; enforced, it would refuse data/log, which is outside
# /var/log.

set -eu

NAME=gbd-geoservices-v03

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root: sudo $0" >&2
    exit 2
fi

BASE=$(cd "$(dirname "$0")" && pwd)
LOG_DIR=$BASE/data/log
RSYSLOG_CONF=/etc/rsyslog.d/30-$NAME.conf
LOGROTATE_CONF=/etc/logrotate.d/$NAME
# Where the service name starts in the tag `$NAME-<service>`, 1-based.
SERVICE_FROM=$((${#NAME} + 2))

if [ -e /etc/apparmor.d/usr.sbin.rsyslogd ] && [ ! -e /etc/apparmor.d/disable/usr.sbin.rsyslogd ]; then
    echo "warning: the rsyslogd AppArmor profile is enabled; rsyslog cannot write to $LOG_DIR" >&2
fi

mkdir -p "$LOG_DIR"
chown syslog:adm "$LOG_DIR"
chmod 755 "$LOG_DIR"

cat > "$RSYSLOG_CONF" <<EOF
# Written by $BASE/setup.sh.

template(name="$NAME-file" type="string"
         string="$LOG_DIR/%programname:$SERVICE_FROM:\$%.log")

template(name="$NAME-line" type="string"
         string="%timereported:::date-year%-%timereported:::date-month%-%timereported:::date-day% %timereported:::date-hour%:%timereported:::date-minute%:%timereported:::date-second% |%msg:::sp-if-no-1st-sp%%msg:::drop-last-lf%\n")

if \$programname startswith "$NAME-" then {
    action(type="omfile" dynaFile="$NAME-file" template="$NAME-line"
           fileOwner="syslog" fileGroup="adm" fileCreateMode="0644")
    stop
}
EOF

cat > "$LOGROTATE_CONF" <<EOF
# Written by $BASE/setup.sh.

$LOG_DIR/*.log {
    su syslog adm
    daily
    rotate 14
    missingok
    notifempty
    compress
    delaycompress
    sharedscripts
    postrotate
        /usr/lib/rsyslog/rsyslog-rotate
    endscript
}
EOF

rsyslogd -N1 >/dev/null
systemctl restart rsyslog

echo "wrote $RSYSLOG_CONF and $LOGROTATE_CONF; the services log to $LOG_DIR/"
