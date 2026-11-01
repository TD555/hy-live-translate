"""Convert a Claude data export (conversations.json) into one Markdown file per chat.

The text is copied as-is: no message is edited, shortened or dropped. Content blocks
this script doesn't know are written out as raw JSON instead of being skipped.

Usage (PowerShell):
  python export_chats.py conversations.json --list
  python export_chats.py conversations.json --uuid <uuid> --uuid <uuid> --out chats
"""
import argparse
import json
import re
import sys
from pathlib import Path


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        sys.exit(f"Expected a list of conversations in {path}, got {type(data).__name__}")
    return data


def fence(text, lang=""):
    ticks = "````" if "```" in text else "```"
    return f"{ticks}{lang}\n{text}\n{ticks}"


def render_block(block):
    kind = block.get("type")
    if kind == "text":
        return block.get("text", "")
    if kind == "thinking":
        body = block.get("thinking", "")
        return "> **Thinking:**\n" + "\n".join("> " + line for line in body.splitlines())
    if kind == "tool_use":
        args = json.dumps(block.get("input", {}), ensure_ascii=False, indent=2)
        return f"**Tool call: `{block.get('name', '?')}`**\n\n" + fence(args, "json")
    if kind == "tool_result":
        content = block.get("content", "")
        if isinstance(content, list):
            parts = [c.get("text", json.dumps(c, ensure_ascii=False)) for c in content]
            content = "\n".join(parts)
        return f"**Tool result ({block.get('name', '')})**\n\n" + fence(str(content))
    # Unknown block type: keep it, never drop it.
    return f"**[{kind} block]**\n\n" + fence(json.dumps(block, ensure_ascii=False, indent=2), "json")


def render_message(msg):
    who = {"human": "User", "assistant": "Claude"}.get(msg.get("sender"), msg.get("sender", "?"))
    parts = [f"## {who} — {msg.get('created_at', '')}"]
    blocks = msg.get("content")
    if blocks:
        parts += [render_block(b) for b in blocks]
    elif msg.get("text") is not None:
        parts.append(msg["text"])
    else:
        raise ValueError(f"Message {msg.get('uuid')} has neither 'content' nor 'text'")
    for att in msg.get("attachments") or []:
        name = att.get("file_name", "attachment")
        parts.append(f"**Attachment: {name}**\n\n" + fence(att.get("extracted_content", "")))
    for f in msg.get("files") or []:
        parts.append(f"**File: {f.get('file_name', '?')}** (file content not included in the export)")
    return "\n\n".join(parts)


def render_chat(conv):
    header = [
        f"# {conv.get('name') or '(untitled)'}",
        "",
        f"- Conversation id: `{conv.get('uuid')}`",
        f"- Created: {conv.get('created_at')}",
        f"- Last updated: {conv.get('updated_at')}",
        "- Source: Claude data export (Settings > Privacy > Export data), converted by `export_chats.py` without edits.",
        "",
        "---",
    ]
    msgs = conv.get("chat_messages")
    if msgs is None:
        raise ValueError(f"Conversation {conv.get('uuid')} has no 'chat_messages'")
    return "\n".join(header) + "\n\n" + "\n\n---\n\n".join(render_message(m) for m in msgs) + "\n"


def slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", text or "untitled").strip("-").lower()[:60] or "untitled"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("export", help="conversations.json from the Claude data export")
    p.add_argument("--list", action="store_true", help="print all chats and exit")
    p.add_argument("--uuid", action="append", default=[], help="conversation id to export (repeatable)")
    p.add_argument("--out", default="chats")
    args = p.parse_args()

    convs = load(args.export)
    if args.list:
        for c in sorted(convs, key=lambda c: c.get("created_at", "")):
            n = len(c.get("chat_messages") or [])
            print(f"{c.get('created_at', '')[:16]}  {c.get('uuid')}  {n:4d} msgs  {c.get('name') or '(untitled)'}")
        return
    if not args.uuid:
        sys.exit("Give at least one --uuid (see --list)")

    by_id = {c.get("uuid"): c for c in convs}
    missing = [u for u in args.uuid if u not in by_id]
    if missing:
        sys.exit(f"Not found in the export: {', '.join(missing)}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    chosen = sorted((by_id[u] for u in args.uuid), key=lambda c: c.get("created_at", ""))
    for i, conv in enumerate(chosen, 1):
        path = out / f"{i:02d}-{conv.get('created_at', '')[:10]}-{slug(conv.get('name'))}.md"
        path.write_text(render_chat(conv), encoding="utf-8")
        print(f"wrote {path}  ({len(conv['chat_messages'])} messages)")


if __name__ == "__main__":
    main()
