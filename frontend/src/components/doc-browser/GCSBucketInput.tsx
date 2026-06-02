"use client";

import { useEffect, useRef, useState } from "react";

const STORAGE_KEY = "ap-gcs-user-bucket";

interface GCSBucketInputProps {
  onBucketChange: (bucket: string) => void;
  onBrowse: () => void;
}

export function GCSBucketInput({ onBucketChange, onBrowse }: GCSBucketInputProps) {
  const [inputValue, setInputValue] = useState("");
  const onBucketChangeRef = useRef(onBucketChange);
  onBucketChangeRef.current = onBucketChange;

  // Load persisted bucket name on mount and notify parent
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) ?? "";
    if (stored) {
      setInputValue(stored);
      onBucketChangeRef.current(stored);
    }
  }, []); // intentionally only on mount

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value.replace(/^gs:\/\//, "");
    setInputValue(raw);
    onBucketChange(raw);
    if (raw) {
      localStorage.setItem(STORAGE_KEY, raw);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }

  function handleClear() {
    setInputValue("");
    onBucketChange("");
    localStorage.removeItem(STORAGE_KEY);
  }

  return (
    <div className="flex items-center gap-1.5">
      <input
        type="text"
        value={inputValue}
        onChange={handleChange}
        placeholder="bucket-name or gs://bucket-name"
        className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1 text-[11px] text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/40"
      />
      <button
        type="button"
        onClick={onBrowse}
        disabled={!inputValue.trim()}
        className="shrink-0 rounded border border-primary/30 px-2 py-1 text-[10px] font-medium text-primary hover:bg-primary/10 disabled:opacity-40"
      >
        Browse
      </button>
      {inputValue && (
        <button
          type="button"
          onClick={handleClear}
          aria-label="Clear bucket"
          className="shrink-0 rounded px-1.5 py-1 text-[10px] text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      )}
    </div>
  );
}
