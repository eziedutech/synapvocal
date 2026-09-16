# Node 24 is the current Active LTS. Node 26 becomes LTS on 2026-10-28, after the hackathon.
FROM node:24.21.0-alpine AS dev-deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24.21.0-alpine AS prod-deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM node:24.21.0-alpine AS build
WORKDIR /app
ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
COPY --from=dev-deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24.21.0-alpine
WORKDIR /app
ARG GIT_SHA=dev
ENV NODE_ENV=production GIT_SHA=${GIT_SHA} PORT=3000
COPY package.json package-lock.json ./
COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=build /app/build ./build
EXPOSE 3000
CMD ["npm", "run", "start"]
