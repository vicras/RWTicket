# Firefox Extension: RW Ticket Downloader (TypeScript)

> Язык: **TypeScript** → компилируется в JS. Сборщик: **webpack**.

## Context

Firefox-плагин для Android, который:
1. При нажатии кнопки тулбара — ищет все PDF-ссылки на тикеты на текущей странице pass.rw.by
2. Скачивает каждый PDF, рендерит его первую страницу в JPEG
3. Сохраняет JPEG в папку Downloads (откуда доступна из галереи)

Сайт: https://pass.rw.by/ru/ — портал билетов Белорусской железной дороги.

---

## Project Structure

```
rw-ticket-downloader/
├── package.json
├── tsconfig.json
├── webpack.config.js       # bundles TS → dist/
├── src/
│   ├── background.ts       # PDF→image converter + downloader
│   ├── content.ts          # PDF link finder + fetcher (runs on pass.rw.by)
│   ├── popup.ts            # Toolbar popup logic
│   └── types.d.ts          # shared message types
├── public/
│   ├── manifest.json       # MV2
│   ├── popup.html
│   └── icons/
│       ├── icon48.png
│       └── icon96.png
└── dist/                   # build output (loaded into Firefox)
    ├── manifest.json
    ├── background.js
    ├── content.js
    ├── popup.js
    ├── popup.html
    └── pdf.worker.min.js   # copied from pdfjs-dist
```

---

## Implementation Steps

### 1. Tooling setup
- `package.json` с devDeps: `typescript`, `webpack`, `ts-loader`, `copy-webpack-plugin`, `@types/firefox-webext-browser`, `pdfjs-dist`
- `tsconfig.json`: target ES2020, lib: ES2020/DOM, strict: true
- `webpack.config.js`: 3 entry points (`background`, `content`, `popup`), copies `public/` и `pdf.worker.min.js` в `dist/`

### 2. `src/types.d.ts` — общие типы сообщений

```ts
export type ExtMessage =
  | { action: "findAndSave" }
  | { action: "savePdf"; filename: string; base64: string }
  | { action: "status"; text: string };
```

### 3. `public/manifest.json` (MV2)

```json
{
  "manifest_version": 2,
  "name": "RW Ticket Downloader",
  "version": "1.0",
  "permissions": ["activeTab", "downloads", "*://pass.rw.by/*"],
  "browser_action": { "default_popup": "popup.html" },
  "content_scripts": [{ "matches": ["*://pass.rw.by/*"], "js": ["content.js"] }],
  "background": { "scripts": ["background.js"] },
  "web_accessible_resources": ["pdf.worker.min.js"]
}
```

### 4. `src/popup.ts`
- При DOMContentLoaded: получить активный таб, показать кнопку
- Клик → `browser.tabs.sendMessage(tabId, {action: "findAndSave"})`
- Слушать сообщения `{action: "status"}` → показывать в `<p id="status">`

### 5. `src/content.ts`
- Слушать `{action: "findAndSave"}`
- Сканировать DOM: `document.querySelectorAll('a[href]')` → фильтровать href по `.pdf`, `download`, `ticket`
- Для каждого URL: `fetch(url, {credentials: "include"})` → `arrayBuffer()` → конвертировать в base64
- Отправить `{action: "savePdf", filename: "ticket_N.jpg", base64}` в background через `browser.runtime.sendMessage`
- Отправить `{action: "status", text: "Найдено N тикетов..."}` обратно в popup

### 6. `src/background.ts`
- Импортировать `pdfjs-dist`, установить `workerSrc`
- Слушать `{action: "savePdf", filename, base64}`
- Декодировать base64 → `Uint8Array` → `pdfjsLib.getDocument({data})` → `getPage(1)`
- Рендерить в `OffscreenCanvas` (scale 2.0 для качества)
- `canvas.convertToBlob({type: "image/jpeg", quality: 0.92})` → `URL.createObjectURL()`
- `browser.downloads.download({url, filename, saveAs: false})`

---

## Flow (CORS-safe)

```
User clicks toolbar button
    → popup.ts → browser.tabs.sendMessage({action: "findAndSave"})
        → content.ts: scans DOM for PDF links
        → fetch(pdfUrl, {credentials: "include"})  ← same-origin, cookies included
        → arrayBuffer → base64
        → browser.runtime.sendMessage({action: "savePdf", filename, base64})
            → background.ts: base64 → Uint8Array → PDF.js → OffscreenCanvas → JPEG blob
            → browser.downloads.download({url: objectURL, filename})
                → Downloads folder → Gallery
```

---

## Key Technical Notes

- **MV2**: Firefox Android не поддерживает MV3 — использовать MV2
- **CORS-safe fetch**: `content.ts` делает fetch в контексте страницы (same-origin + куки) — нет CORS-проблем
- **OffscreenCanvas**: доступен в FF background scripts (не Service Worker), поддерживает `convertToBlob()`
- **pdfjs-dist v3.x**: последняя версия, хорошо работающая в MV2 background scripts
- **Только 1-я страница** каждого PDF рендерится (тикеты всегда 1 страница)

---

## Verification

1. `npm run build` → папка `dist/` заполнена
2. Firefox Android → `about:debugging` → Load Temporary Add-on → выбрать `dist/manifest.json`
3. Войти на pass.rw.by, перейти на страницу заказов
4. Нажать кнопку тулбара → popup открывается → нажать "Скачать тикеты"
5. Статус: "Найдено N тикетов, сохранено"
6. JPEG файлы появляются в папке Downloads / галерее
