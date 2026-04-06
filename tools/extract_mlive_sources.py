import argparse
import json
import re
import subprocess
import time
from pathlib import Path


WELCOME_URL_PATTERN = re.compile(
    r"(?:\x01\u0545F|\x01ՅF)?([^\x00\r\n]{1,36})\s*https?://(?:thirdwx\.qlogo\.cn/mmopen/vi_32|thirdqq\.qlogo\.cn/g\?b=sdk|pic6\.y\.qq\.com/qqmusic/avatar)/[^ \r\n]+/(?:132f|140f|1400)\x12([^\x00\r\n]{2,24})"
)
BARRAGE_STRUCT_PATTERN = re.compile(
    r"(?:\x01\u0545F|\x01ՅF)([^\x00\r\n]{1,36})\s*(https?://[^ \r\n]+/(?:132f|140f|1400))([^\x00\r\n]{1,120})\}",
    re.S,
)
BARRAGE_FALLBACK_PATTERN = re.compile(
    r"([A-Za-z0-9_\u4e00-\u9fff🦋✨😄😎🤗💞'@#·]{2,36})\s*[Vv][LlTt]?\s*https?://[^ \r\n]+/(?:132f|140f|1400)([^\x00\r\n]{1,140})\}",
    re.S,
)
WELCOME_HINT_KEYWORDS = ("进入了直播间", "加入了直播间", "通过关注进入直播间", "来了")
GIFT_HINT_KEYWORDS = ("送", "礼物", "x", "X", "×", "MVP", "点赞")
MOJIBAKE_HINT_CHARS = "杩涘叆鎺掍綅缁撴灉鎶㈤亾鍏鏅琛屼綔"
DEFAULT_STATE_FILE = "qqmusic_live_bot/data/logs/reverse_extract_state.json"


def run(args: list[str]) -> str:
    cp = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if cp.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(args)}\n{cp.stderr}")
    return cp.stdout


def latest_network_log(serial: str) -> str:
    out = run(
        [
            "adb",
            "-s",
            serial,
            "shell",
            "ls -t /data/data/com.tencent.qqmusic/files/log/network/NI_* | head -n 1",
        ]
    ).strip()
    if not out:
        raise RuntimeError("no NI_* network log found")
    return out


def pull_file(serial: str, remote: str, local: Path) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(["adb", "-s", serial, "pull", remote, str(local)], capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr)


