import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

console.log("? index.js loaded"); // コンソール確認用
const el = document.getElementById("root");
if (!el) alert("root が見つかりません");
const root = createRoot(el);
root.render(<App />);
