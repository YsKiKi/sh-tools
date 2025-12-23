import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Tuple, List
import ctypes
from pathlib import Path

def get_special_folder_path(folder_id):
    """获取 Windows 特殊文件夹路径"""
    SHGFP_TYPE_CURRENT = 0
    
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, folder_id, None, SHGFP_TYPE_CURRENT, buf)
    
    return Path(buf.value)

# Videos 文件夹的 CSIDL（常数ID）
CSIDL_MYVIDEO = 0x000E

SCRIPT_DIR = Path(__file__).parent                                  # 脚本所在目录
INPUT_DIR = get_special_folder_path(CSIDL_MYVIDEO) / "bilibili"     # 输入目录
OUTPUT_DIR = SCRIPT_DIR / "output"                                  # 输出目录
TEMP_DIR = SCRIPT_DIR / "temp"                                      # 临时文件目录（存放清理后的m4s）
FFMPEG_PATH = "ffmpeg"                                              # ffmpeg路径（若未加入环境变量，需指定绝对路径）

# 创建必要目录
for dir_path in [INPUT_DIR, OUTPUT_DIR, TEMP_DIR]:
    dir_path.mkdir(exist_ok=True)


def find_m4s_pairs() -> List[Tuple[Path, Path]]:
    """
    查找input目录下所有子文件夹中的m4s文件对（每个子文件夹中两个文件）
    返回格式：[(文件1路径, 文件2路径), ...]
    """
    pairs = []
    for sub_dir in INPUT_DIR.iterdir():
        if sub_dir.is_dir():
            m4s_files = list(sub_dir.glob("*.m4s"))
            if len(m4s_files) != 2:
                raise ValueError(f"子文件夹 {sub_dir.name} 下需存在且仅存在2个.m4s文件，当前找到{len(m4s_files)}个")
            
            pairs.append((m4s_files[0], m4s_files[1]))
    
    if not pairs:
        raise ValueError("input目录下未找到任何有效的子文件夹（包含一对m4s文件）")
    
    return pairs


def remove_leading_zeros(input_file: Path, output_file: Path) -> None:
    """
    高效删除文件开头的连续0字符（支持超大文件，逐块处理）
    :param input_file: 原始文件路径
    :param output_file: 清理后的文件路径
    """
    BLOCK_SIZE = 1024 * 1024  # 1MB块大小（可根据内存调整）
    zero_byte = b'\x00'
    
    with open(input_file, "rb") as in_f, open(output_file, "wb") as out_f:
        # 第一阶段：跳过开头的连续0
        while True:
            chunk = in_f.read(BLOCK_SIZE)
            if not chunk:
                break  # 文件全是0
            
            # 找到第一个非0字节的位置
            non_zero_idx = chunk.find(zero_byte)
            if non_zero_idx == -1:
                continue  # 该块全是0
            
            # 写入非0部分
            out_f.write(chunk[non_zero_idx:])
            break
        
        # 第二阶段：写入剩余所有内容
        while True:
            chunk = in_f.read(BLOCK_SIZE)
            if not chunk:
                break
            out_f.write(chunk)


def process_file_pair(file1: Path, file2: Path) -> None:
    """
    处理单个文件对：清理0字符 → 区分音视频 → 合并为MP4
    """
    # 步骤1：清理文件开头的0（多线程处理）
    temp_file1 = TEMP_DIR / file1.name
    temp_file2 = TEMP_DIR / file2.name
    
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
    
    # 步骤3：调用ffmpeg合并
    output_filename = f"{file1.stem.split('-')[0]}.mp4"
    output_path = OUTPUT_DIR / output_filename
    
    cmd = [
        FFMPEG_PATH,
        "-i", str(video_file),
        "-i", str(audio_file),
        "-codec", "copy",
        "-y",  # 覆盖已存在的文件
        str(output_path)
    ]
    
    try:
        # 执行ffmpeg命令，隐藏输出（如需调试可去掉stdout/stderr）
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"✅ 合并完成：{output_path}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg执行失败：{e}")
    finally:
        # 清理临时文件
        temp_file1.unlink(missing_ok=True)
        temp_file2.unlink(missing_ok=True)


def main():
    try:
        # 查找m4s文件对
        file_pairs = find_m4s_pairs()
        
        # 处理每个文件对
        for file1, file2 in file_pairs:
            print(f"开始处理文件对：{file1.name} 和 {file2.name}")
            process_file_pair(file1, file2)
        
        print("\n🎉 所有文件处理完成！输出文件位于：", OUTPUT_DIR)
    
    except Exception as e:
        print(f"❌ 处理失败：{e}")
        # 清理临时文件
        for temp_file in TEMP_DIR.glob("*.m4s"):
            temp_file.unlink(missing_ok=True)
        exit(1)


if __name__ == "__main__":
    main()