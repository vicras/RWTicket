import type { ExtMessage } from "./types";

function sendStatus(text: string, done = false): void {
  browser.runtime.sendMessage({ action: "status", text, done } as ExtMessage);
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

const MONTH_MAP: Record<string, string> = {
  "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
  "мая": "05", "июня": "06", "июля": "07", "августа": "08",
  "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
};

function getOrderMeta(): { orderNum: string; date: string } {
  // Order number from <h1 class="small">Заказ №17005825</h1>
  const h1 = document.querySelector<HTMLElement>("h1.small");
  const orderMatch = h1?.textContent?.match(/№(\d+)/);
  const orderNum = orderMatch ? orderMatch[1] : "unknown";

  // Date from .caption containing "Оплачен 05 июня 2026"
  const captions = Array.from(document.querySelectorAll<HTMLElement>(".caption"));
  const paidCaption = captions.find(el => el.textContent?.includes("Оплачен"));
  const dateMatch = paidCaption?.textContent?.match(/(\d{1,2})\s+(\S+)\s+(\d{4})/);
  let date = "unknown-date";
  if (dateMatch) {
    const day = dateMatch[1].padStart(2, "0");
    const month = MONTH_MAP[dateMatch[2]] ?? "00";
    const year = dateMatch[3];
    date = `${year}-${month}-${day}`;
  }

  return { orderNum, date };
}

function findPdfLinks(): string[] {
  const anchors = Array.from(document.querySelectorAll<HTMLAnchorElement>("a[href]"));
  const seen = new Set<string>();
  const urls: string[] = [];

  for (const a of anchors) {
    const href = a.href;
    if (!href || seen.has(href)) continue;
    if (!href.startsWith("http://") && !href.startsWith("https://")) continue;
    if (href.endsWith("#")) continue;

    const lower = href.toLowerCase();
    const isPdf =
      lower.includes("pdf=1") ||
      lower.endsWith(".pdf") ||
      lower.includes(".pdf?") ||
      lower.includes("/ticket/pdf") ||
      lower.includes("/pdf/ticket");

    if (isPdf) {
      seen.add(href);
      urls.push(href);
    }
  }

  return urls;
}

browser.runtime.onMessage.addListener(async (msg: ExtMessage) => {
  if (msg.action !== "findAndSave") return;

  const urls = findPdfLinks();

  if (urls.length === 0) {
    sendStatus("PDF-билеты не найдены на этой странице", true);
    return;
  }

  sendStatus(`Найдено ${urls.length} билет(ов). Скачивание...`);

  let saved = 0;
  let failed = 0;

  for (let i = 0; i < urls.length; i++) {
    const url = urls[i];
    sendStatus(`Обработка ${i + 1}/${urls.length}...`);

    try {
      const response = await fetch(url, { credentials: "include" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const buffer = await response.arrayBuffer();
      const base64 = arrayBufferToBase64(buffer);
      const { orderNum, date } = getOrderMeta();
      const filename = `ticket_${date}_${orderNum}_${i + 1}.jpg`;

      await browser.runtime.sendMessage({
        action: "savePdf",
        filename,
        base64,
      } as ExtMessage);

      saved++;
    } catch (err) {
      console.error("RW Ticket: failed to fetch", url, err);
      failed++;
    }
  }

  const parts = [`Готово: сохранено ${saved}`];
  if (failed > 0) parts.push(`ошибок ${failed}`);
  sendStatus(parts.join(", "), true);
});
