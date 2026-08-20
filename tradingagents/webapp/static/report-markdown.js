const SIGNAL_GROUPS = Object.freeze({
  positive: new Set(["strong buy", "buy", "overweight", "bullish", "upside"]),
  negative: new Set(["strong sell", "sell", "underweight", "bearish", "downside"]),
  neutral: new Set(["hold", "neutral"]),
});

const INLINE_PATTERN = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|~~[^~\n]+~~|\*[^*\n]+\*|_[^_\n]+_|\b(?:strong\s+buy|strong\s+sell|buy|sell|overweight|underweight|hold|neutral|bullish|bearish|upside|downside)\b)/gi;
const MAX_BLOCKS = 1000;
const MAX_INLINE_TOKENS = 1000;
const MAX_LIST_ITEMS = 500;
const MAX_TABLE_CELLS = 1200;
const MAX_TABLE_COLUMNS = 24;
const MAX_LINK_LABEL_LENGTH = 512;
const MAX_LINK_URL_LENGTH = 2048;

function appendText(parent, value, documentRef) {
  if (value) parent.append(documentRef.createTextNode(String(value)));
}

function signalGroup(value) {
  const normalized = String(value).trim().toLowerCase().replace(/\s+/g, " ");
  return Object.keys(SIGNAL_GROUPS).find(function (group) {
    return SIGNAL_GROUPS[group].has(normalized);
  }) || "";
}

export function isSafeReportLink(value) {
  try {
    const parsed = new URL(String(value));
    return (
      (parsed.protocol === "http:" || parsed.protocol === "https:") &&
      !parsed.username && !parsed.password
    );
  } catch (_error) {
    return false;
  }
}

function takeInlineToken(budget) {
  if (budget.inlineTokens <= 0) return false;
  budget.inlineTokens -= 1;
  return true;
}

function appendStyledText(parent, value, documentRef, budget) {
  const source = String(value || "");
  const inlinePattern = new RegExp(INLINE_PATTERN.source, INLINE_PATTERN.flags);
  let cursor = 0;
  let match;

  while ((match = inlinePattern.exec(source)) !== null) {
    appendText(parent, source.slice(cursor, match.index), documentRef);
    const token = match[0];
    if (!takeInlineToken(budget)) {
      appendText(parent, source.slice(match.index), documentRef);
      return;
    }
    let node = null;

    if (token.startsWith("`") && token.endsWith("`")) {
      node = documentRef.createElement("code");
      node.textContent = token.slice(1, -1);
    } else if (
      (token.startsWith("**") && token.endsWith("**")) ||
      (token.startsWith("__") && token.endsWith("__"))
    ) {
      node = documentRef.createElement("strong");
      appendInline(node, token.slice(2, -2), documentRef, budget);
    } else if (token.startsWith("~~") && token.endsWith("~~")) {
      node = documentRef.createElement("del");
      appendInline(node, token.slice(2, -2), documentRef, budget);
    } else if (
      (token.startsWith("*") && token.endsWith("*")) ||
      (token.startsWith("_") && token.endsWith("_"))
    ) {
      node = documentRef.createElement("em");
      appendInline(node, token.slice(1, -1), documentRef, budget);
    } else {
      const group = signalGroup(token);
      if (group) {
        node = documentRef.createElement("span");
        node.className = "md-signal";
        node.dataset.signal = group;
        node.textContent = token;
      }
    }

    if (node) parent.append(node);
    cursor = match.index + token.length;
  }
  appendText(parent, source.slice(cursor), documentRef);
}

function nextMarkdownLink(source, startIndex) {
  let searchIndex = startIndex;
  while (searchIndex < source.length) {
    const open = source.indexOf("[", searchIndex);
    if (open < 0) return null;
    const labelEnd = source.indexOf("](", open + 1);
    if (labelEnd < 0) return null;
    if (labelEnd - open - 1 > MAX_LINK_LABEL_LENGTH) {
      searchIndex = labelEnd + 2;
      continue;
    }
    const urlEnd = source.indexOf(")", labelEnd + 2);
    if (urlEnd < 0) return null;
    const href = source.slice(labelEnd + 2, urlEnd);
    if (!href || href.length > MAX_LINK_URL_LENGTH || /\s/.test(href)) {
      searchIndex = urlEnd + 1;
      continue;
    }
    return {
      end: urlEnd + 1,
      href,
      label: source.slice(open + 1, labelEnd),
      open,
    };
  }
  return null;
}

