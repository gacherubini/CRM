# VM 3 — Python APIs + portal + catalogo + site + nginx edge
# n8n NÃO entra nesta imagem (npm install-g demora 10–20min e quebra o deploy).
# n8n roda no app n8n2037 (imagem oficial n8nio/n8n) — fly.n8n.toml
#
# Deploy: fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    REVY_APP_IMAGE_REV=8

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      nginx \
      supervisor \
      tini \
    && rm -rf /var/lib/apt/lists/* \
    && nginx -v

COPY deploy/fly/3vm/requirements-app.txt /tmp/requirements-app.txt
RUN pip install --no-cache-dir -r /tmp/requirements-app.txt

COPY chatbot-api/app /srv/chatbot/app
COPY chatbot-api/alembic /srv/chatbot/alembic
COPY chatbot-api/alembic.ini /srv/chatbot/alembic.ini

COPY estoque-api/app /srv/estoque/app
COPY estoque-api/alembic /srv/estoque/alembic
COPY estoque-api/alembic.ini /srv/estoque/alembic.ini

COPY portal-gestao/app /srv/portal/app
COPY portal-gestao/alembic /srv/portal/alembic
COPY portal-gestao/alembic.ini /srv/portal/alembic.ini

COPY revy-trafego/app /srv/revy-trafego/app
COPY revy-trafego/alembic /srv/revy-trafego/alembic
COPY revy-trafego/alembic.ini /srv/revy-trafego/alembic.ini

COPY catalogo-publico/app /srv/catalogo/app

COPY motor-simulacao/app /srv/motor/app
COPY motor-simulacao/alembic /srv/motor/alembic
COPY motor-simulacao/alembic.ini /srv/motor/alembic.ini

COPY site/index.html /srv/site/html/index.html
COPY site/assets /srv/site/html/assets
COPY deploy/fly/3vm/site-nginx.conf /etc/nginx/sites-available/site.conf
COPY deploy/fly/3vm/nginx-edge.conf /etc/nginx/edge.conf
COPY deploy/fly/3vm/nginx.conf /etc/nginx/nginx.conf
RUN mkdir -p /etc/nginx/sites-enabled /etc/nginx/sites-available \
               /data/portal /data/revy-trafego /data/catalogo /data/estoque/media \
               /data/motor/screenshots /data/motor/storage_state \
               /var/log/nginx /var/lib/nginx /run \
    && rm -f /etc/nginx/sites-enabled/default \
    && ln -sf /etc/nginx/sites-available/site.conf /etc/nginx/sites-enabled/site.conf \
    && nginx -t

COPY deploy/fly/3vm/supervisord.conf /etc/supervisord.conf
COPY deploy/fly/3vm/healthz.py /srv/healthz.py
COPY deploy/fly/3vm/entrypoint-app.sh /srv/entrypoint-app.sh
COPY deploy/fly/3vm/estoque-entrypoint.sh /srv/scripts/estoque-entrypoint.sh
COPY deploy/fly/3vm/motor-entrypoint.sh /srv/scripts/motor-entrypoint.sh
COPY deploy/fly/3vm/run-chatbot.sh /srv/scripts/run-chatbot.sh
COPY deploy/fly/3vm/run-estoque.sh /srv/scripts/run-estoque.sh
COPY deploy/fly/3vm/run-portal.sh /srv/scripts/run-portal.sh
COPY deploy/fly/3vm/run-revy-trafego.sh /srv/scripts/run-revy-trafego.sh
COPY deploy/fly/3vm/run-catalogo.sh /srv/scripts/run-catalogo.sh
COPY deploy/fly/3vm/run-motor.sh /srv/scripts/run-motor.sh

RUN chmod +x /srv/entrypoint-app.sh /srv/scripts/*.sh

EXPOSE 8080

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/srv/entrypoint-app.sh"]
