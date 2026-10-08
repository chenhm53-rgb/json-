import React, { useMemo, useState } from 'react';
import {
  CheckCircle2,
  Download,
  FileArchive,
  FileCheck2,
  Trash2,
  UploadCloud,
} from 'lucide-react';
import { downloadBlob, formatBytes, getChunkSize, splitFileByLines } from './emailSplitter.js';

function fileKey(file) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

function SplitDropZone({ onFiles, dragging, setDragging }) {
  const handleFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (files.length) onFiles(files);
  };

  return (
    <label
      className={`split-drop-zone ${dragging ? 'is-dragging' : ''}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        handleFiles(event.dataTransfer.files);
      }}
    >
      <input
        type="file"
        multiple
        accept="*/*"
        onChange={(event) => handleFiles(event.target.files)}
      />
      <span className="split-drop-icon">
        <UploadCloud size={26} />
      </span>
      <span className="split-drop-copy">
        <strong>把大邮箱文件拖到这里</strong>
        <span>支持拖入任意扩展名文件，分割区不会改变原文件。</span>
        <span className="split-select-link">点击选择文件</span>
      </span>
    </label>
  );
}

export default function EmailSplitter({ encoding }) {
  const [files, setFiles] = useState([]);
  const [chunkSize, setChunkSize] = useState(10000);
  const [skipEmpty, setSkipEmpty] = useState(true);
  const [chunks, setChunks] = useState([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState('等待选择需要分割的文件');
  const [progress, setProgress] = useState(0);
  const [processedLines, setProcessedLines] = useState(0);

  const totalChunkLines = useMemo(
    () => chunks.reduce((sum, chunk) => sum + chunk.count, 0),
    [chunks],
  );

  const addFiles = (incoming) => {
    const known = new Set(files.map(fileKey));
    const next = incoming.filter((file) => {
      const key = fileKey(file);
      if (known.has(key)) return false;
      known.add(key);
      return true;
    });
    if (!next.length) return;
    setFiles((current) => [...current, ...next]);
    setChunks([]);
    setStatus(`已选择 ${files.length + next.length} 个文件`);
    setProgress(0);
    setProcessedLines(0);
  };

  const removeFile = (file) => {
    setFiles((current) => current.filter((item) => fileKey(item) !== fileKey(file)));
    setChunks([]);
    setStatus('已移除文件，等待重新分割');
  };

  const clear = () => {
    if (busy) return;
    setFiles([]);
    setChunks([]);
    setProgress(0);
    setProcessedLines(0);
    setStatus('等待选择需要分割的文件');
  };

  const splitFiles = async () => {
    if (!files.length || busy) return;
    const safeChunkSize = getChunkSize(chunkSize);
    setBusy(true);
    setChunks([]);
    setProgress(0);
    setProcessedLines(0);
    const allChunks = [];

    try {
      for (const [fileIndex, file] of files.entries()) {
        setStatus(`正在分割 ${fileIndex + 1}/${files.length}：${file.name}`);
        const result = await splitFileByLines(file, {
          chunkSize: safeChunkSize,
          encoding,
          skipEmpty,
          onProgress: ({ progress: fileProgress, totalLines }) => {
            const overall = Math.round(((fileIndex + fileProgress / 100) / files.length) * 100);
            setProgress(overall);
            setProcessedLines((current) => Math.max(current, totalLines));
          },
        });
        allChunks.push(...result.chunks);
        setChunks([...allChunks]);
      }

      const totalLines = allChunks.reduce((sum, chunk) => sum + chunk.count, 0);
      setProcessedLines(totalLines);
      setProgress(100);
      setStatus(
        `分割完成：${totalLines.toLocaleString('zh-CN')} 行，${allChunks.length} 个小文件，每份最多 ${safeChunkSize.toLocaleString('zh-CN')} 行`,
      );
    } catch (error) {
      setStatus(`分割失败：${error.message}`);
    } finally {
      setBusy(false);
    }
  };

  const downloadChunk = (chunk) => {
    downloadBlob(chunk.blob, chunk.fileName);
  };

  const downloadAll = async () => {
    if (!chunks.length || busy) return;
    setStatus(`正在触发 ${chunks.length} 个文件下载，请按浏览器提示允许多个下载`);
    for (const chunk of chunks) {
      downloadChunk(chunk);
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
    setStatus(`已触发 ${chunks.length} 个分片下载`);
  };

  return (
    <section className="split-panel" aria-label="文件分割">
      <div className="split-panel-header">
        <div className="section-title">
          <FileArchive size={18} />
          <div>
            <h2>文件分割</h2>
            <p className="panel-caption">把大邮箱 TXT 按行拆成多个较小文件，原始顺序保持不变。</p>
          </div>
        </div>
        <div className="split-stat">
          <strong>{chunks.length.toLocaleString('zh-CN')}</strong>
          <span>个分片</span>
        </div>
      </div>

      <div className="split-layout">
        <SplitDropZone onFiles={addFiles} dragging={dragging} setDragging={setDragging} />

        <div className="split-settings">
          <label className="field">
            <span>每个小文件行数</span>
            <input
              aria-label="每个小文件行数"
              type="number"
              min="1"
              max="1000000"
              step="1000"
              value={chunkSize}
              disabled={busy}
              onChange={(event) => setChunkSize(getChunkSize(event.target.value))}
            />
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={skipEmpty}
              disabled={busy}
              onChange={(event) => setSkipEmpty(event.target.checked)}
            />
            <span>跳过空行</span>
          </label>
          <div className="split-button-row">
            <button type="button" className="secondary-button" onClick={splitFiles} disabled={!files.length || busy}>
              <FileCheck2 size={16} />
              {busy ? '分割中…' : '开始分割'}
            </button>
            <button type="button" className="ghost-button" onClick={clear} disabled={busy || (!files.length && !chunks.length)}>
              <Trash2 size={16} />
              清空
            </button>
          </div>
        </div>
      </div>

      <div className="split-status-bar">
        <div>
          <span className={`status-dot ${busy ? 'active' : ''}`} />
          <span>{status}</span>
        </div>
        <div className="split-progress-copy">
          {processedLines.toLocaleString('zh-CN')} 行 · {progress}%
        </div>
      </div>
      <div className="split-progress-track">
        <span style={{ width: `${progress}%` }} />
      </div>

      <div className="split-files-list">
        {files.length === 0 ? (
          <p className="empty-text">还没有待分割文件。</p>
        ) : (
          files.map((file) => (
            <div className="split-source-row" key={fileKey(file)}>
              <div>
                <strong title={file.name}>{file.name}</strong>
                <span>{formatBytes(file.size)}</span>
              </div>
              <button type="button" className="icon-button" title="移除文件" onClick={() => removeFile(file)} disabled={busy}>
                <Trash2 size={16} />
              </button>
            </div>
          ))
        )}
      </div>

      <div className="split-results">
        <div className="split-results-header">
          <div className="section-title">
            <Download size={17} />
            <h3>分片文件</h3>
            <span>{totalChunkLines.toLocaleString('zh-CN')} 行</span>
          </div>
          <button type="button" className="primary-button" onClick={downloadAll} disabled={!chunks.length || busy}>
            <Download size={16} />
            全部下载
          </button>
        </div>
        {chunks.length === 0 ? (
          <p className="empty-text">设置每份行数后点击“开始分割”，这里会列出每个可下载文件。</p>
        ) : (
          <div className="split-result-list">
            {chunks.map((chunk) => (
              <div className="split-result-row" key={chunk.id}>
                <div className="split-result-main">
                  <CheckCircle2 size={17} />
                  <div>
                    <strong title={chunk.fileName}>{chunk.fileName}</strong>
                    <span>{chunk.count.toLocaleString('zh-CN')} 行 · {formatBytes(chunk.bytes)} · 来源：{chunk.sourceName}</span>
                  </div>
                </div>
                <button type="button" className="ghost-button" onClick={() => downloadChunk(chunk)}>
                  <Download size={15} />
                  下载
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
