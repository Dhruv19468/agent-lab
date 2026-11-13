#!/bin/sh
# Runs at container start (the nginx image runs every script in /docker-entrypoint.d/).
# With BASIC_AUTH_PASSWORD set, the whole site asks for a user name and password.
set -eu
if [ -n "${BASIC_AUTH_PASSWORD:-}" ]; then
    user="${BASIC_AUTH_USER:-lab}"
    printf '%s:%s\n' "$user" "$(openssl passwd -apr1 "$BASIC_AUTH_PASSWORD")" > /etc/nginx/.htpasswd
    printf 'auth_basic "Agent Lab";\nauth_basic_user_file /etc/nginx/.htpasswd;\n' > /etc/nginx/auth.conf
    echo "basic-auth: enabled for user $user"
else
    : > /etc/nginx/auth.conf
    echo "basic-auth: off (BASIC_AUTH_PASSWORD not set)"
fi
