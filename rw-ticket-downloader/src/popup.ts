import type { ExtMessage } from "./types";

const btn = document.getElementById("btn") as HTMLButtonElement;
const status = document.getElementById("status") as HTMLParagraphElement;

// Listen for status updates from content/background scripts
browser.runtime.onMessage.addListener((msg: ExtMessage) => {
  if (msg.action === "status") {
    status.textContent = msg.text;
    if (msg.done) {
      btn.disabled = false;
    }
  }
});

btn.addEventListener("click", async () => {
  btn.disabled = true;
  status.textContent = "Поиск тикетов...";

  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    status.textContent = "Ошибка: нет активной вкладки";
    btn.disabled = false;
    return;
  }

  if (!tab.url?.includes("pass.rw.by")) {
    status.textContent = "Откройте страницу pass.rw.by";
    btn.disabled = false;
    return;
  }

  try {
    await browser.tabs.sendMessage(tab.id, { action: "findAndSave" } as ExtMessage);
  } catch {
    status.textContent = "Ошибка: обновите страницу и попробуйте снова";
    btn.disabled = false;
  }
});