function appendInline(parent, value, documentRef, budget) {
  const source = String(value || "");
  let cursor = 0;
  while (cursor < source.length) {
    const link = nextMarkdownLink(source, cursor);
    if (!link) {
      appendStyledText(parent, source.slice(cursor), documentRef, budget);
      return;
    }
    if (link.open > cursor && source[link.open - 1] === "!") {
      appendStyledText(parent, source.slice(cursor, link.open - 1), documentRef, budget);
      if (!takeInlineToken(budget)) {
        appendText(parent, source.slice(link.open - 1), documentRef);
        return;
      }
      appendText(parent, source.slice(link.open - 1, link.end), documentRef);
      cursor = link.end;
      continue;
    }
    appendStyledText(parent, source.slice(cursor, link.open), documentRef, budget);
    if (!takeInlineToken(budget)) {
      appendText(parent, source.slice(link.open), documentRef);
      return;
    }
    const token = source.slice(link.open, link.end);
    if (isSafeReportLink(link.href)) {
      const node = documentRef.createElement("a");
      node.href = link.href;
      node.target = "_blank";
      node.rel = "noopener noreferrer nofollow";
      appendStyledText(node, link.label, documentRef, budget);
      parent.append(node);
    } else {
      appendText(parent, token, documentRef);
    }
    cursor = link.end;
  }
}

function splitTableRow(line) {
  let value = String(line).trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);

  const cells = [];
  let cell = "";
  let escaped = false;
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    const next = value[index + 1];
    if (character === "\\" && (next === "|" || next === "\\")) {
      cell += next;
      index += 1;
    } else if (character === "|") {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += character;
    }
  }
  cells.push(cell.trim());
  return cells;
}

function isTableDelimiter(line) {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every(function (cell) {
    return /^:?-{3,}:?$/.test(cell.replace(/\s+/g, ""));
  });
}

