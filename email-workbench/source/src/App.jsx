import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Eye,
  EyeOff,
  FileText,
  RefreshCw,
  Settings2,
  Table,
  Trash2,
  UploadCloud,
} from 'lucide-react';
import EmailSplitter from './EmailSplitter.jsx';

const DEFAULT_TEMPLATE = '{email}----{password}----{guid}----{token}----{recovery}----{tail}';
const FIELD_NAMES = ['email', 'password', 'guid', 'token', 'recovery', 'tail'];
const PREVIEW_LIMIT = 80;
const ISSUE_LIMIT = 80;
const DEFAULT_TARGET_ROWS = 400000;

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-CN');
}

function normalizeTargetRows(value) {
  const parsed = Number.parseInt(String(value).replace(/[^\d]/g, ''), 10);
  if (Number.isNaN(parsed)) return 0;
  return Math.max(0, parsed);
}

function maskEmail(value = '') {
  const [name, domain] = value.split('@');
  if (!domain) return maskToken(value, 4, 3);
  const prefix = name.length <= 3 ? `${name[0] || ''}***` : `${name.slice(0, 3)}***`;
  return `${prefix}@${domain}`;
}

function maskToken(value = '', start = 5, end = 4) {
  if (!value) return '';
  if (value.length <= start + end + 3) return `${value.slice(0, 2)}***`;
  return `${value.slice(0, start)}...${value.slice(-end)}`;
}

function maskRecord(record) {
  return {
    ...record,
    email: maskEmail(record.email),
    password: maskToken(record.password, 2, 2),
    guid: maskToken(record.guid, 6, 4),
    token: maskToken(record.token, 10, 8),
    recovery: maskEmail(record.recovery),
    tail: maskToken(record.tail, 2, 2),
  };
}

function makeFileId(file) {
  return `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`;
}

function applyTemplate(template, record) {
  return template.replace(/\{(email|password|guid|token|recovery|tail|file|line)\}/g, (_, key) =>
    String(record[key] ?? ''),
  );
}

function parseLine(rawLine, options, fileName, lineNumber) {
  const normalized = rawLine.replace(/\r$/, '');
  if (!normalized.trim()) {
    return { skipped: true };
  }

  const parts = normalized.split(options.separator);
  if (parts.length < FIELD_NAMES.length) {
    return {
      issue: {
        file: fileName,
        line: lineNumber,
        reason: `字段不足：需要 ${FIELD_NAMES.length} 段，实际 ${parts.length} 段`,
        sample: normalized.slice(0, 180),
        raw: normalized,
      },
    };
  }

  const record = FIELD_NAMES.reduce((acc, key, index) => {
    acc[key] = options.trimFields ? parts[index].trim() : parts[index];
    return acc;
  }, {});

  record.file = fileName;
  record.line = lineNumber;
  return { record };
}

async function processFile(fileItem, options, emitProgress, emitLine) {
  const decoder = new TextDecoder(options.encoding);
  const reader = fileItem.file.stream().getReader();
  let buffer = '';
  let bytesRead = 0;
  let lineNumber = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    bytesRead += value.byteLength;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      lineNumber += 1;
      emitLine(parseLine(line, options, fileItem.file.name, lineNumber));
    }

    emitProgress(fileItem.id, {
      status: 'reading',
      progress: Math.min(99, Math.round((bytesRead / fileItem.file.size) * 100)),
      rowsSeen: lineNumber,
    });

    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  const finalText = decoder.decode();
  if (finalText) buffer += finalText;
  if (buffer) {
    lineNumber += 1;
    emitLine(parseLine(buffer, options, fileItem.file.name, lineNumber));
  }

  emitProgress(fileItem.id, {
    status: 'done',
    progress: 100,
    rowsSeen: lineNumber,
  });
}

