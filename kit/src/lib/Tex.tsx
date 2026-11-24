import katex from "katex";
import "katex/dist/katex.min.css";
import "./katex-fix.css";
import React from "react";

const cache = new Map<string, string>();

export const texHtml = (tex: string) => {
  let html = cache.get(tex);
  if (!html) {
    html = katex.renderToString(tex, { throwOnError: true, output: "html", strict: false });
    cache.set(tex, html);
  }
  return html;
};

export const Tex: React.FC<{ tex: string; style?: React.CSSProperties }> = ({ tex, style }) => (
  <span style={{ whiteSpace: "nowrap", ...style }} dangerouslySetInnerHTML={{ __html: texHtml(tex) }} />
);

// 中文夾數學式：用 $...$ 包住 TeX
export const Rich: React.FC<{ text: string; style?: React.CSSProperties; mathStyle?: React.CSSProperties }> = ({
  text,
  style,
  mathStyle,
}) => {
  const parts = text.split("$");
  return (
    <span style={style}>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <Tex key={i} tex={p} style={{ fontSize: "1.08em", margin: "0 0.12em", ...mathStyle }} />
        ) : (
          <React.Fragment key={i}>{p}</React.Fragment>
        ),
      )}
    </span>
  );
};
