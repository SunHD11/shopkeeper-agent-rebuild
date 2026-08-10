# syntax=docker/dockerfile:1

FROM node:24-alpine AS builder

WORKDIR /app

# 与 packageManager 保持一致，冻结安装保证 CI、开发机和镜像使用同一依赖图。
RUN npm install --global pnpm@10.33.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY index.html postcss.config.js tailwind.config.ts ./
COPY tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts ./
COPY src ./src
RUN pnpm build

# 非 root Nginx 监听 8080，前端容器不需要系统级权限。
FROM nginxinc/nginx-unprivileged:1.29-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=12 \
    CMD wget -q -O - http://127.0.0.1:8080/healthz >/dev/null || exit 1