function DropZone({ onFiles }) {
  const [dragging, setDragging] = useState(false);

  const handleFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (files.length) onFiles(files);
  };

  return (
    <section
      className={`drop-zone ${dragging ? 'is-dragging' : ''}`}
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
      <div className="drop-icon">
        <UploadCloud size={32} />
      </div>
      <div>
        <h2>拖入邮箱文件</h2>
        <p>支持多个 TXT/CSV，默认按 `邮箱----密码----GUID----token----辅助邮箱----尾码` 合并。</p>
        <label className="file-picker-button">
          <input
            type="file"
            multiple
            accept=".txt,.csv,.log,text/plain,text/csv"
            onChange={(event) => handleFiles(event.target.files)}
          />
          选择文件
        </label>
      </div>
    </section>
  );
}

function StatCard({ label, value, tone }) {
  return (
    <div className={`stat-card ${tone || ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Toggle({ checked, onChange, label }) {
  return (
    <label className="toggle-row">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

function App() {
  const [files, setFiles] = useState([]);
  const [separator, setSeparator] = useState('----');
  const [template, setTemplate] = useState(DEFAULT_TEMPLATE);
  const [encoding, setEncoding] = useState('utf-8');
  const [trimFields, setTrimFields] = useState(true);
  const [dedupe, setDedupe] = useState(true);
  const [skipInvalid, setSkipInvalid] = useState(true);
  const [limitRows, setLimitRows] = useState(true);
  const [targetRows, setTargetRows] = useState(DEFAULT_TARGET_ROWS);
  const [maskPreview, setMaskPreview] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progressText, setProgressText] = useState('等待导入文件');
  const [result, setResult] = useState({
    output: '',
    preview: [],
    issues: [],
    stats: {
      total: 0,
      valid: 0,
      invalid: 0,
      duplicate: 0,
      capped: 0,
      skipped: 0,
      files: 0,
      bytes: 0,
    },
  });

  const readyToExport = result.output.length > 0;
  const hasValidTarget = !limitRows || normalizeTargetRows(targetRows) > 0;
  const canMerge = files.length > 0 && separator.length > 0 && hasValidTarget && !busy;

  const totalBytes = useMemo(() => files.reduce((sum, item) => sum + item.file.size, 0), [files]);

  const addFiles = (newFiles) => {
    const next = newFiles.map((file) => ({
      id: makeFileId(file),
      file,
      status: 'queued',
      progress: 0,
      rowsSeen: 0,
    }));
    setFiles((current) => [...current, ...next]);
    setProgressText(`已加入 ${next.length} 个文件`);
  };

  const updateFile = (id, patch) => {
    setFiles((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  const clearAll = () => {
    if (busy) return;
    setFiles([]);
    setResult({
      output: '',
      preview: [],
      issues: [],
      stats: {
        total: 0,
        valid: 0,
        invalid: 0,
        duplicate: 0,
        capped: 0,
        skipped: 0,
        files: 0,
        bytes: 0,
      },
    });
    setProgressText('等待导入文件');
  };

  const mergeFiles = async () => {
    if (!canMerge) return;
    setBusy(true);
    setResult((current) => ({ ...current, output: '', preview: [], issues: [] }));

    const activeTargetRows = limitRows ? normalizeTargetRows(targetRows) : 0;
    const seen = new Set();
    const outputLines = [];
    const preview = [];
    const issues = [];
    const stats = {
      total: 0,
      valid: 0,
      invalid: 0,
      duplicate: 0,
      capped: 0,
      skipped: 0,
      files: files.length,
      bytes: totalBytes,
    };

    const options = {
      separator,
      template,
      encoding,
      trimFields,
    };

    try {
      for (const [fileIndex, item] of files.entries()) {
        updateFile(item.id, { status: 'reading', progress: 0, rowsSeen: 0 });
        setProgressText(`正在处理 ${fileIndex + 1}/${files.length}：${item.file.name}`);

        await processFile(
          item,
          options,
          updateFile,
          (parsed) => {
            if (parsed.skipped) {
              stats.skipped += 1;
              return;
            }

            stats.total += 1;

            if (parsed.issue) {
              stats.invalid += 1;
              if (issues.length < ISSUE_LIMIT) issues.push(parsed.issue);
              if (!skipInvalid) {
                const rawLine = parsed.issue.raw;
                if (!dedupe || !seen.has(rawLine)) {
                  seen.add(rawLine);
                  if (!activeTargetRows || outputLines.length < activeTargetRows) {
                    outputLines.push(rawLine);
                    stats.valid += 1;
                  } else {
                    stats.capped += 1;
                  }
                } else {
                  stats.duplicate += 1;
                }
              }
              return;
            }

            const line = applyTemplate(template, parsed.record);
            if (dedupe && seen.has(line)) {
              stats.duplicate += 1;
              return;
            }

            seen.add(line);
            let addedToOutput = false;
            if (!activeTargetRows || outputLines.length < activeTargetRows) {
              outputLines.push(line);
              stats.valid += 1;
              addedToOutput = true;
            } else {
              stats.capped += 1;
            }

            if (addedToOutput && preview.length < PREVIEW_LIMIT) {
              preview.push({
                ...parsed.record,
                output: line,
              });
            }
          },
        );
      }

      const output = outputLines.join('\n');
      setResult({ output, preview, issues, stats });
      if (activeTargetRows && stats.valid < activeTargetRows) {
        setProgressText(`合并完成：${formatNumber(stats.valid)} 行可导出，未满 ${formatNumber(activeTargetRows)}，还差 ${formatNumber(activeTargetRows - stats.valid)} 行`);
      } else if (activeTargetRows && stats.capped > 0) {
        setProgressText(`合并完成：已凑满 ${formatNumber(activeTargetRows)} 行，超出 ${formatNumber(stats.capped)} 行未导出`);
      } else {
        setProgressText(`合并完成：${formatNumber(stats.valid)} 行可导出`);
      }
    } catch (error) {
      setProgressText(`处理失败：${error.message}`);
    } finally {
      setBusy(false);
    }
  };

  const downloadOutput = () => {
    if (!readyToExport) return;
    const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
    const blob = new Blob([result.output], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `merged-email-${stamp}.txt`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  const previewRows = maskPreview ? result.preview.map(maskRecord) : result.preview;

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div>
          <p className="overline">本地文件工作台</p>
          <h1>邮箱文件合并</h1>
        </div>
        <div className="privacy-pill">
          <CheckCircle2 size={16} />
          <span>本机处理，不上传</span>
        </div>
      </header>

      <section className="summary-grid">
        <StatCard label="文件" value={formatNumber(files.length)} />
        <StatCard label="体积" value={formatBytes(totalBytes)} />
        <StatCard label="导出行" value={formatNumber(result.stats.valid)} tone="good" />
        <StatCard label="异常/重复/超出" value={`${formatNumber(result.stats.invalid)}/${formatNumber(result.stats.duplicate)}/${formatNumber(result.stats.capped)}`} tone="warn" />
      </section>

      <div className="main-grid">
        <aside className="side-panel">
          <DropZone onFiles={addFiles} />

          <section className="panel-section">
            <div className="section-title">
              <FileText size={18} />
              <h2>文件队列</h2>
            </div>
            <div className="file-list">
              {files.length === 0 ? (
                <p className="empty-text">还没有文件，拖进来就能开始。</p>
              ) : (
                files.map((item) => (
                  <div className="file-row" key={item.id}>
                    <div className="file-meta">
                      <strong title={item.file.name}>{item.file.name}</strong>
                      <span>{formatBytes(item.file.size)} · {formatNumber(item.rowsSeen)} 行</span>
                    </div>
                    <div className="progress-track">
                      <span style={{ width: `${item.progress}%` }} />
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </aside>

        <section className="center-panel">
          <div className="action-bar">
            <div>
              <span className={`status-dot ${busy ? 'active' : ''}`} />
              <span>{progressText}</span>
            </div>
            <div className="button-row">
              <button type="button" className="ghost-button" onClick={clearAll} disabled={busy || files.length === 0}>
                <Trash2 size={16} />
                清空
              </button>
              <button type="button" className="secondary-button" onClick={mergeFiles} disabled={!canMerge}>
                <RefreshCw size={16} className={busy ? 'spin' : ''} />
                合并预览
              </button>
              <button type="button" className="primary-button" onClick={downloadOutput} disabled={!readyToExport || busy}>
                <Download size={16} />
                导出 TXT
              </button>
            </div>
          </div>

          <div className="preview-header">
            <div className="section-title">
              <Table size={18} />
              <h2>预览</h2>
            </div>
            <button type="button" className="icon-button" onClick={() => setMaskPreview((value) => !value)} title="切换预览脱敏">
              {maskPreview ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>邮箱</th>
                  <th>密码</th>
                  <th>GUID</th>
                  <th>Token</th>
                  <th>辅助邮箱</th>
                  <th>尾码</th>
                </tr>
              </thead>
              <tbody>
                {previewRows.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="empty-cell">合并后会显示前 {PREVIEW_LIMIT} 行预览。</td>
                  </tr>
                ) : (
                  previewRows.map((row, index) => (
                    <tr key={`${row.file}-${row.line}-${index}`}>
                      <td>{row.email}</td>
                      <td>{row.password}</td>
                      <td>{row.guid}</td>
                      <td>{row.token}</td>
                      <td>{row.recovery}</td>
                      <td>{row.tail}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <section className="issue-panel">
            <div className="section-title">
              <AlertTriangle size={18} />
              <h2>异常行</h2>
            </div>
            {result.issues.length === 0 ? (
              <p className="empty-text">暂无异常。字段不足或格式不匹配的行会出现在这里。</p>
            ) : (
              <div className="issue-list">
                {result.issues.map((issue, index) => (
                  <div className="issue-row" key={`${issue.file}-${issue.line}-${index}`}>
                    <strong>{issue.file} · 第 {issue.line} 行</strong>
                    <span>{issue.reason}</span>
                    <code>{issue.sample}</code>
                  </div>
                ))}
              </div>
            )}
          </section>
        </section>

        <aside className="settings-panel">
          <div className="section-title">
            <Settings2 size={18} />
            <h2>合并格式</h2>
          </div>

          <label className="field">
            <span>分隔符</span>
            <input value={separator} onChange={(event) => setSeparator(event.target.value)} />
          </label>

          <label className="field">
            <span>编码</span>
            <select value={encoding} onChange={(event) => setEncoding(event.target.value)}>
              <option value="utf-8">UTF-8</option>
              <option value="gb18030">GB18030</option>
            </select>
          </label>

          <label className="field">
            <span>导出模板</span>
            <textarea value={template} onChange={(event) => setTemplate(event.target.value)} rows={5} />
          </label>

          <div className="token-help">
            <code>{'{email}'}</code>
            <code>{'{password}'}</code>
            <code>{'{guid}'}</code>
            <code>{'{token}'}</code>
            <code>{'{recovery}'}</code>
            <code>{'{tail}'}</code>
            <code>{'{file}'}</code>
            <code>{'{line}'}</code>
          </div>

          <div className="toggle-group">
            <Toggle checked={trimFields} onChange={setTrimFields} label="去掉字段前后空格" />
            <Toggle checked={dedupe} onChange={setDedupe} label="按导出整行去重" />
            <Toggle checked={skipInvalid} onChange={setSkipInvalid} label="跳过格式异常行" />
            <Toggle checked={limitRows} onChange={setLimitRows} label="只导出固定行数" />
          </div>

          <label className="field">
            <span>凑整行数</span>
            <input
              type="number"
              min="1"
              step="1000"
              value={targetRows}
              disabled={!limitRows}
              onChange={(event) => setTargetRows(normalizeTargetRows(event.target.value))}
            />
          </label>

          <div className="rounding-card">
            <strong>凑整规则</strong>
            <p>开启后最多导出 {formatNumber(normalizeTargetRows(targetRows))} 行；数据不足时只提示差额，不自动补假行。</p>
          </div>

          <div className="format-card">
            <strong>当前导出格式</strong>
            <code>{DEFAULT_TEMPLATE}</code>
          </div>
        </aside>
      </div>

      <EmailSplitter encoding={encoding} />
    </main>
  );
}

export default App;
