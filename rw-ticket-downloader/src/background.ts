import type { ExtMessage } from "./types";
import * as pdfjsLib from "pdfjs-dist";

// Point the worker to the bundled copy in the extension
pdfjsLib.GlobalWorkerOptions.workerSrc = browser.runtime.getURL("pdf.worker.min.js");

function base64ToUint8Array(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function pdfToJpeg(data: Uint8Array): Promise<Blob> {
  const loadingTask = pdfjsLib.getDocument({ data });
  const pdf = await loadingTask.promise;
  const page = await pdf.getPage(1);

  const SCALE = 2.0;
  const viewport = page.getViewport({ scale: SCALE });

  const canvas = new OffscreenCanvas(viewport.width, viewport.height);
  const ctx = canvas.getContext("2d") as OffscreenCanvasRenderingContext2D;

  await page.render({ canvasContext: ctx as unknown as CanvasRenderingContext2D, viewport }).promise;

  const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: 0.92 });
  return blob;
}

browser.runtime.onMessage.addListener(async (msg: ExtMessage) => {
  if (msg.action !== "savePdf") return;

  const { filename, base64 } = msg;

  try {
    const data = base64ToUint8Array(base64);
    const blob = await pdfToJpeg(data);
    const objectUrl = URL.createObjectURL(blob);

    await browser.downloads.download({
      url: objectUrl,
      filename,
      saveAs: false,
    });

    // Revoke after a short delay to allow the download to start
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch (err) {
    console.error("RW Ticket: failed to convert/save", filename, err);
  }
});
