FROM node:24-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build
# vite preview serves dist/ and proxies /api to API_TARGET (see vite.config.ts)
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "4173", "--strictPort"]
