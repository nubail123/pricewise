FROM node:20-bookworm-slim AS frontend
WORKDIR /app
COPY retailers.json ./retailers.json
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY retailers.json ./retailers.json
COPY --from=frontend /app/site ./site
ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "server/app.py"]
