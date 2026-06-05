// Shared message types between popup, content script, and background script

export type ExtMessage =
  | { action: "findAndSave" }
  | { action: "savePdf"; filename: string; base64: string }
  | { action: "status"; text: string; done?: boolean };
