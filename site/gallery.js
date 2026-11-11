const gallery = document.querySelector("#gallery");
const status = document.querySelector("#status");
const query = document.querySelector("#query");
const buttons = [...document.querySelectorAll("[data-category]")];
const categories = new Map(buttons.slice(1).map(button => [
  button.dataset.category, button.textContent,
]));
const catalogs = new Map();
const initialParams = new URLSearchParams(location.search);
let category = initialParams.get("category");
if (!categories.has(category)) category = "all";
query.value = initialParams.get("q") ?? "";
let requestNumber = 0;

function loadCatalog(name) {
  if (!catalogs.has(name)) {
    const url = new URL(`catalog/${name}.json`, document.baseURI);
    const request = fetch(url).then(async response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const examples = await response.json();
      return examples.map(example => ({
        ...example,
        category: name,
        cover: new URL(example.cover, response.url).href,
        page: new URL(example.page, response.url).href,
      }));
    }).catch(error => {
      catalogs.delete(name);
      throw error;
    });
    catalogs.set(name, request);
  }
  return catalogs.get(name);
}

function normalize(text) {
  return text.normalize("NFKC").toLowerCase();
}

function search(examples, input) {
  const terms = [...new Set(normalize(input).split(/\s+/).filter(Boolean))];
  if (terms.length === 0) return examples;
  return examples.map(example => {
    const text = normalize([example.title, example.style, example.description].join(" "));
    const score = terms.filter(term => text.includes(term)).length;
    return {example, score};
  }).filter(result => result.score > 0)
    .sort((left, right) => right.score - left.score)
    .map(result => result.example);
}

function createCard(example) {
  const card = document.createElement("a");
  card.className = "card";
  card.href = example.page;

  const cover = document.createElement("img");
  cover.className = "cover";
  cover.src = example.cover;
  cover.alt = "";
  cover.loading = "lazy";
  cover.decoding = "async";

  const body = document.createElement("div");
  body.className = "card-body";
  const label = document.createElement("p");
  label.className = "eyebrow";
  label.textContent = `${categories.get(example.category)} / ${example.style}`;
  const title = document.createElement("h2");
  title.textContent = example.title;
  const description = document.createElement("p");
  description.className = "card-description";
  description.textContent = example.description;
  body.append(label, title, description);
  card.append(cover, body);
  return card;
}

async function updateGallery() {
  const currentRequest = ++requestNumber;
  const input = query.value.trim();
  const params = new URLSearchParams();
  if (category !== "all") params.set("category", category);
  if (input) params.set("q", input);
  const suffix = params.size ? `?${params}` : "";
  history.replaceState(null, "", `${location.pathname}${suffix}`);
  for (const button of buttons) {
    button.setAttribute("aria-pressed", button.dataset.category === category);
  }

  const names = category === "all" ? [...categories.keys()] : [category];
  gallery.setAttribute("aria-busy", "true");
  try {
    const examples = (await Promise.all(names.map(loadCatalog))).flat();
    if (currentRequest !== requestNumber) return;
    const results = search(examples, input);
    gallery.replaceChildren(...results.map(createCard));
    if (results.length) {
      status.textContent = `${results.length} 个示例`;
    } else {
      status.textContent = input ? "没有匹配的示例。试试较短的关键词。" : "这个类别暂时没有示例。";
    }
  } catch {
    if (currentRequest !== requestNumber) return;
    gallery.replaceChildren();
    status.textContent = "暂时无法载入示例。请刷新重试。";
  } finally {
    if (currentRequest === requestNumber) gallery.setAttribute("aria-busy", "false");
  }
}

for (const button of buttons) {
  button.addEventListener("click", () => {
    category = button.dataset.category;
    updateGallery();
  });
}
query.addEventListener("input", updateGallery);
document.querySelector("#search").addEventListener("submit", event => {
  event.preventDefault();
  updateGallery();
});
updateGallery();
