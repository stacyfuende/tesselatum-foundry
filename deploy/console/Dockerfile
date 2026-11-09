FROM nginxinc/nginx-unprivileged:1.28-alpine

COPY console/index.html console/app.js console/styles.css /usr/share/nginx/html/
COPY deploy/console/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
