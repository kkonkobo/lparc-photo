# Static download page. The installers themselves live in GitHub Releases.
FROM nginxinc/nginx-unprivileged:1.27-alpine
ARG GIT_SHA=unknown
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY assets /usr/share/nginx/html/assets
USER root
# Images are cached for a week, by browsers and by Cloudflare in front of the site. Stamping every
# /assets/ address with this build's commit makes a changed image a new address, so it is never stale.
RUN printf '{"sha":"%s"}\n' "$GIT_SHA" > /usr/share/nginx/html/version.json \
 && sed -i -E "s#(/assets/[A-Za-z0-9._-]+)#\1?v=${GIT_SHA}#g" /usr/share/nginx/html/index.html
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/health || exit 1