def adb_read_increment(serial: str, remote: str, start_offset: int) -> bytes:
    # adb shell tail is 1-based; start_offset is 0-based byte count.
    start = max(1, int(start_offset) + 1)
    cp = subprocess.run(
        ["adb", "-s", serial, "shell", f"tail -c +{start} {remote}"],
        capture_output=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", errors="ignore"))
    return cp.stdout


def adb_file_size(serial: str, remote: str) -> int:
    out = run(["adb", "-s", serial, "shell", f"wc -c < {remote}"]).strip()
    try:
        return int(out or "0")
    except ValueError:
        return 0


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def recover_mojibake(text: str) -> str:
    s = text or ""
    if not s:
        return ""
    if not any(ch in s for ch in MOJIBAKE_HINT_CHARS):
        return s
    try:
        fixed = s.encode("gb18030", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        return s
    if not fixed:
        return s
    old_cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    new_cjk = len(re.findall(r"[\u4e00-\u9fff]", fixed))
    return fixed if new_cjk >= old_cjk else s


def sanitize_user(user: str) -> str:
    user = re.sub(r"[\x00-\x1f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]", "", user)
    user = recover_mojibake(user).strip().strip(":：")
    user = re.sub(r"\s+", "", user)
    user = re.sub(r"[Vv][LlTt]?$", "", user).strip()
    if (
        len(user) >= 3
        and re.match(r"^[A-Za-z][\u4e00-\u9fff]", user)
        and not re.search(r"[A-Za-z0-9]", user[1:])
    ):
        user = user[1:]
    if not user or "http" in user.lower() or "/" in user or "&" in user:
        return ""
    if "**" in user:
        return ""
    if len(user) < 2 or len(user) > 24:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", user):
        return ""
    if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", user):
        return ""
    return user


def sanitize_msg(msg: str) -> str:
    msg = re.sub(r"[\x00-\x1f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]", "", msg or "")
    msg = recover_mojibake(msg).strip().strip(":：")
    msg = re.sub(r"\s+", "", msg)
    return msg


def extract_welcome(text: str):
    for m in WELCOME_URL_PATTERN.finditer(text):
        user = sanitize_user(m.group(1))
        msg = sanitize_msg(m.group(2))
        if not user or not msg:
            continue
        if not any(k in msg for k in WELCOME_HINT_KEYWORDS):
            continue
        yield {
            "type": "welcome",
            "user": user,
            "content": "enter",
            "raw": f"{user} 进入了直播间",
            "source": "network_welcome_struct",
        }


def extract_barrage_like(text: str):
    seen = set()
    for m in BARRAGE_STRUCT_PATTERN.finditer(text):
        user = sanitize_user(m.group(1))
        msg = sanitize_msg(m.group(3))
        if not user or not msg:
            continue
        if len(msg) < 2 or len(msg) > 48:
            continue
        if any(k in msg for k in WELCOME_HINT_KEYWORDS):
            continue

        trailing = text[m.end() : m.end() + 220]
        if "IMBarrageInfo" not in trailing:
            continue

        event_type = "barrage"
        if any(k in msg for k in GIFT_HINT_KEYWORDS):
            event_type = "gift_notice"
        row = {
            "type": event_type,
            "user": user,
            "content": msg,
            "raw": f"{user}: {msg}",
            "source": "network_barrage_struct",
        }
        key = (row["type"], row["user"], row["content"])
        if key in seen:
            continue
        seen.add(key)
        yield row

    # Fallback: some records don't carry the marker prefix but still contain nick+avatar+msg.
    for m in BARRAGE_FALLBACK_PATTERN.finditer(text):
        user = sanitize_user(m.group(1))
        msg = sanitize_msg(m.group(2))
        if not user or not msg:
            continue
        if len(msg) < 2 or len(msg) > 48:
            continue
        if any(k in msg for k in WELCOME_HINT_KEYWORDS):
            continue
        if any(k in msg for k in ("IMJoinAnimation", "IMJoinBubble", "treasureLevel", "join-room-bgpic")):
            continue
        event_type = "barrage"
        if any(k in msg for k in GIFT_HINT_KEYWORDS):
            event_type = "gift_notice"
        row = {
            "type": event_type,
            "user": user,
            "content": msg,
            "raw": f"{user}: {msg}",
            "source": "network_barrage_fallback",
        }
        key = (row["type"], row["user"], row["content"])
        if key in seen:
            continue
        seen.add(key)
        yield row


def extract_pk_markers(text: str):
    for m in re.finditer(r"(music_pk_3_[0-9_]{10,})", text):
        marker = m.group(1)
        yield {
            "type": "pk_marker",
            "user": "",
            "content": marker,
            "raw": marker,
            "source": "network_marker",
        }


def extract_barrage_candidates(text: str):
    # Loose probe: pull short CJK-like phrases around IMBarrageInfo that are not welcome copy.
    out = []
    idx = 0
    while True:
        i = text.find("IMBarrageInfo", idx)
        if i < 0:
            break
        s = max(0, i - 260)
        chunk = text[s:i]
        lines = re.findall(r"([\u4e00-\u9fffA-Za-z0-9@#💞🦋✨😄😎🤗\s]{2,36})", chunk)
        for seg in lines[-8:]:
            msg = sanitize_msg(seg)
            if not msg or len(msg) < 2:
                continue
            if any(k in msg for k in WELCOME_HINT_KEYWORDS):
                continue
            if msg in ("IMJoinAnimation", "IMJoinBubble", "IMBarrageInfo", "treasureLevel"):
                continue
            out.append(
                {
                    "type": "barrage_candidate",
                    "user": "",
                    "content": msg,
                    "raw": msg,
                    "source": "network_barrage_probe",
                    "marker_offset": i,
                }
            )
        idx = i + 1
    return dedupe(out)


def extract_barrage_blocks(text: str):
    rows = []
    idx = 0
    while True:
        i = text.find("IMBarrageInfo", idx)
        if i < 0:
            break
        s = max(0, i - 260)
        e = min(len(text), i + 80)
        snippet = text[s:e].replace("\n", " ")
        rows.append(
            {
                "type": "barrage_block",
                "source": "network_raw_block",
                "marker_offset": i,
                "snippet": snippet,
            }
        )
        idx = i + 1
    return rows


def write_jsonl(path: Path, rows: list[dict], append: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    encoding = "utf-8" if append else "utf-8-sig"
    with path.open(mode, encoding=encoding) as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def dedupe(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for r in rows:
        k = (r.get("type"), r.get("user"), r.get("content"), r.get("raw"))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="192.168.1.182:5555")
    ap.add_argument("--pull-to", default="qqmusic_live_bot/data/logs/reverse_latest_network_extract.bin")
    ap.add_argument("--out-dir", default="qqmusic_live_bot/data/logs")
    ap.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    ap.add_argument(
        "--reset-offset",
        action="store_true",
        help="reset to EOF first, then only parse new bytes after this run",
    )
    ap.add_argument(
        "--rewind-bytes",
        type=int,
        default=0,
        help="rewind current offset by N bytes before incremental read (debug/backfill)",
    )
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    pull_path = Path(args.pull_to)
    state_path = Path(args.state_file)
    state = load_state(state_path)

    remote = latest_network_log(args.serial)
    print(f"[info] remote_log={remote}")

    current_size = adb_file_size(args.serial, remote)
    prev_remote = str(state.get("remote_path", ""))
    prev_offset = int(state.get("offset", 0) or 0)

    if args.reset_offset:
        prev_offset = current_size
        print(f"[info] reset_offset=true, set offset to EOF={current_size}")

    # When rotated to a new NI file, start from EOF to avoid replay history.
    if prev_remote and prev_remote != remote:
        prev_offset = current_size
        print(f"[info] log rotated, move offset to EOF={current_size}")

    if prev_offset > current_size:
        prev_offset = 0
    if args.rewind_bytes > 0:
        prev_offset = max(0, prev_offset - int(args.rewind_bytes))
        print(f"[info] rewind-bytes={args.rewind_bytes}, adjusted offset={prev_offset}")

    blob = adb_read_increment(args.serial, remote, prev_offset)
    # keep a local snapshot of the incremental bytes for debugging
    pull_path.parent.mkdir(parents=True, exist_ok=True)
    pull_path.write_bytes(blob)
    new_offset = prev_offset + len(blob)
    print(f"[info] incremental bytes={len(blob)} offset {prev_offset} -> {new_offset}")

    welcomes = []
    barrages = []
    gifts = []
    pk_markers = []
    candidates = []
    blocks = []

    txt = blob.decode("utf-8", errors="ignore")
    now = time.time()
    for row in extract_welcome(txt):
        row["ts"] = now
        row["offset_start"] = prev_offset
        row["offset_end"] = new_offset
        welcomes.append(row)
    for row in extract_barrage_like(txt):
        row["ts"] = now
        row["offset_start"] = prev_offset
        row["offset_end"] = new_offset
        if row["type"] == "gift_notice":
            gifts.append(row)
        else:
            barrages.append(row)
    for row in extract_pk_markers(txt):
        row["ts"] = now
        row["offset_start"] = prev_offset
        row["offset_end"] = new_offset
        pk_markers.append(row)
    for row in extract_barrage_candidates(txt):
        row["ts"] = now
        row["offset_start"] = prev_offset
        row["offset_end"] = new_offset
        candidates.append(row)
    for row in extract_barrage_blocks(txt):
        row["ts"] = now
        row["offset_start"] = prev_offset
        row["offset_end"] = new_offset
        blocks.append(row)

    welcomes = dedupe(welcomes)
    barrages = dedupe(barrages)
    gifts = dedupe(gifts)
    pk_markers = dedupe(pk_markers)
    candidates = dedupe(candidates)
    blocks = dedupe(blocks)

    write_jsonl(out_dir / "reverse_welcome_from_network.jsonl", welcomes, append=True)
    write_jsonl(out_dir / "reverse_barrage_from_network.jsonl", barrages, append=True)
    write_jsonl(out_dir / "reverse_gift_from_network.jsonl", gifts, append=True)
    write_jsonl(out_dir / "reverse_pk_from_network.jsonl", pk_markers, append=True)
    write_jsonl(out_dir / "reverse_barrage_candidates.jsonl", candidates, append=True)
    write_jsonl(out_dir / "reverse_barrage_blocks.jsonl", blocks, append=True)

    state["remote_path"] = remote
    state["offset"] = new_offset
    state["updated_at"] = time.time()
    save_state(state_path, state)

    print(
        f"[summary] welcome={len(welcomes)} barrage={len(barrages)} gift={len(gifts)} pk={len(pk_markers)} candidate={len(candidates)} blocks={len(blocks)}"
    )


if __name__ == "__main__":
    main()
