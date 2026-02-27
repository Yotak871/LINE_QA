"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, ImageIcon } from "lucide-react";
import clsx from "clsx";

interface Props {
  label: string;
  hint: string;
  file: File | null;
  onFile: (f: File) => void;
  onClear: () => void;
}

export default function UploadZone({ label, hint, file, onFile, onClear }: Props) {
  const [preview, setPreview] = useState<string | null>(null);

  const onDrop = useCallback((accepted: File[]) => {
    if (!accepted[0]) return;
    onFile(accepted[0]);
    setPreview(URL.createObjectURL(accepted[0]));
  }, [onFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "image/png": [], "image/jpeg": [], "image/webp": [] },
    maxSize: 20 * 1024 * 1024,
    multiple: false,
  });

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClear();
    setPreview(null);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-[#111]">{label}</span>
        {file && (
          <span className="text-xs text-[#999] truncate max-w-[160px]">{file.name}</span>
        )}
      </div>

      <div
        {...getRootProps()}
        className={clsx(
          "relative border-2 border-dashed rounded-lg cursor-pointer transition-all",
          "flex items-center justify-center min-h-[220px] overflow-hidden",
          isDragActive
            ? "border-line-500 bg-line-50"
            : file
            ? "border-surface-100 bg-surface-50"
            : "border-surface-100 bg-white hover:border-line-500 hover:bg-line-50"
        )}
      >
        <input {...getInputProps()} />

        {preview ? (
          <>
            <img src={preview} alt="preview" className="max-h-[220px] max-w-full object-contain" />
            <button
              onClick={handleClear}
              className="absolute top-2 right-2 bg-white border border-surface-100 rounded-full p-1 shadow-sm hover:bg-red-50 transition-colors"
            >
              <X size={14} className="text-[#616161]" />
            </button>
          </>
        ) : (
          <div className="flex flex-col items-center gap-3 p-6 text-center">
            <div className="w-12 h-12 rounded-full bg-surface-50 flex items-center justify-center">
              {isDragActive ? (
                <ImageIcon size={20} className="text-line-500" />
              ) : (
                <Upload size={20} className="text-[#999]" />
              )}
            </div>
            <div>
              <p className="text-sm font-medium text-[#111]">
                {isDragActive ? "여기에 놓으세요" : "이미지를 드래그하거나 클릭"}
              </p>
              <p className="text-xs text-[#999] mt-1">{hint}</p>
              <p className="text-xs text-[#b7b7b7] mt-0.5">PNG, JPG, WebP · 최대 20MB</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
