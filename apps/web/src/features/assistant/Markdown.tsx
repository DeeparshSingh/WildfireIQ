/**
 * A small markdown renderer for assistant answers.
 *
 * The assistant writes a constrained subset — paragraphs, bullet and
 * numbered lists, bold, inline code, and the occasional small table — so a
 * full markdown library would be several times the size of the feature it
 * serves. More importantly, this renderer builds React elements from
 * parsed text and never touches `dangerouslySetInnerHTML`, so model output
 * cannot inject markup into the page.
 */
import { Fragment, type ReactNode } from "react";

const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`)/g;

/** Split a line into bold / code / plain runs. */
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;

  for (const match of text.matchAll(INLINE_PATTERN)) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const token = match[0];
    // The offset into the source string is a stable identity for this run:
    // two identical `**High**` spans in one line still get distinct keys.
    const key = `${keyPrefix}@${match.index}`;
    if (token.startsWith("**")) {
      nodes.push(
        <strong key={key} style={{ color: "var(--color-text-hi)", fontWeight: 600 }}>
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      nodes.push(
        <code
          key={key}
          style={{
            fontFamily: "var(--font-data)",
            fontSize: "0.92em",
            background: "var(--color-bg-3)",
            padding: "1px 5px",
            borderRadius: 4,
          }}
        >
          {token.slice(1, -1)}
        </code>,
      );
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

/**
 * Parsed blocks carry the source line they started on. That gives every
 * rendered node a key derived from where it came from in the answer rather
 * than from its position in an array — which matters here, because the
 * answer is re-parsed on every streamed token and array positions shift
 * under React as the text grows.
 */
type Line = { text: string; at: number };
type Cell = { value: string; key: string };
type Row = { cells: Cell[]; at: number };

type Block =
  | { kind: "p"; at: number; lines: Line[] }
  | { kind: "ul" | "ol"; at: number; items: Line[] }
  | { kind: "table"; at: number; rows: Row[] };

function splitRow(line: string, at: number): Row {
  const cells = line
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell, column) => ({ value: cell.trim(), key: `r${at}c${column}` }));
  return { cells, at };
}

const isDivider = (line: string) => /^\|?[\s:|-]+\|[\s:|-]*$/.test(line) && line.includes("-");

const BULLET = /^\s*[-*+]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;

function parse(markdown: string): Block[] {
  const blocks: Block[] = [];
  const lines = markdown.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const start = i;

    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (line.includes("|") && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const rows: Row[] = [splitRow(line, i)];
      i += 2;
      while (i < lines.length && lines[i].includes("|")) {
        rows.push(splitRow(lines[i], i));
        i += 1;
      }
      blocks.push({ kind: "table", at: start, rows });
      continue;
    }

    if (BULLET.test(line) || NUMBERED.test(line)) {
      const ordered = NUMBERED.test(line);
      const items: Line[] = [];
      while (i < lines.length && (BULLET.test(lines[i]) || NUMBERED.test(lines[i]))) {
        items.push({ text: lines[i].replace(BULLET, "").replace(NUMBERED, ""), at: i });
        i += 1;
      }
      blocks.push({ kind: ordered ? "ol" : "ul", at: start, items });
      continue;
    }

    const paragraph: Line[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !BULLET.test(lines[i]) &&
      !NUMBERED.test(lines[i])
    ) {
      // Strip heading markers: the assistant is asked not to use them, but
      // rendering a stray "###" as literal text looks worse than dropping it.
      paragraph.push({ text: lines[i].replace(/^#{1,6}\s+/, ""), at: i });
      i += 1;
    }
    blocks.push({ kind: "p", at: start, lines: paragraph });
  }

  return blocks;
}

export function Markdown({ text }: { text: string }) {
  const blocks = parse(text);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {blocks.map((block) => {
        const key = `b${block.at}`;

        if (block.kind === "p") {
          return (
            <p key={key} style={{ margin: 0, lineHeight: 1.6 }}>
              {block.lines.map((line, offset) => (
                <Fragment key={`${key}L${line.at}`}>
                  {offset > 0 && " "}
                  {renderInline(line.text, `${key}L${line.at}`)}
                </Fragment>
              ))}
            </p>
          );
        }

        if (block.kind === "table") {
          const [header, ...body] = block.rows;
          return (
            <div key={key} style={{ overflowX: "auto" }}>
              <table
                style={{
                  borderCollapse: "collapse",
                  fontSize: 12,
                  fontFamily: "var(--font-data)",
                  minWidth: "100%",
                }}
              >
                <thead>
                  <tr>
                    {header.cells.map((cell) => (
                      <th
                        key={cell.key}
                        style={{
                          textAlign: "left",
                          padding: "4px 10px 4px 0",
                          color: "var(--color-text-low)",
                          fontWeight: 500,
                          borderBottom: "1px solid var(--color-stroke)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {cell.value}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((row) => (
                    <tr key={`row${row.at}`}>
                      {row.cells.map((cell) => (
                        <td
                          key={cell.key}
                          style={{
                            padding: "4px 10px 4px 0",
                            color: "var(--color-text-mid)",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {renderInline(cell.value, cell.key)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        const ListTag = block.kind === "ol" ? "ol" : "ul";
        return (
          <ListTag
            key={key}
            style={{
              margin: 0,
              paddingLeft: 18,
              display: "flex",
              flexDirection: "column",
              gap: 4,
              lineHeight: 1.55,
            }}
          >
            {block.items.map((item) => (
              <li key={`${key}I${item.at}`}>{renderInline(item.text, `${key}I${item.at}`)}</li>
            ))}
          </ListTag>
        );
      })}
    </div>
  );
}
