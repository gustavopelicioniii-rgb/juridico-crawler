const express = require("express");
const path = require("path");

const app = express();
const PORT = 3333;

// Servir arquivos estáticos
app.use(express.static(path.join(__dirname, "public")));

// Rota principal
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

// Rota de health check
app.get("/health", (req, res) => {
  res.json({ status: "online", timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
  console.log(`\n┌─────────────────────────────────────────┐`);
  console.log(`│  🚀 JurídicoCrawler Dashboard Online   │`);
  console.log(`├─────────────────────────────────────────┤`);
  console.log(`│  http://localhost:${PORT}                  │`);
  console.log(`└─────────────────────────────────────────┘\n`);
});
