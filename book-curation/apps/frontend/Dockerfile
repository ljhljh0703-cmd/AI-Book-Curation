# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
# 수정 포인트: BuildKit cache mount로 npm tarball cache를 빌드 간 재사용합니다.
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY . .

ARG VITE_USE_RELATIVE_API=true
ARG VITE_API_BASE_URL=
ARG VITE_OAUTH_BASE_URL=
ARG VITE_PUBLIC_SITE_URL=https://book.taeo-dev.com

ENV VITE_USE_RELATIVE_API=${VITE_USE_RELATIVE_API}
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_OAUTH_BASE_URL=${VITE_OAUTH_BASE_URL}
ENV VITE_PUBLIC_SITE_URL=${VITE_PUBLIC_SITE_URL}

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
