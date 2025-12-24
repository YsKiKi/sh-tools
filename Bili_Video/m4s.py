import os
import shutil
import subprocess
import threading
import json
import re
from pathlib import Path
from typing import Tuple, List

def find_m4s_pairs(input_dir: Path) -> List[Tuple[Path, Path]]:
    """查找input目录下所有子文件夹中的m4s文件对"""
    pairs = []
    for sub_dir in input_dir.iterdir():
        if sub_dir.is_dir():
            m4s_files = list(sub_dir.glob("*.m4s"))
            if len(m4s_files) != 2:
                raise ValueError(f"子文件夹 {sub_dir.name} 下需存在且仅存在2个.m4s文件，当前找到{len(m4s_files)}个")
            
            pairs.append((m4s_files[0], m4s_files[1]))
    
    if not pairs:
        raise ValueError("input目录下未找到任何有效的子文件夹（包含一对m4s文件）")
    
    return pairs


def remove_leading_zeros(input_file: Path, output_file: Path) -> None:
    """高效删除文件开头的连续0字符"""
    BLOCK_SIZE = 1024 * 1024  # 1MB块大小
    zero_byte = b'\x00'
    
    with open(input_file, "rb") as in_f, open(output_file, "wb") as out_f:
        # 第一阶段：跳过开头的连续0
        while True:
            chunk = in_f.read(BLOCK_SIZE)
            if not chunk:
                break  # 文件全是0
            
            # 找到第一个非0字节的位置
            non_zero_pos = chunk.find(zero_byte)
            if non_zero_pos == -1:
                continue  # 该块全是0
            
            # 写入非0部分
            out_f.write(chunk[non_zero_pos:])
            break
        
        # 第二阶段：写入剩余所有内容
        while True:
            chunk = in_f.read(BLOCK_SIZE)
            if not chunk:
                break
            out_f.write(chunk)


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """清理文件名中不可用于文件系统的字符"""
    if not isinstance(name, str):
        name = str(name)
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', replacement, name)
    return name[:200].rstrip()


def get_output_filename_from_video_info(folder: Path, fallback_stem: str) -> str:
    """尝试从videoInfo.json读取标题信息生成文件名"""
    info_path = folder / "videoInfo.json"
    if not info_path.exists():
        return f"{fallback_stem}.mp4"
    
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        title = data.get("title")
        uname = data.get("uname")
        if title and uname:
            title_s = sanitize_filename(title)
            uname_s = sanitize_filename(uname)
            return f"{title_s} - {uname_s}.mp4"
        else:
            return f"{fallback_stem}.mp4"
    except Exception:
        return f"{fallback_stem}.mp4"


def process_file_pair(file1: Path, file2: Path, temp_dir: Path, output_dir: Path, ffmpeg_path: str) -> None:
    """处理单个文件对：清理0字符 → 区分音视频 → 合并为MP4"""
    # 步骤1：清理文件开头的0（多线程处理）
    temp_file1 = temp_dir / file1.name
    temp_file2 = temp_dir / file2.name
    
    thread1 = threading.Thread(target=remove_leading_zeros, args=(file1, temp_file1))
    thread2 = threading.Thread(target=remove_leading_zeros, args=(file2, temp_file2))
    
    thread1.start()
    thread2.start()
    thread1.join()
    thread2.join()
    
    # 步骤2：区分视频（大文件）和音频（小文件）
    size1 = temp_file1.stat().st_size
    size2 = temp_file2.stat().st_size
    
    video_file = temp_file1 if size1 > size2 else temp_file2
    audio_file = temp_file2 if size1 > size2 else temp_file1
    
    # 步骤3：决定输出文件名
    parent_folder = file1.parent
    fallback_stem = file1.stem.split('-')[0]
    output_filename = get_output_filename_from_video_info(parent_folder, fallback_stem)
    output_path = output_dir / output_filename
    
    cmd = [
        ffmpeg_path,
        "-i", str(video_file),
        "-i", str(audio_file),
        "-codec", "copy",
        "-y",  # 覆盖已存在的文件
        str(output_path)
    ]
    
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg执行失败：{e}")
    finally:
        # 清理临时文件
        temp_file1.unlink(missing_ok=True)
        temp_file2.unlink(missing_ok=True)
