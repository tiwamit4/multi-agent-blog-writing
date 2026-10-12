import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ArticlePreview({ markdown, runId }: { markdown: string; runId: string }) {
  return <article className="article-preview"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    img: ({ src, alt, ...props }) => <img {...props} alt={alt ?? ""} src={src?.startsWith("output/images/")
      ? `/api/runs/${encodeURIComponent(runId)}/image?path=${encodeURIComponent(src)}` : src} />,
    a: ({ href, children, ...props }) => <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
  }}>{markdown}</ReactMarkdown></article>;
}
