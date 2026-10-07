#!/bin/sh
# Reload the aaPanel nginx after certbot renews a certificate, only if the configuration is valid.
/www/server/nginx/sbin/nginx -t -q && /etc/init.d/nginx reload