function fenceMatch(line) {
  return String(line).match(/^ {0,3}(`{3,}|~{3,})\s*([\w.+-]*)\s*$/);
}

function headingMatch(line) {
  return String(line).match(/^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+[ \t]*)?$/);
}

function unorderedMatch(line) {
  return String(line).match(/^ {0,3}[-+*]\s+(.+)$/);
}

function orderedMatch(line) {
  return String(line).match(/^ {0,3}(\d+)[.)]\s+(.+)$/);
}

function isHorizontalRule(line) {
  return /^ {0,3}(?:(?:-\s*){3,}|(?:_\s*){3,}|(?:\*\s*){3,})$/.test(String(line));
}

function isBlockStart(lines, index) {
  const line = lines[index] || "";
  if (
    fenceMatch(line) || headingMatch(line) || unorderedMatch(line) || orderedMatch(line) ||
    isHorizontalRule(line) || /^ {0,3}>/.test(line)
  ) {
    return true;
  }
  return isTableStart(lines, index);
}

function isTableStart(lines, index) {
  if (index + 1 >= lines.length || !String(lines[index]).includes("|")) return false;
  const headings = splitTableRow(lines[index]);
  const delimiters = splitTableRow(lines[index + 1]);
  return headings.length >= 2 && headings.length === delimiters.length && isTableDelimiter(lines[index + 1]);
}

function isTableBodyLine(line) {
  return Boolean(
    String(line).trim() && String(line).includes("|") && !fenceMatch(line) &&
    !headingMatch(line) && !unorderedMatch(line) && !orderedMatch(line) &&
    !isHorizontalRule(line) && !/^ {0,3}>/.test(line)
  );
}

function appendPlainBlock(parent, value, documentRef) {
  const block = documentRef.createElement("pre");
  block.className = "md-plain-block";
  block.textContent = String(value);
  parent.append(block);
}

function appendTable(parent, lines, startIndex, documentRef, budget) {
  const headings = splitTableRow(lines[startIndex]);
  const alignments = splitTableRow(lines[startIndex + 1]).map(function (cell) {
    const value = cell.replace(/\s+/g, "");
    if (value.startsWith(":") && value.endsWith(":")) return "center";
    if (value.endsWith(":")) return "right";
    return "left";
  });
  const wrapper = documentRef.createElement("div");
  wrapper.className = "md-table-scroll";
  wrapper.tabIndex = 0;
  wrapper.setAttribute("aria-label", "Scrollable analysis table");

  let endIndex = startIndex + 2;
  while (endIndex < lines.length && isTableBodyLine(lines[endIndex])) endIndex += 1;
  const cellCount = headings.length * (endIndex - startIndex - 1);
  if (headings.length > MAX_TABLE_COLUMNS || cellCount > MAX_TABLE_CELLS) {
    appendPlainBlock(parent, lines.slice(startIndex, endIndex).join("\n"), documentRef);
    return endIndex;
  }

  const table = documentRef.createElement("table");
  const head = documentRef.createElement("thead");
  const headRow = documentRef.createElement("tr");
  headings.forEach(function (heading, index) {
    const cell = documentRef.createElement("th");
    cell.style.textAlign = alignments[index] || "left";
    appendInline(cell, heading, documentRef, budget);
    headRow.append(cell);
  });
  head.append(headRow);
  table.append(head);

  const body = documentRef.createElement("tbody");
  let index = startIndex + 2;
  while (index < endIndex) {
    const row = documentRef.createElement("tr");
    const values = splitTableRow(lines[index]);
    headings.forEach(function (_heading, cellIndex) {
      const cell = documentRef.createElement("td");
      cell.style.textAlign = alignments[cellIndex] || "left";
      appendInline(cell, values[cellIndex] || "", documentRef, budget);
      row.append(cell);
    });
    body.append(row);
    index += 1;
  }
  table.append(body);
  wrapper.append(table);
  parent.append(wrapper);
  return index;
}

export function renderReportMarkdown(value, documentRef = document) {
  const source = String(value || "").replace(/\r\n?/g, "\n");
  const lines = source.split("\n");
  const fragment = documentRef.createDocumentFragment();
  const budget = { blocks: MAX_BLOCKS, inlineTokens: MAX_INLINE_TOKENS };
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (budget.blocks <= 0) {
      appendPlainBlock(fragment, lines.slice(index).join("\n"), documentRef);
      break;
    }
    budget.blocks -= 1;

    const fence = fenceMatch(line);
    if (fence) {
      const marker = fence[1];
      const codeLines = [];
      index += 1;
      while (index < lines.length) {
        const closing = lines[index].match(/^ {0,3}(`{3,}|~{3,})\s*$/);
        if (closing && closing[1][0] === marker[0] && closing[1].length >= marker.length) {
          index += 1;
          break;
        }
        codeLines.push(lines[index]);
        index += 1;
      }
      const pre = documentRef.createElement("pre");
      pre.className = "md-code-block";
      pre.dataset.language = (fence[2] || "CODE").toUpperCase();
      const code = documentRef.createElement("code");
      code.textContent = codeLines.join("\n");
      pre.append(code);
      fragment.append(pre);
      continue;
    }

    const heading = headingMatch(line);
    if (heading) {
      const level = heading[1].length;
      const node = documentRef.createElement("h" + Math.min(6, level + 1));
      node.className = "md-heading md-heading-level-" + level;
      appendInline(node, heading[2], documentRef, budget);
      fragment.append(node);
      index += 1;
      continue;
    }

    if (isHorizontalRule(line)) {
      fragment.append(documentRef.createElement("hr"));
      index += 1;
      continue;
    }

    if (isTableStart(lines, index)) {
      index = appendTable(fragment, lines, index, documentRef, budget);
      continue;
    }

    if (/^ {0,3}>/.test(line)) {
      const quoteLines = [];
      while (index < lines.length && /^ {0,3}>/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^ {0,3}>\s?/, ""));
        index += 1;
      }
      const quote = documentRef.createElement("blockquote");
      appendInline(quote, quoteLines.join("\n"), documentRef, budget);
      fragment.append(quote);
      continue;
    }

    const unordered = unorderedMatch(line);
    const ordered = orderedMatch(line);
    if (unordered || ordered) {
      const list = documentRef.createElement(ordered ? "ol" : "ul");
      const listStart = Number(ordered && ordered[1]);
      if (ordered && Number.isSafeInteger(listStart) && listStart > 1 && listStart <= 999999) {
        list.start = listStart;
      }
      let itemCount = 0;
      while (index < lines.length && itemCount < MAX_LIST_ITEMS) {
        const itemMatch = ordered ? orderedMatch(lines[index]) : unorderedMatch(lines[index]);
        if (!itemMatch) break;
        const itemLines = [itemMatch[ordered ? 2 : 1]];
        index += 1;
        while (
          index < lines.length && lines[index].trim() &&
          !(ordered ? orderedMatch(lines[index]) : unorderedMatch(lines[index])) &&
          !isBlockStart(lines, index)
        ) {
          itemLines.push(lines[index].trim());
          index += 1;
        }
        const item = documentRef.createElement("li");
        appendInline(item, itemLines.join(" "), documentRef, budget);
        list.append(item);
        itemCount += 1;
      }
      fragment.append(list);
      if (itemCount === MAX_LIST_ITEMS) {
        const overflowStart = index;
        while (index < lines.length && (ordered ? orderedMatch(lines[index]) : unorderedMatch(lines[index]))) {
          index += 1;
        }
        if (index > overflowStart) {
          appendPlainBlock(fragment, lines.slice(overflowStart, index).join("\n"), documentRef);
        }
      }
      continue;
    }

    const paragraphLines = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines, index)) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    const paragraph = documentRef.createElement("p");
    appendInline(paragraph, paragraphLines.join(" "), documentRef, budget);
    fragment.append(paragraph);
  }

  return fragment;
}
