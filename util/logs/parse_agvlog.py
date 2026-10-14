#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_agvlog —— AGV 日志解压工具 / 库

核心解压逻辑来自对 parsezlib_2_7_8.exe 的完整静态反编译，已用真实日志做过
逐字节比对（输出 sha256 与 exe 产出完全相同）。命令行与 API 在其之上做了
工程化补全：支持指定路径 / 递归 / 输出目录 / 流式处理 / 结果对象。

    util/tool/parsezlib_2_7_8.exe
    sha256 aa5108c2f794243f5d42ee21738f826bee791831bc2cfcfa6a1597dcfb64b83e

--------------------------------------------------------------------
数据格式（与原程序 0x4014d0 / 0x403f20 一致）
--------------------------------------------------------------------
日志由若干块首尾相接组成，每块两种之一：

    "$AGV" 压缩块
        0..3    b"$AGV"
        4..7    保留字段（原程序读进寄存器但未使用，实测恒为 0）
        8..11   u32 小端 = csize，后面 zlib 流的字节数
        12..    zlib 流（csize 字节），解压后写出

    "#AGV" 明文块
        0..3    b"#AGV"
        4..7    u32 大端 = size
        8..     size 字节原始数据，直接写出

    两者都不匹配 -> 结束。zlib 解压用 uncompress()，目标缓冲上限 0x500000。

--------------------------------------------------------------------
输出文件名（与原程序 0x4013c0 一致）
--------------------------------------------------------------------
    exe 规则： name[len-4:] + "_" + name[:len-5] + ".txt"
        AGV_2026_05_21_23_31_33_CASTOR_1051
        -> 1051_AGV_2026_05_21_23_31_33_CASTOR.txt
      （该规则硬假定设备号恰好 4 位；不是 4 位就会切错。）
    smart 规则：以最后一个 '_' 分界，任意长度设备号都正确。

输出默认用文本模式写出（每个 \\n 变 \\r\\n），与原 exe 的 fopen "w+" 一致。

--------------------------------------------------------------------
作为库调用
--------------------------------------------------------------------
    from parse_agvlog import decompress_file, parse_file, iter_chunks, codec_for

    # 1) 只要解压出来的字节
    data = decompress_file(r"D:\\log\\AGV_2026_05_21_23_31_33_CASTOR_1051")

    # 2) 解压到文件，拿结构化结果
    r = parse_file(src, dst=None)        # dst=None 时按命名规则自动生成
    print(r.ok, r.chunks, r.out_bytes, r.error)

    # 3) 自己流式消费每一块（大文件不必整份读进内存）
    with open(src, "rb") as fh:
        for i, blob in enumerate(iter_chunks(fh)):
            ...

--------------------------------------------------------------------
关于其它日志类型
--------------------------------------------------------------------
原 exe 一共认 7 个通配符，路由到 5 个解析器：

    AGV_* DEP_* SLA_*  -> AGV_LOG_PARSER     已实现（本文件）
    SENS*              -> SENS_LOG_PARSER    已实现（同逻辑，二进制写出）
    RCD_*              -> RCD_LOG_PARSER     输出是 SQLite 库，未实现
    SLM_*              -> SLAM_LOG_PARSER    写出函数未反编译，未实现
    DSP_*              -> DSP_LOG_PARSER     格式已知但无样本，未实现

