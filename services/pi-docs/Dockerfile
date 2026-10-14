FROM node:24-bookworm-slim

ARG PI_VERSION=0.83.0

RUN npm install --global --ignore-scripts "@earendil-works/pi-coding-agent@${PI_VERSION}" \
    && npm install --prefix /app --omit=dev --ignore-scripts typebox@1.3.7 \
    && groupadd --gid 10001 pi \
    && useradd --uid 10001 --gid pi --create-home --shell /usr/sbin/nologin pi \
    && mkdir -p /app /docs /home/pi/.pi/agent \
    && chown -R pi:pi /app /home/pi/.pi

COPY --chown=pi:pi extension /app/extension
COPY --chown=pi:pi policy.md /app/policy.md
COPY --chown=pi:pi entrypoint.mjs /app/entrypoint.mjs

ENV DOCS_ROOT=/docs \
    HOME=/home/pi \
    PI_OFFLINE=1

USER pi
WORKDIR /docs

ENTRYPOINT ["node", "/app/entrypoint.mjs"]
