import React, { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";

// 等字型載入完才開始截圖，避免第一格用到備用字型
const FACES = [
  "40px KaTeX_Main",
  "italic 40px KaTeX_Math",
  "bold 40px KaTeX_Main",
  "40px KaTeX_Size1",
  "40px KaTeX_Size2",
  "40px KaTeX_AMS",
  "40px 'Noto Sans CJK TC'",
  "bold 40px 'Noto Sans CJK TC'",
];

export const FontGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    Promise.all(FACES.map((f) => document.fonts.load(f, "Pφ→∧∨¬中")))
      .then(() => document.fonts.ready)
      .then(() => continueRender(handle))
      .catch((e) => {
        console.error(e);
        continueRender(handle);
      });
  }, [handle]);
  return <>{children}</>;
};
