import assert from "node:assert/strict";
import test from "node:test";
import { createUploadItem } from "../src/components/upload/uploadQueue.ts";

function sourceFile(path: string, content = "customer,amount\nAlice,10\n") {
  const file = new File([content], path.split("/").pop()!, { lastModified: 123 });
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
}

test("same file selected again has the same key; different folders keep same-name files", () => {
  const east = createUploadItem(sourceFile("资料/华东/销售.csv"));
  const eastAgain = createUploadItem(sourceFile("资料/华东/销售.csv"));
  const south = createUploadItem(sourceFile("资料/华南/销售.csv"));
  assert.equal(east.id, eastAgain.id);
  assert.notEqual(east.id, south.id);
  assert.equal(east.status, "pending");
  assert.equal(south.status, "pending");
});

test("all supported extensions accept uppercase names", () => {
  for (const name of ["Sales.CSV", "Sales.XLSX", "Report.PDF", "Report.DOCX"]) {
    assert.equal(createUploadItem(sourceFile(name)).status, "pending", name);
  }
});

test("unsupported, empty, system and Office temporary files are skipped with reasons", () => {
  for (const name of ["readme.txt", ".DS_Store", "Thumbs.db", "~$report.xlsx", "._report.pdf", "__MACOSX/report.pdf"]) {
    const item = createUploadItem(sourceFile(name));
    assert.equal(item.status, "skipped", name);
    assert.ok(item.message, name);
  }
  assert.match(createUploadItem(sourceFile("empty.csv", "")).message!, /为空/);
});

test("single-file size boundary accepts 30 MB and skips larger files", () => {
  const data = new Uint8Array(30 * 1024 * 1024);
  assert.equal(createUploadItem(new File([data], "limit.csv")).status, "pending");
  const oversized = createUploadItem(new File([data, "x"], "oversize.csv"));
  assert.equal(oversized.status, "skipped");
  assert.match(oversized.message!, /30 MB/);
});
