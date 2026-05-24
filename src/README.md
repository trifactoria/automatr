# Automatr Frontend

This directory contains the Next.js control panel for Automatr. The full project
setup, backend commands, security notes, and smoke-check instructions live in the
root [README.md](../README.md).

## Local Development

```bash
npm ci
npm run dev
```

The frontend expects the Automatr host API to be available locally. By default,
use the backend at `http://127.0.0.1:8766` and open the UI at
`http://127.0.0.1:3000`.

## Checks

```bash
npm run lint
npm run build
```
