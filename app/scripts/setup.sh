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
#       rotates them daily and keeps a week.
#   /etc/cron.d/gbd-geoservices-v03
#       `manage.sh update` on Monday, Wednesday and Friday at 02:00 (UTC on
#       the server): imports serve_area and reloads, as the owner of this
#       directory, appending to data/cron.log. A job running this
#       manage.sh in that user's own crontab is removed first. Docker makes
#       data/ root's, so the log is created here: cron's shell could not
#       create it, and with no MTA on the host cron discards that error.
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
CRON_CONF=/etc/cron.d/$NAME
CRON_LOG=$BASE/data/cron.log
OPERATOR=$(stat -c %U "$BASE")
AREA=$(sed -n 's/^serve_area: *//p' "$BASE/config/options.yaml")
# Where the service name starts in the tag `$NAME-<service>`, 1-based.
SERVICE_FROM=$((${#NAME} + 2))

if [ -z "$AREA" ]; then
    echo "no serve_area in $BASE/config/options.yaml" >&2
    exit 2
fi

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
    rotate 7
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

touch "$CRON_LOG"
chown "$OPERATOR:" "$CRON_LOG"

# A job for this stack in the operator's own crontab would run beside the
# one below, and its import would fail because the first one is running.
if crontab -u "$OPERATOR" -l 2>/dev/null | grep -qF "$BASE/manage.sh"; then
    crontab -u "$OPERATOR" -l | grep -vF "$BASE/manage.sh" | crontab -u "$OPERATOR" -
    echo "removed the $BASE/manage.sh job from $OPERATOR's crontab"
fi
rm -f "$CRON_CONF"

cat > "$CRON_CONF" <<EOF
# Written by $BASE/setup.sh.

0 2 * * 1,3,5  $OPERATOR  $BASE/manage.sh update $AREA >> $CRON_LOG 2>&1
EOF

rsyslogd -N1 >/dev/null
systemctl restart rsyslog

echo "wrote $RSYSLOG_CONF, $LOGROTATE_CONF and $CRON_CONF; the services log to $LOG_DIR/"
