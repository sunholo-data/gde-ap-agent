import Link from "next/link";

export default function NewSkillPage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="max-w-md space-y-4 text-center">
        <h1 className="text-2xl font-semibold">Create a new skill</h1>
        <p className="text-muted-foreground">
          The skill creation wizard is on its way. For now, use{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-sm">aitana skill create</code>{" "}
          from the local CLI.
        </p>
        <Link className="inline-block text-sm underline" href="/">
          ← Back to home
        </Link>
      </div>
    </main>
  );
}
