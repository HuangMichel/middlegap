'use client';
import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist';
import type { Evidence } from '../lib/types';
import { API } from '../lib/api';
export default function SourceDrawer({
  evidence,
  onClose,
}: {
  evidence: Evidence;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    canvas = useRef<HTMLCanvasElement>(null),
    container = useRef<HTMLDivElement>(null);
  const initialPage = evidence.anchors[0]?.page_number || 1;
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null),
    [page, setPage] = useState(initialPage),
    [width, setWidth] = useState(640),
    [size, setSize] = useState({ width: 640, height: 830 }),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [zoom, setZoom] = useState(1);
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    element?.showModal();
    return () => {
      element?.close();
      previous?.focus();
    };
  }, []);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(180, entries[0].contentRect.width - 24)),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let cancelled = false;
    let task: ReturnType<(typeof import('pdfjs-dist'))['getDocument']> | undefined;
    setLoading(true);
    setError('');
    setPdf(null);
    setPage(initialPage);
    import('pdfjs-dist')
      .then((library) => {
        if (cancelled) return;
        library.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs';
        task = library.getDocument({
          url: `${API}/documents/${encodeURIComponent(evidence.document_id)}/file`,
          standardFontDataUrl: '/pdf-standard-fonts/',
          wasmUrl: '/pdf-wasm/',
        });
        return task.promise;
      })
      .then((document) => {
        if (document && !cancelled) setPdf(document);
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(`Could not open the original PDF: ${reason.message}`);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [evidence.document_id, evidence.id, initialPage]);
  useEffect(() => {
    if (!pdf) return;
    let cancelled = false;
    let render: RenderTask | undefined;
    setLoading(true);
    setError('');
    pdf
      .getPage(page)
      .then((source) => {
        if (cancelled || !canvas.current) return;
        const initial = source.getViewport({ scale: 1 });
        const viewport = source.getViewport({ scale: (width / initial.width) * zoom });
        const ratio = window.devicePixelRatio || 1;
        const target = canvas.current;
        target.width = Math.floor(viewport.width * ratio);
        target.height = Math.floor(viewport.height * ratio);
        target.style.width = `${viewport.width}px`;
        target.style.height = `${viewport.height}px`;
        setSize({ width: viewport.width, height: viewport.height });
        render = source.render({
          canvas: target,
          viewport,
          transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
        });
        return render.promise;
      })
      .then(() => {
        if (!cancelled) setLoading(false);
      })
      .catch((reason) => {
        if (!cancelled && reason.name !== 'RenderingCancelledException') {
          setError(`Could not render page ${page}: ${reason.message}`);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
      render?.cancel();
    };
  }, [pdf, page, width, zoom]);
  const anchors = evidence.anchors.filter((a) => a.page_number === page);
  return (
    <dialog
      ref={dialog}
      className="source-drawer"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      aria-labelledby="source-title"
    >
      <header className="drawer-header">
        <div>
          <h2 id="source-title">{evidence.original_filename}</h2>
        </div>
        <button aria-label="Close source drawer" onClick={onClose}>
          Close ×
        </button>
      </header>
      <div className="pdf-toolbar">
        <button
          disabled={!pdf || page <= 1}
          onClick={() => setPage((p) => p - 1)}
          aria-label="Previous page"
        >
          ←
        </button>
        <label>
          Page{' '}
          <input
            type="number"
            min="1"
            max={pdf?.numPages || 1}
            value={page}
            onChange={(event) => {
              const n = Number(event.target.value);
              if (pdf && n >= 1 && n <= pdf.numPages) setPage(n);
            }}
          />
        </label>
        <span>of {pdf?.numPages || '…'}</span>
        <button
          disabled={!pdf || page >= pdf.numPages}
          onClick={() => setPage((p) => p + 1)}
          aria-label="Next page"
        >
          →
        </button>
        <label>
          Zoom{' '}
          <select value={zoom} onChange={(event) => setZoom(Number(event.target.value))}>
            <option value={1}>Fit width</option>
            <option value={1.25}>125%</option>
            <option value={1.5}>150%</option>
          </select>
        </label>
        <a
          href={`${API}/documents/${encodeURIComponent(evidence.document_id)}/file`}
          target="_blank"
          rel="noreferrer"
        >
          Open PDF ↗
        </a>
      </div>
      <div className="source-citation">
        <span className="tag">{evidence.classification}</span>
        <p>“{evidence.quoted_passage}”</p>
        <div className="anchor-links">
          {Array.from(new Set(evidence.anchors.map((a) => a.page_number))).map((number) => (
            <button key={number} aria-pressed={number === page} onClick={() => setPage(number)}>
              Cited page {number}
            </button>
          ))}
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error} Use “Open PDF” to inspect the original artifact.
        </p>
      )}
      <div ref={container} className="pdf-scroll" aria-busy={loading}>
        {loading && (
          <p className="pdf-loading" role="status">
            Rendering original page…
          </p>
        )}
        <div className="pdf-page" style={{ width: size.width, height: size.height }}>
          <canvas ref={canvas} aria-label={`Original PDF page ${page}`} />
          {!loading &&
            anchors.map((anchor, index) => (
              <div
                key={index}
                className="pdf-highlight"
                title={anchor.text}
                aria-label={`Highlighted passage: ${anchor.text}`}
                style={{
                  left: `${anchor.x0 * 100}%`,
                  top: `${anchor.y0 * 100}%`,
                  width: `${(anchor.x1 - anchor.x0) * 100}%`,
                  height: `${(anchor.y1 - anchor.y0) * 100}%`,
                }}
              />
            ))}
        </div>
      </div>
    </dialog>
  );
}
