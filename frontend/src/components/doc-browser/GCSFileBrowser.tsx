"use client";

import { useEffect, useState } from "react";
import { useGCSBucket } from "@/hooks/useGCSBucket";
import { GCSBucketInput } from "./GCSBucketInput";
import { GCSFileItem } from "./GCSFileItem";
import { subscribeDocumentImported } from "@/lib/documentEvents";

function Skeleton() {
  return (
    <div className="space-y-1.5 px-2 py-2">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-6 animate-pulse rounded bg-muted" />
      ))}
    </div>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 4l4 4-4 4" />
    </svg>
  );
}

interface GCSFileBrowserProps {
  skillId?: string;
}

export function GCSFileBrowser({ skillId = "" }: GCSFileBrowserProps) {
  const [userBucket, setUserBucket] = useState("");

  const demo = useGCSBucket("demo");
  const user = useGCSBucket(userBucket);

  // Controlled accordion state so the source sections can auto-collapse
  // after an import — sidebar real estate is tight and once the doc has
  // moved into My Documents, the user's attention shifts there. The
  // demo section stays open by default to advertise the example
  // invoices to first-time visitors.
  const [demoOpen, setDemoOpen] = useState(true);
  const [userOpen, setUserOpen] = useState(false);

  useEffect(() => {
    return subscribeDocumentImported(() => {
      setDemoOpen(false);
      setUserOpen(false);
    });
  }, []);

  return (
    <div className="text-xs">
      {/* Example Invoices */}
      <details
        open={demoOpen}
        onToggle={(e) => setDemoOpen((e.target as HTMLDetailsElement).open)}
        className="group"
      >
        <summary className="flex cursor-pointer select-none items-center gap-1.5 border-b border-border px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/50 hover:text-muted-foreground">
          <ChevronIcon open={demoOpen} />
          Example Invoices
        </summary>
        {demo.isLoading && <Skeleton />}
        {!demo.isLoading && demo.error && (
          <div className="px-3 py-2">
            <p className="text-[10px] text-destructive">{demo.error}</p>
            {demo.saEmail && (
              <p className="mt-1 text-[10px] text-muted-foreground">
                Grant{" "}
                <code className="rounded bg-muted px-0.5 text-[10px]">{demo.saEmail}</code>{" "}
                Storage Object Viewer
              </p>
            )}
          </div>
        )}
        {!demo.isLoading && !demo.error && demo.objects.length === 0 && (
          <p className="px-3 py-2 text-[10px] text-muted-foreground">
            No demo files — run setup-demo-bucket.sh
          </p>
        )}
        {!demo.isLoading && demo.objects.length > 0 && (
          <div className="max-h-[32vh] overflow-y-auto py-0.5">
            {demo.objects.map((obj) => (
              <GCSFileItem key={obj.name} obj={obj} bucket="demo" skillId={skillId} />
            ))}
          </div>
        )}
      </details>

      {/* Your GCS Bucket */}
      <details
        open={userOpen}
        onToggle={(e) => setUserOpen((e.target as HTMLDetailsElement).open)}
        className="group"
      >
        <summary className="flex cursor-pointer select-none items-center gap-1.5 border-b border-border px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/50 hover:text-muted-foreground">
          <ChevronIcon open={userOpen} />
          Your GCS Bucket
        </summary>
        <div className="space-y-2 px-3 py-2">
          <GCSBucketInput onBucketChange={setUserBucket} onBrowse={() => user.refetch()} />
          {user.isLoading && <Skeleton />}
          {!user.isLoading && user.error && (
            <div>
              <p className="text-[10px] text-destructive">{user.error}</p>
              {user.saEmail && (
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Grant{" "}
                  <code className="rounded bg-muted px-0.5 text-[10px]">{user.saEmail}</code>{" "}
                  Storage Object Viewer
                </p>
              )}
            </div>
          )}
          {!user.isLoading && !user.error && userBucket && user.objects.length === 0 && (
            <p className="text-[10px] text-muted-foreground">No files found in this bucket.</p>
          )}
          {!user.isLoading && user.objects.length > 0 && (
            <div className="max-h-[32vh] overflow-y-auto py-0.5">
              {user.objects.map((obj) => (
                <GCSFileItem key={obj.name} obj={obj} bucket={userBucket} skillId={skillId} />
              ))}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