未实现的类型会被识别出来并明确报告，不会被当成 AGV 日志错解。
"""

from __future__ import annotations

import argparse
import os
import sys
import zlib
from dataclasses import dataclass, field
from typing import BinaryIO, Callable, Iterable, Iterator, List, Optional, Sequence, Tuple

__version__ = "1.0.0"

__all__ = [
    "MAGIC_COMPRESSED",
    "MAGIC_PLAIN",
    "DST_CAP",
    "ALL_PREFIXES",
    "PLAN",
    "Codec",
    "AGV_CODEC",
    "SENS_CODEC",
    "ParseError",
    "UnsupportedLogType",
    "ParseResult",
    "zlib_uncompress",
    "iter_chunks",
    "decompress_bytes",
    "decompress_file",
    "codec_for",
    "output_name_for",
    "parse_file",
    "collect_inputs",
    "parse_paths",
    "main",
]

# ----------------------------------------------------------------- 常量

MAGIC_COMPRESSED = b"$AGV"
MAGIC_PLAIN = b"#AGV"
DST_CAP = 0x500000              # 原程序 0x403fc8：uncompress 目标缓冲上限

# 原 exe 的扫描顺序：通配符 -> 解析器
PLAN: Tuple[Tuple[str, Optional[str]], ...] = (
    ("AGV_", "agv"),
    ("DEP_", "agv"),
    ("SLA_", "agv"),
    ("RCD_", None),
    ("SLM_", None),
    ("DSP_", None),
    ("SENS", "sens"),
)
ALL_PREFIXES: Tuple[str, ...] = tuple(p for p, _ in PLAN)

UNSUPPORTED_REASON = {
    "RCD_": "RCD_LOG_PARSER：输出为 SQLite 数据库（RCD_DATA/NOTE 表），未实现",
    "SLM_": "SLAM_LOG_PARSER：写函数 0x4065a0 未反编译，格式未确认",
    "DSP_": "DSP_LOG_PARSER：定长 1632 字节记录 + 表头，无样本可验证",
}


# ----------------------------------------------------------------- 异常


class ParseError(Exception):
    """日志内容不合法（头部截断、zlib 数据损坏等）。"""


class UnsupportedLogType(ParseError):
    """识别出属于尚未实现的解析器类型。"""


# ----------------------------------------------------------------- 编解码器


@dataclass(frozen=True)
class Codec:
    """一种解析器的行为参数，与原 exe 的虚函数组合一一对应。"""

    name: str
    text: bool          # True = 输出文本模式（\\n -> \\r\\n），对应 fopen "w+"
    plain: bool         # True = 处理 "#AGV" 明文块，对应 0x4014d0 相对 0x404050 的差别
    ext: str = ".txt"

    def suffix(self) -> str:
        return self.ext


AGV_CODEC = Codec(name="agv", text=True, plain=True, ext=".txt")
SENS_CODEC = Codec(name="sens", text=False, plain=False, ext=".txt")

_CODECS = {"agv": AGV_CODEC, "sens": SENS_CODEC}


def codec_for(name: str) -> Optional[Codec]:
    """按文件名前缀选解析器；返回 None 表示是该前缀未实现的类型。"""
    base = os.path.basename(name)
    for prefix, kind in PLAN:
        if base.startswith(prefix):
            return _CODECS.get(kind) if kind else None
    return None


def prefix_of(name: str) -> Optional[str]:
    base = os.path.basename(name)
    for prefix, _ in PLAN:
        if base.startswith(prefix):
            return prefix
    return None


# ----------------------------------------------------------------- 核心解压


def zlib_uncompress(src: bytes, cap: int = DST_CAP) -> Tuple[int, bytes]:
    """等价于 zlib 的 uncompress(dst, &dstLen=cap, src, len(src))。

    返回 (err, out)，err == 0 表示成功。错误码沿用 zlib：
    -3 = Z_DATA_ERROR（数据损坏）、-5 = Z_BUF_ERROR（输出超过 cap 或输入截断）。
    """
    d = zlib.decompressobj()
    try:
        out = d.decompress(src, cap)
        if not d.eof:
            return -5, out
        return 0, out + d.flush()
    except zlib.error:
        return -3, b""


def _read_exact(fh: BinaryIO, n: int) -> bytes:
    """尽量读满 n 字节（read 不保证一次读完）。"""
    if n <= 0:
        return b""
    parts = []
    got = 0
    while got < n:
        chunk = fh.read(n - got)
        if not chunk:
            break
        parts.append(chunk)
        got += len(chunk)
    return b"".join(parts)


def iter_chunks(
    fh: BinaryIO,
    *,
    plain: bool = True,
    dst_cap: int = DST_CAP,
) -> Iterator[bytes]:
    """流式解析，逐块产出解压后的数据。

    对应原程序 0x404340 里 ``pos = vtable+0x0c(...)`` 的循环。文件尾部出现
    未知标记或读到文件尾即正常结束（原程序返回 0，同样如此）。
    """
    while True:
        magic = fh.read(4)
        if len(magic) < 4:
            return                      # 干净结束

        if plain and magic == MAGIC_PLAIN:
            head = fh.read(4)
            if len(head) < 4:
                return                  # 头部截断，按原程序语义干净结束
            size = int.from_bytes(head, "big")
            blob = _read_exact(fh, size)
            if len(blob) != size:
                raise ParseError(
                    "明文块被截断：声明 %d 字节，实际只有 %d 字节" % (size, len(blob))
                )
            yield blob
            continue

        if magic == MAGIC_COMPRESSED:
            head = fh.read(8)
            if len(head) < 8:
                return                  # 头部截断，干净结束
            csize = int.from_bytes(head[4:8], "little")
            src = _read_exact(fh, csize)
            if len(src) != csize:
                return                  # 数据截断：原程序 (csize+12 > remaining) 也是返回 0
            err, out = zlib_uncompress(src, dst_cap)
            if err != 0:
                raise ParseError(
                    "zlib 解压失败：uncompress 返回 %d（dst_len 上限 %d，src_len %d）,[-3 = Z_DATA_ERROR（数据损坏）、-5 = Z_BUF_ERROR（输出超过 cap 或输入截断）。]"
                    % (err, dst_cap, csize)
                )
            yield out
            continue

        return                          # 未知标记，干净结束


def decompress_bytes(data: bytes, *, plain: bool = True, dst_cap: int = DST_CAP) -> bytes:
    """把整份日志字节解压成原始字节（不分块拼接）。"""
    import io

    return b"".join(iter_chunks(io.BytesIO(data), plain=plain, dst_cap=dst_cap))


def decompress_file(
    src: os.PathLike | str,
    *,
    codec: Optional[Codec] = None,
    dst_cap: int = DST_CAP,
) -> bytes:
    """读取日志文件并返回解压后的原始字节（不落盘、不做换行转换）。"""
    c = codec or codec_for(os.fspath(src)) or AGV_CODEC
    with open(src, "rb") as fh:
        return b"".join(iter_chunks(fh, plain=c.plain, dst_cap=dst_cap))


# ----------------------------------------------------------------- 输出命名


def output_name_for(name: str, *, ext: str = ".txt", rule: str = "exe") -> str:
    """由输入文件名推出输出文件名。

    rule="exe"   ：原程序 0x4013c0 的规则，假定设备号恰好 4 位。
    rule="smart" ：以最后一个 '_' 分界，任意长度设备号都正确。
    """
    base = os.path.basename(name)
    stem = base

    if rule == "exe":
        n = len(stem)
        if n < 5:
            raise ValueError("文件名太短，无法按 exe 规则构造输出名: %r" % base)
        return stem[n - 4:] + "_" + stem[:n - 5] + ext

    if rule == "smart":
        if "_" not in stem:
            return stem + "_out" + ext
        head, dev = stem.rsplit("_", 1)
        if not head:
            raise ValueError("文件名没有可用的设备号前缀: %r" % base)
        return dev + "_" + head + ext

    raise ValueError("未知的命名规则: %r" % rule)


# ----------------------------------------------------------------- 结果对象


@dataclass
class ParseResult:
    """单个文件的处理结果。"""

    src: str
    dst: Optional[str] = None
    ok: bool = False
    skipped: bool = False
    chunks: int = 0
    in_bytes: int = 0
    out_bytes: int = 0
    error: Optional[str] = None
    codec: Optional[str] = None

    @property
    def ratio(self) -> float:
        return (self.out_bytes / self.in_bytes) if self.in_bytes else 0.0

    def __bool__(self) -> bool:
        return self.ok


# ----------------------------------------------------------------- 文件级处理


def parse_file(
    src: os.PathLike | str,
    dst: Optional[os.PathLike | str] = None,
    *,
    codec: Optional[Codec] = None,
    text: Optional[bool] = None,
    dst_cap: int = DST_CAP,
    overwrite: bool = True,
    name_rule: str = "exe",
    on_chunk: Optional[Callable[[int, bytes], None]] = None,
) -> ParseResult:
    """解压一个日志文件。

    参数:
        src        输入文件
        dst        输出文件；None 表示按命名规则生成，放在输入文件同目录
        codec      解析器；None 表示按文件名前缀自动选择
        text       覆盖换行模式：True 转 \\r\\n，False 原样写；None 用 codec 的默认
        overwrite  False 且输出已存在时跳过（结果里 skipped=True）
        name_rule  自动命名规则，"exe" 或 "smart"
        on_chunk   每写出一块回调 (块序号, 原始解压数据)

    不会抛异常（输入无法打开、zlib 损坏等都会记在返回值的 error 里）。
    """
    src = os.fspath(src)
    res = ParseResult(src=src)

    prefix = prefix_of(src)
    c = codec
    if c is None:
        if prefix and prefix in UNSUPPORTED_REASON:
            res.error = "不支持的日志类型 %s：%s" % (prefix, UNSUPPORTED_REASON[prefix])
            return res
        c = codec_for(src) or AGV_CODEC
    res.codec = c.name

    ext = c.ext
    if dst is None:
        try:
            dst = os.path.join(
                os.path.dirname(os.path.abspath(src)),
                output_name_for(os.path.basename(src), ext=ext, rule=name_rule),
            )
        except ValueError as e:
            res.error = str(e)
            return res
    else:
        dst = os.fspath(dst)

    res.dst = dst
    want_text = c.text if text is None else bool(text)

    if not overwrite and os.path.exists(dst):
        res.skipped = True
        res.error = "输出已存在，跳过"
        return res

    try:
        res.in_bytes = os.path.getsize(src)
    except OSError as e:
        res.error = "无法读取输入文件: %s" % e
        return res

    try:
        fh_in = open(src, "rb")
    except OSError as e:
        res.error = "Open input file %s failed: %s" % (src, e)
        return res

    try:
        parent = os.path.dirname(os.path.abspath(dst))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        fh_out = open(dst, "wb")            # 文本转换自己做，保证逐字节可控
    except OSError as e:
        fh_in.close()
        res.error = "Open output file %s failed: %s" % (dst, e)
        return res

    try:
        for blob in iter_chunks(fh_in, plain=c.plain, dst_cap=dst_cap):
            if on_chunk is not None:
                on_chunk(res.chunks, blob)
            fh_out.write(blob.replace(b"\n", b"\r\n") if want_text else blob)
            res.chunks += 1
            res.out_bytes += len(blob)
        res.ok = True
    except ParseError as e:
        res.error = str(e)
    except OSError as e:
        res.error = "写出失败: %s" % e
    finally:
        try:
            fh_out.close()
        except OSError:
            pass
        fh_in.close()

    return res


# ----------------------------------------------------------------- 输入收集

_WILDCARDS = ("*", "?", "[")


def collect_inputs(
    paths: Sequence[str],
    *,
    recursive: bool = False,
    prefixes: Sequence[str] = ALL_PREFIXES,
) -> Iterator[str]:
    """把用户给的路径展开成待处理的文件列表。

    路径可以是文件、目录（扫描其中的日志）或通配符。目录中的文件只保留开头
    匹配 ``prefixes`` 的，按名字排序，结果可复现。
    """
    import glob as _glob

    seen = set()
    for raw in paths:
        p = os.fspath(raw)
        if any(ch in p for ch in _WILDCARDS):
            matches = sorted(_glob.glob(p, recursive=recursive))
            for m in matches:
                if os.path.isfile(m) and m not in seen:
                    seen.add(m)
                    yield m
            continue

        if os.path.isfile(p):
            if p not in seen:
                seen.add(p)
                yield p
            continue

        if not os.path.isdir(p):
            continue

        if recursive:
            walker = (
                os.path.normpath(os.path.join(root, fn))
                for root, _dirs, files in os.walk(p)
                for fn in files
            )
        else:
            walker = (os.path.normpath(os.path.join(p, fn)) for fn in os.listdir(p))

        for full in sorted(walker):
            if not os.path.isfile(full):
                continue
            if not os.path.basename(full).startswith(tuple(prefixes)):
                continue
            if full in seen:
                continue
            seen.add(full)
            yield full


def parse_paths(
    paths: Sequence[str],
    *,
    output_dir: Optional[str] = None,
    recursive: bool = False,
    prefixes: Sequence[str] = ALL_PREFIXES,
    text: Optional[bool] = None,
    dst_cap: int = DST_CAP,
    overwrite: bool = True,
    name_rule: str = "exe",
) -> Iterator[ParseResult]:
    """批量处理，逐个产出 ParseResult（不打印任何东西）。"""
    for src in collect_inputs(paths, recursive=recursive, prefixes=prefixes):
        dst = None
        if output_dir:
            prefix = prefix_of(src) or ""
            c = codec_for(src)
            if c is None and prefix in UNSUPPORTED_REASON:
                yield ParseResult(
                    src=src,
                    error="不支持的日志类型 %s：%s" % (prefix, UNSUPPORTED_REASON[prefix]),
                )
                continue
            try:
                dst = os.path.join(
                    output_dir,
                    output_name_for(
                        os.path.basename(src), ext=(c or AGV_CODEC).ext, rule=name_rule
                    ),
                )
            except ValueError as e:
                yield ParseResult(src=src, error=str(e))
                continue
        yield parse_file(
            src,
            dst,
            text=text,
            dst_cap=dst_cap,
            overwrite=overwrite,
            name_rule=name_rule,
        )


# ----------------------------------------------------------------- 命令行


def _fmt_bytes(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    f = float(n)
    i = 0
    while f >= 1024.0 and i < len(units) - 1:
        f /= 1024.0
        i += 1
    return "%d %s" % (n, units[0]) if i == 0 else "%.2f %s" % (f, units[i])


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="parse_agvlog",
        description="解压 AGV 日志（parsezlib_2_7_8.exe 的等价实现）。",
        epilog=(
            "不带路径时处理当前目录，与原始 exe 一致。\n"
            "示例:\n"
            "  parse_agvlog.py                          # 解压当前目录\n"
            "  parse_agvlog.py D:\\logs                  # 解压指定目录\n"
            "  parse_agvlog.py D:\\logs -r -o D:\\out    # 递归 + 指定输出目录\n"
            "  parse_agvlog.py AGV_2026*.log -v         # 通配符 + 详细信息\n"
            "\n"
            "中文提示按系统编码输出；在 UTF-8 终端（Git Bash / mintty 等）里如见乱码，\n"
            "先设环境变量 PYTHONUTF8=1。\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "paths",
        nargs="*",
        help="文件 / 目录 / 通配符；省略则处理当前目录",
    )
    p.add_argument("-o", "--output-dir", metavar="DIR", help="输出目录（默认与输入同目录）")
    p.add_argument("-r", "--recursive", action="store_true", help="目录递归处理")
    p.add_argument(
        "-p",
        "--prefix",
        action="append",
        metavar="PREFIX",
        help="只处理这些前缀（可重复）；默认全部 7 个原版通配符",
    )
    p.add_argument(
        "-m",
        "--mode",
        choices=("auto", "text", "binary"),
        default="auto",
        help="换行模式：auto 按解析器（默认），text 转 \\r\\n，binary 原样",
    )
    p.add_argument(
        "--name-rule",
        choices=("exe", "smart"),
        default="exe",
        help="输出命名规则：exe 完全复刻原程序（设备号须 4 位），smart 以最后一个下划线分界",
    )
    p.add_argument("-n", "--no-clobber", action="store_true", help="输出已存在则跳过（默认覆盖）")
    p.add_argument("--dst-cap", type=int, default=DST_CAP, metavar="N",
                   help="单块解压缓冲上限，默认 %d（原程序值）" % DST_CAP)
    p.add_argument("--dry-run", action="store_true", help="只列出将要处理的文件")
    p.add_argument("--stats", action="store_true", help="结束时打印汇总")
    p.add_argument("-q", "--quiet", action="store_true", help="只输出错误")
    p.add_argument("-v", "--verbose", action="store_true", help="输出每个文件的细节")
    p.add_argument("--version", action="version", version="parse_agvlog %s" % __version__)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    prefixes = tuple(args.prefix) if args.prefix else ALL_PREFIXES
    text = {"auto": None, "text": True, "binary": False}[args.mode]
    paths = args.paths or ["."]

    if args.verbose and args.quiet:
        sys.stderr.write("[-q] 与 [-v] 同时给出，按 -q 处理\n")
        args.verbose = False

    n_ok = n_fail = n_skip = 0
    total_in = total_out = 0

    for src in collect_inputs(paths, recursive=args.recursive, prefixes=prefixes):
        prefix = prefix_of(src)

        if prefix in UNSUPPORTED_REASON:
            sys.stderr.write("[跳过] %s：%s\n" % (src, UNSUPPORTED_REASON[prefix]))
            n_skip += 1
            continue

        if args.dry_run:
            try:
                dst = "自动命名"
                if args.output_dir:
                    dst = os.path.join(
                        args.output_dir,
                        output_name_for(
                            os.path.basename(src), rule=args.name_rule
                        ),
                    )
            except ValueError:
                pass
            print("%s  ->  %s" % (src, dst))
            n_ok += 1
            continue

        if not args.quiet:
            print("Parsing %s" % src)

        if args.output_dir:
            c = codec_for(src) or AGV_CODEC
            try:
                dst = os.path.join(
                    args.output_dir,
                    output_name_for(os.path.basename(src), ext=c.ext, rule=args.name_rule),
                )
            except ValueError as e:
                sys.stderr.write("[错误] %s：%s\n" % (src, e))
                n_fail += 1
                continue
        else:
            dst = None

        res = parse_file(
            src,
            dst,
            text=text,
            dst_cap=args.dst_cap,
            overwrite=not args.no_clobber,
            name_rule=args.name_rule,
        )

        total_in += res.in_bytes
        total_out += res.out_bytes

        if res.skipped:
            n_skip += 1
            if not args.quiet:
                print("  跳过（输出已存在）：%s" % res.dst)
            continue

        if res.ok:
            n_ok += 1
            if args.verbose:
                print(
                    "  -> %s  (%d 块, %s -> %s, %.2fx)"
                    % (res.dst, res.chunks, _fmt_bytes(res.in_bytes),
                       _fmt_bytes(res.out_bytes), res.ratio)
                )
            elif not args.quiet:
                pass
            if not args.quiet:
                print("Parse file %s success." % src)
        else:
            n_fail += 1
            sys.stderr.write("[错误] %s：%s\n" % (src, res.error))
            if res.out_bytes and not args.quiet:
                print("  已写出 %s（不完整）" % _fmt_bytes(res.out_bytes))

    if args.stats and not args.dry_run:
        print(
            "汇总: 成功 %d, 失败 %d, 跳过 %d；%s -> %s"
            % (n_ok, n_fail, n_skip, _fmt_bytes(total_in), _fmt_bytes(total_out))
        )

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
