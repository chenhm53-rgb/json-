const DEFAULT_CHUNK_SIZE = 10000;

function clampChunkSize(value) {
  const parsed = Number.parseInt(String(value).replace(/[^\d]/g, ''), 10);
  if (!Number.isFinite(parsed) || parsed < 1) return DEFAULT_CHUNK_SIZE;
  return Math.min(parsed, 1000000);
}

function baseName(fileName) {
  return String(fileName || 'email')
    .replace(/\.[^.]+$/g, '')
    .replace(/[^\w\u4e00-\u9fa5-]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 80) || 'email';
}

function formatChunkName(fileName, chunkIndex, chunkTotal) {
  const suffix = String(chunkIndex).padStart(Math.max(3, String(chunkTotal).length), '0');
  return `${baseName(fileName)}_part_${suffix}.txt`;
}

function makeChunk(lines, fileName, chunkIndex, chunkTotal) {
  const text = `${lines.join('\n')}\n`;
  return {
    id: `${fileName}-${chunkIndex}-${crypto.randomUUID()}`,
    fileName: formatChunkName(fileName, chunkIndex, chunkTotal),
    sourceName: fileName,
    index: chunkIndex,
    count: lines.length,
    bytes: new Blob([text]).size,
    blob: new Blob([text], { type: 'text/plain;charset=utf-8' }),
    firstLine: lines[0] || '',
    lastLine: lines[lines.length - 1] || '',
  };
}

export function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function getChunkSize(value) {
  return clampChunkSize(value);
}

export async function splitFileByLines(
  file,
  { chunkSize = DEFAULT_CHUNK_SIZE, encoding = 'utf-8', skipEmpty = true, onProgress } = {},
) {
  const safeChunkSize = clampChunkSize(chunkSize);
  const decoder = new TextDecoder(encoding);
  const reader = file.stream().getReader();
  const chunks = [];
  let buffer = '';
  let currentLines = [];
  let bytesRead = 0;
  let totalLines = 0;

  const emitProgress = () => {
    onProgress?.({
      bytesRead,
      totalBytes: file.size,
      progress: file.size ? Math.min(99, Math.round((bytesRead / file.size) * 100)) : 0,
      totalLines,
    });
  };

  const pushLine = (rawLine) => {
    const line = rawLine.replace(/\r$/, '');
    if (skipEmpty && !line.trim()) return;
    currentLines.push(line);
    totalLines += 1;
    if (currentLines.length >= safeChunkSize) {
      chunks.push(currentLines);
      currentLines = [];
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    bytesRead += value.byteLength;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    lines.forEach(pushLine);
    emitProgress();
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  const tail = decoder.decode();
  if (tail) buffer += tail;
  if (buffer) pushLine(buffer);
  if (currentLines.length) chunks.push(currentLines);

  const totalChunks = chunks.length;
  const outputChunks = chunks.map((lines, index) =>
    makeChunk(lines, file.name, index + 1, totalChunks),
  );

  onProgress?.({
    bytesRead: file.size,
    totalBytes: file.size,
    progress: 100,
    totalLines,
  });

  return {
    fileName: file.name,
    totalLines,
    totalChunks,
    chunks: outputChunks,
  };
}

export function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
