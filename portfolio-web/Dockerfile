FROM node:22-slim AS build
WORKDIR /app
COPY portfolio-web/package*.json ./
COPY portfolio-web/ ./
RUN npm install --include=dev
RUN chmod +x ./node_modules/.bin/ng
RUN npm run build -- --configuration production

FROM node:22-slim AS runtime
WORKDIR /app

COPY --from=build /app/dist/portfolio-web ./dist/portfolio-web
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
# Les certificats sont montés au lancement (volume ./certs:/app/certs), jamais copiés dans l'image

EXPOSE 4443

CMD ["node", "dist/portfolio-web/server/server.mjs"]
