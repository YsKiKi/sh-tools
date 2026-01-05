import json
import re
import os
import time
from pathlib import Path
from typing import Optional, Dict, Tuple, List
import requests
import qrcode
from io import BytesIO
from PIL import Image

# B站API端点
BILI_HEADER = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36',
    'referer': 'https://www.bilibili.com',
}

BILI_PLAY_STREAM = "https://api.bilibili.com/x/player/wbi/playurl?cid={cid}&bvid={bvid}&qn={qn}&fnval={fnval}&fourk={fourk}"
BILI_BVID_TO_CID = "https://api.bilibili.com/x/player/pagelist?bvid={bvid}&jsonp=jsonp"
BILI_VIDEO_INFO = "http://api.bilibili.com/x/web-interface/view"
BILI_BANGUMI_STREAM = "https://api.bilibili.com/pgc/player/web/playurl?ep_id={ep_id}&cid={cid}&qn={qn}&fnval={fnval}&fourk={fourk}"
BILI_EP_INFO = "https://api.bilibili.com/pgc/view/web/season?ep_id={}"
BILI_SCAN_CODE_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
BILI_SCAN_CODE_DETECT = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={}"

# 画质列表
BILI_RESOLUTION_LIST = [
    {'label': '8K 超高清', 'value': 0, 'qn': 127},
    {'label': '杜比视界', 'value': 1, 'qn': 126},
    {'label': 'HDR 真彩', 'value': 2, 'qn': 125},
    {'label': '4K 超清', 'value': 3, 'qn': 120},
    {'label': '1080P 60 高帧率', 'value': 4, 'qn': 116},
    {'label': '1080P+ 高码率', 'value': 5, 'qn': 112},
    {'label': '1080P 高清', 'value': 6, 'qn': 80},
    {'label': '720P60 高帧率', 'value': 7, 'qn': 74},
    {'label': '720P 高清', 'value': 8, 'qn': 64},
    {'label': '480P 清晰', 'value': 9, 'qn': 32},
    {'label': '360P 流畅', 'value': 10, 'qn': 16},
]

# 全局日志回调函数
_log_callback = None

def set_log_callback(callback):
    """设置日志回调函数，用于将日志输出到GUI"""
    global _log_callback
    _log_callback = callback

def _log(message: str):
    """内部日志函数，优先使用回调，否则不输出（避免打包后弹出终端）"""
    if _log_callback:
        _log_callback(message)
    # 在打包后的exe中，不输出到控制台，避免弹出终端


def extract_sessdata(cookie_or_sessdata: str) -> str:
    """
    从cookie字符串中提取SESSDATA的值
    支持两种格式：
    1. 直接SESSDATA值：abc123%2C...
    2. 完整cookie字符串：CURRENT_QUALITY=120;...;SESSDATA=abc123%2C...;...
    """
    if not cookie_or_sessdata:
        return ''
    
    if 'SESSDATA=' in cookie_or_sessdata:
        match = re.search(r'SESSDATA=([^;]+)', cookie_or_sessdata)
        if match and match.group(1):
            return match.group(1)
    
    return cookie_or_sessdata


def calculate_fnval(qn: int, smart_resolution: bool = False) -> Dict[str, int]:
    """
    根据请求的画质(qn)计算对应的fnval值
    fnval是二进制标志位组合：16(DASH) | 特定功能 | 2048(AV1)
    """
    base_dash = 16
    av1_codec = 2048
    
    fnval = base_dash | av1_codec
    fourk = 0
    
    if smart_resolution:
        fnval = base_dash | av1_codec | 1024 | 128 | 64 | 512
        fourk = 1
        return {'fnval': fnval, 'fourk': fourk}
    
    qn_int = int(qn)
    if qn_int == 127:  # 8K
        fnval |= 1024
        fourk = 1
    elif qn_int == 126:  # 杜比视界
        fnval |= 512
        fourk = 1
    elif qn_int == 125:  # HDR
        fnval |= 64
        fourk = 1
    elif qn_int == 120:  # 4K
        fnval |= 128
        fourk = 1
    
    return {'fnval': fnval, 'fourk': fourk}


def fetch_cid(bvid: str) -> str:
    """
    bvid转换成cid
    """
    url = BILI_BVID_TO_CID.replace("{bvid}", bvid)
    response = requests.get(url, headers=BILI_HEADER)
    json_data = response.json()
    cid = json_data['data'][0]['cid']
    return str(cid)


def get_page_cid(bvid: str, p_number: int) -> Optional[str]:
    """
    获取指定分P的CID
    """
    try:
        url = f"{BILI_VIDEO_INFO}?bvid={bvid}"
        response = requests.get(url, headers=BILI_HEADER)
        json_data = response.json()
        pages = json_data.get('data', {}).get('pages', [])
        
        if pages and len(pages) >= p_number and p_number > 0:
            target_page = pages[p_number - 1]
            return str(target_page['cid'])
        
        if pages:
            return str(pages[0]['cid'])
        return None
    except Exception as e:
        _log(f"获取分P CID失败: {e}")
        return None


def get_video_info(url: str) -> Dict:
    """
    获取视频信息
    """
    video_match = re.search(r'/video/([^\?\/ ]+)', url)
    if not video_match:
        raise ValueError(f"无法识别的URL格式: {url}")
    
    video_id = video_match.group(1)
    final_url = f"{BILI_VIDEO_INFO}?"
    
    if video_id.lower().startswith('av'):
        final_url += f"aid={video_id[2:]}"
    else:
        final_url += f"bvid={video_id}"
    
    response = requests.get(final_url, headers=BILI_HEADER)
    resp_json = response.json()
    resp_data = resp_json['data']
    
    return {
        'title': resp_data.get('title', ''),
        'pic': resp_data.get('pic', ''),
        'desc': resp_data.get('desc', ''),
        'duration': resp_data.get('duration', 0),
        'dynamic': resp_data.get('dynamic', ''),
        'stat': resp_data.get('stat', {}),
        'bvid': resp_data.get('bvid', ''),
        'aid': resp_data.get('aid', ''),
        'cid': resp_data.get('pages', [{}])[0].get('cid', '') if resp_data.get('pages') else '',
        'owner': resp_data.get('owner', {}),
        'pages': resp_data.get('pages', []),
    }


def get_bangumi_video_info(ep_id: str) -> Optional[Dict]:
    """
    获取番剧视频信息（包含标题等详细信息）
    """
    try:
        url = BILI_EP_INFO.replace("{}", ep_id)
        response = requests.get(url, headers=BILI_HEADER)
        json_data = response.json()
        
        if json_data.get('code') != 0:
            _log(f"获取番剧信息失败: {json_data.get('message', '未知错误')}")
            return None
        
        result = json_data.get('result', {})
        target_ep = None
        
        # 从episodes中查找
        for section in [result.get('episodes', []), *[s.get('episodes', []) for s in result.get('section', [])]]:
            if not section:
                continue
            target_ep = next((ep for ep in section if str(ep.get('id', '')) == ep_id or str(ep.get('ep_id', '')) == ep_id), None)
            if target_ep:
                break
        
        if not target_ep and result.get('main_section', {}).get('episodes'):
            target_ep = next((ep for ep in result['main_section']['episodes'] if str(ep.get('id', '')) == ep_id or str(ep.get('ep_id', '')) == ep_id), None)
        
        if not target_ep:
            target_ep = result.get('episodes', [{}])[0] if result.get('episodes') else None
        
        if not target_ep:
            return None
        
        # 获取番剧标题和集标题
        season_title = result.get('title', '')  # 番剧总标题
        ep_title = target_ep.get('title', '')  # 集标题
        long_title = target_ep.get('long_title', '')  # 长标题
        
        # 组合标题：番剧名 - 集标题
        if season_title and ep_title:
            title = f"{season_title} - {ep_title}"
        elif season_title:
            title = f"{season_title} - EP{ep_id}"
        elif ep_title:
            title = ep_title
        elif long_title:
            title = long_title
        else:
            title = f"EP{ep_id}"
        
        return {
            'bvid': target_ep.get('bvid', ''),
            'cid': str(target_ep.get('cid', '')),
            'title': title,
            'season_title': season_title,
            'ep_title': ep_title,
            'long_title': long_title,
            'duration': target_ep.get('duration', 0)  # 时长（秒）
        }
    except Exception as e:
        _log(f"获取番剧信息异常: {e}")
        return None


def get_bili_video_with_session(bvid: str, cid: str, sessdata: str, qn: int, smart_resolution: bool = False) -> Dict:
    """
    获取B站视频流（带session）
    """
    if not cid:
        cid = fetch_cid(bvid)
    
    fnval_data = calculate_fnval(qn, smart_resolution)
    fnval = fnval_data['fnval']
    fourk = fnval_data['fourk']
    
    api_url = BILI_PLAY_STREAM.replace("{bvid}", bvid).replace("{cid}", cid).replace("{qn}", str(qn)).replace("{fnval}", str(fnval)).replace("{fourk}", str(fourk))
    
    sessdata_value = extract_sessdata(sessdata)
    cookie_header = sessdata if 'SESSDATA=' in sessdata else f"SESSDATA={sessdata_value}"
    
    headers = {**BILI_HEADER, 'Cookie': cookie_header}
    response = requests.get(api_url, headers=headers)
    json_data = response.json()
    
    if json_data.get('code') != 0:
        raise Exception(f"请求失败: {json_data.get('message', '未知错误')}")
    
    return json_data.get('data', {}).get('dash', {})


def get_bangumi_bili_video_with_session(ep_id: str, cid: str, sessdata: str, qn: int, smart_resolution: bool = False) -> Dict:
    """
    获取番剧视频流（使用PGC专用API）
    """
    fnval_data = calculate_fnval(qn, smart_resolution)
    fnval = fnval_data['fnval']
    fourk = fnval_data['fourk']
    
    api_url = BILI_BANGUMI_STREAM.replace("{ep_id}", ep_id).replace("{cid}", cid).replace("{qn}", str(qn)).replace("{fnval}", str(fnval)).replace("{fourk}", str(fourk))
    
    sessdata_value = extract_sessdata(sessdata)
    cookie_header = sessdata if 'SESSDATA=' in sessdata else f"SESSDATA={sessdata_value}"
    
    headers = {**BILI_HEADER, 'Cookie': cookie_header}
    response = requests.get(api_url, headers=headers)
    json_data = response.json()
    
    if json_data.get('code') != 0:
        raise Exception(f"番剧API错误: {json_data.get('message', '未知错误')} (code: {json_data.get('code')})")
    
    result = json_data.get('result', {})
    if not result:
        raise Exception("番剧API返回数据为空")
    
    if result.get('dash'):
        return {'type': 'dash', 'data': result['dash'], 'result': result}
    elif result.get('durl') or result.get('durls'):
        return {'type': 'durl', 'data': result}
    else:
        raise Exception("番剧API返回未知格式")


def select_and_avoid_mcdn_url(base_url: str, backup_urls: List[str] = None) -> str:
    """
    动态规避哔哩哔哩cdn中的mcdn
    """
    if backup_urls is None:
        backup_urls = []
    
    slow_cdn_patterns = ['.mcdn.bilivideo.cn', 'mountaintoys.cn', '.szbdyd.com']
    
    def is_slow_cdn(url: str) -> bool:
        try:
            from urllib.parse import urlparse
            hostname = urlparse(url).hostname
            return any(pattern in hostname for pattern in slow_cdn_patterns)
        except:
            return False
    
    if not is_slow_cdn(base_url):
        return base_url
    
    for url in backup_urls:
        if not is_slow_cdn(url):
            return url
    
    return base_url


def get_download_url(url: str, sessdata: str, qn: int, duration: int = 0, smart_resolution: bool = False, file_size_limit: int = 100, preferred_codec: str = 'auto') -> Dict[str, Optional[str]]:
    """
    获取下载链接
    """
    video_id = ""
    cid = ""
    is_bangumi = False
    ep_id = ""
    
    # 检查是否是番剧URL
    ep_match = re.search(r'bangumi/play/ep(\d+)', url)
    if ep_match:
        is_bangumi = True
        ep_id = ep_match.group(1)
        _log(f"[BILI下载] 检测到番剧链接，EP ID: {ep_id}")
        ep_info = get_bangumi_video_info(ep_id)
        if not ep_info:
            raise Exception(f"无法获取番剧信息，EP ID: {ep_id}")
        video_id = ep_info['bvid']
        cid = ep_info['cid']
    else:
        # 普通视频URL
        video_match = re.search(r'/video/([^\?\/ ]+)', url)
        if not video_match:
            raise ValueError(f"无法识别的URL格式: {url}")
        video_id = video_match.group(1)
        
        # 提取URL中的p参数（分P号）
        p_param = None
        try:
            from urllib.parse import urlparse, parse_qs
            if not url.startswith('http'):
                url = 'https://' + url
            url_obj = urlparse(url)
            params = parse_qs(url_obj.query)
            if 'p' in params:
                p_param = int(params['p'][0])
                _log(f"[BILI下载] 检测到分P参数: P{p_param}")
        except Exception as e:
            _log(f"[BILI下载] URL解析P参数失败: {e}")
        
        # AV号特殊处理
        if video_id.lower().startswith('av'):
            # 将 AV 转换为 BV
            video_info = get_video_info(url)
            video_id = video_info['bvid']
            # 如果有P参数且页数足够，获取对应分P的CID
            if p_param and video_info.get('pages') and len(video_info['pages']) >= p_param and p_param > 0:
                cid = str(video_info['pages'][p_param - 1]['cid'])
                _log(f"[BILI下载] AV号分P {p_param}，使用CID: {cid}")
            else:
                cid = str(video_info['cid'])
        elif p_param and p_param > 0:
            # BV号且有分P参数，获取对应分P的CID
            cid = get_page_cid(video_id, p_param)
    
    # 转换画质数字为分辨率
    quality_map = {
        127: "8K超高清",
        126: "杜比视界",
        125: "HDR真彩",
        120: "4K超清",
        116: "1080P60高帧率",
        112: "1080P+高码率",
        80: "1080P高清",
        74: "720P60高帧率",
        64: "720P高清",
        32: "480P清晰",
        16: "360P流畅",
    }
    quality_text = quality_map.get(int(qn), f"未知画质(QN:{qn})")
    _log(f"[BILI下载] 开始获取视频下载链接，视频ID: {video_id}, 请求画质: {quality_text}, QN: {qn}, 编码选择: {preferred_codec}")
    
    stream_data = None
    stream_type = 'dash'
    
    if is_bangumi:
        # 番剧使用专门的API
        bangumi_result = get_bangumi_bili_video_with_session(ep_id, cid, sessdata, qn, smart_resolution)
        stream_type = bangumi_result['type']
        stream_data = bangumi_result
        
        # 如果是DURL格式，直接返回视频URL（不需要音频）
        if stream_type == 'durl':
            durl_data = stream_data.get('data', {}).get('durl')
            if not durl_data or len(durl_data) == 0:
                _log(f"[BILI下载] 番剧DURL数据为空")
                return {'videoUrl': None, 'audioUrl': None}
            first_durl = durl_data[0]
            backup_urls = first_durl.get('backup_url', [])
            _log(f"[BILI下载] 可用URL数量: 1个主URL + {len(backup_urls)}个备用URL")
            video_url = select_and_avoid_mcdn_url(first_durl['url'], backup_urls)
            _log(f"[BILI下载] 番剧DURL格式，视频大小: {round(first_durl.get('size', 0) / 1024 / 1024)}MB, 时长: {round(first_durl.get('length', 0) / 1000)}秒")
            from urllib.parse import urlparse
            _log(f"[BILI下载] 选中的下载URL: {urlparse(video_url).hostname}")
            return {'videoUrl': video_url, 'audioUrl': None}
    else:
        # 普通视频
        stream_data = get_bili_video_with_session(video_id, cid, sessdata, qn, smart_resolution)
    
    # 以下是DASH格式处理逻辑
    dash_data = stream_data.get('data', stream_data) if is_bangumi else stream_data
    video = dash_data.get('video', [])
    audio = dash_data.get('audio', [])
    
    # 根据请求的画质选择对应的视频流
    height_map = {
        127: 4320,  # 8K
        126: 2160,  # 杜比视界
        125: 2160,  # HDR
        120: 2160,  # 4K
        116: 1080,  # 1080P60高帧率
        112: 1080,  # 1080P+高码率
        80: 1080,   # 1080P
        74: 720,    # 720P60高帧率
        64: 720,    # 720P
        32: 480,    # 480P
        16: 360,    # 360P
    }
    target_height = height_map.get(int(qn))
    if target_height is None:
        # 未知QN，使用最高画质
        target_height = max([v.get('height', 0) for v in video]) if video else 1080
        _log(f"[BILI下载] 未知的QN值: {qn}，使用最高可用分辨率: {target_height}p")
    
    # 获取目标分辨率的所有视频流
    if smart_resolution:
        matching_videos = video
        available_heights = sorted(set([v.get('height', 0) for v in video]), reverse=True)
        _log(f"[BILI下载] 智能分辨率模式：使用所有可用画质 {', '.join([str(h) + 'p' for h in available_heights])}")
    else:
        matching_videos = [v for v in video if v.get('height') == target_height]
        
        if not matching_videos:
            available_heights = sorted(set([v.get('height', 0) for v in video]), reverse=True)
            _log(f"[BILI下载] ⚠️ 请求的{target_height}p画质不可用，API返回的最高画质: {available_heights[0]}p")
            _log(f"[BILI下载] API可用分辨率列表: {', '.join([str(h) + 'p' for h in available_heights])}")
            
            matching_videos = sorted([v for v in video if v.get('height', 0) <= target_height], 
                                    key=lambda x: x.get('height', 0), reverse=True)
            
            if matching_videos:
                max_height = matching_videos[0].get('height', 0)
                matching_videos = [v for v in matching_videos if v.get('height') == max_height]
                _log(f"[BILI下载] 降级使用: {max_height}p")
        else:
            _log(f"[BILI下载] ✅ 找到匹配的{target_height}p画质")
        
        if not matching_videos:
            min_height = min([v.get('height', 0) for v in video]) if video else 0
            matching_videos = [v for v in video if v.get('height') == min_height]
            _log(f"[BILI下载] 所有视频流都高于请求画质，使用最低可用: {min_height}p")
    
    # 智能选择最佳视频流
    video_data = None
    if matching_videos:
        # 获取编码类型
        def get_codec_type(codecs: str) -> str:
            codec_lower = codecs.lower()
            if 'av01' in codec_lower or 'av1' in codec_lower:
                return 'av1'
            if 'hev1' in codec_lower or 'hevc' in codec_lower:
                return 'hevc'
            if 'avc1' in codec_lower or 'avc' in codec_lower:
                return 'avc'
            return 'unknown'
        
        # 根据用户选择的编码设置优先级
        if preferred_codec == 'av1':
            codec_priority = {'av1': 1, 'hevc': 2, 'avc': 3, 'unknown': 999}
        elif preferred_codec == 'hevc':
            codec_priority = {'av1': 2, 'hevc': 1, 'avc': 3, 'unknown': 999}
        elif preferred_codec == 'avc':
            codec_priority = {'av1': 2, 'hevc': 3, 'avc': 1, 'unknown': 999}
        else:
            codec_priority = {'av1': 1, 'hevc': 2, 'avc': 3, 'unknown': 999}
        
        # 估算文件大小
        def estimate_size(stream: Dict, audio_stream: Optional[Dict], timelength: int) -> float:
            video_bandwidth = stream.get('bandwidth', 0)
            audio_bandwidth = audio_stream.get('bandwidth', 0) if audio_stream else 0
            total_bandwidth = video_bandwidth + audio_bandwidth
            bytes_per_second = total_bandwidth / 8
            duration_seconds = timelength / 1000 if timelength > 0 else (stream.get('duration', 0) or (audio_stream.get('duration', 0) if audio_stream else 0))
            if duration_seconds == 0:
                _log(f"[BILI下载] 无法获取视频时长，文件大小估算可能不准确")
            return (bytes_per_second * duration_seconds) / (1024 * 1024)  # MB
        
        # 排序视频流
        sorted_videos = sorted(matching_videos, key=lambda v: (
            codec_priority.get(get_codec_type(v.get('codecs', '')), 999),
            v.get('bandwidth', 0)
        ))
        
        audio_data = audio[0] if audio else None
        
        # 获取时长
        timelength = duration * 1000 if duration > 0 else 0
        if timelength == 0:
            if is_bangumi and stream_data.get('result', {}).get('timelength'):
                timelength = stream_data['result']['timelength']
            elif not is_bangumi and stream_data.get('data', {}).get('timelength'):
                timelength = stream_data['data']['timelength']
            elif video and video[0].get('duration'):
                timelength = video[0]['duration'] * 1000
            elif audio_data and audio_data.get('duration'):
                timelength = audio_data['duration'] * 1000
        
        # 番剧不使用文件大小限制
        if is_bangumi:
            smart_resolution = False
        
        # 选择视频流
        if timelength == 0 and not is_bangumi:
            # 使用码率限制策略
            assumed_duration = 300  # 秒
            max_total_bandwidth = (file_size_limit * 1024 * 1024 * 8) / assumed_duration
            _log(f"[BILI下载] 假设视频时长{assumed_duration}秒，计算最大总码率: {round(max_total_bandwidth / 1024)}kbps")
            
            for candidate in sorted_videos:
                video_bandwidth = candidate.get('bandwidth', 0)
                audio_bandwidth = audio_data.get('bandwidth', 0) if audio_data else 0
                total_bandwidth = video_bandwidth + audio_bandwidth
                
                if total_bandwidth <= max_total_bandwidth:
                    video_data = candidate
                    codec_type = get_codec_type(candidate.get('codecs', ''))
                    _log(f"[BILI下载] 选择视频流: {candidate.get('height')}p, 编码: {codec_type.upper()}, 总码率: {round(total_bandwidth / 1024)}kbps")
                    break
            
            if not video_data:
                video_data = sorted_videos[-1]
        else:
            # 使用精确的文件大小估算
            if smart_resolution:
                available_heights = sorted(set([v.get('height', 0) for v in video]), reverse=True)
                _log(f"[BILI下载] 智能分辨率：从最高{available_heights[0]}p开始，符合{file_size_limit}MB限制")
                
                for height in available_heights:
                    height_videos = [v for v in video if v.get('height') == height]
                    sorted_height_videos = sorted(height_videos, key=lambda v: (
                        codec_priority.get(get_codec_type(v.get('codecs', '')), 999),
                        -v.get('bandwidth', 0)  # 智能分辨率优先高码率
                    ))
                    
                    for candidate in sorted_height_videos:
                        estimated_size = estimate_size(candidate, audio_data, timelength)
                        if estimated_size <= file_size_limit:
                            video_data = candidate
                            codec_type = get_codec_type(candidate.get('codecs', ''))
                            _log(f"[BILI下载] ✅ 智能分辨率选择: {candidate.get('height')}p, 编码: {codec_type.upper()}, 预估大小: {round(estimated_size)}MB")
                            break
                    
                    if video_data:
                        break
                
                if not video_data:
                    lowest_height = available_heights[-1]
                    lowest_videos = [v for v in video if v.get('height') == lowest_height]
                    video_data = sorted(lowest_videos, key=lambda x: x.get('bandwidth', 0))[0]
            else:
                # 非智能分辨率
                if is_bangumi:
                    # 番剧特殊处理
                    bangumi_videos = [v for v in video if v.get('height') == target_height]
                    if not bangumi_videos:
                        max_height = max([v.get('height', 0) for v in video])
                        bangumi_videos = [v for v in video if v.get('height') == max_height]
                    
                    bangumi_videos = sorted(bangumi_videos, key=lambda v: (
                        codec_priority.get(get_codec_type(v.get('codecs', '')), 999),
                        v.get('bandwidth', 0)
                    ))
                    video_data = bangumi_videos[0] if bangumi_videos else None
                else:
                    # 普通视频
                    for candidate in sorted_videos:
                        estimated_size = estimate_size(candidate, audio_data, timelength)
                        if estimated_size <= file_size_limit:
                            video_data = candidate
                            codec_type = get_codec_type(candidate.get('codecs', ''))
                            _log(f"[BILI下载] 选择视频流: {candidate.get('height')}p, 编码: {codec_type.upper()}, 预估大小: {round(estimated_size)}MB")
                            break
                    
                    if not video_data:
                        video_data = sorted_videos[-1]
    
    if not video_data:
        _log(f"[BILI下载] 获取视频数据失败，请检查画质参数是否正确")
        return {'videoUrl': None, 'audioUrl': None}
    
    # 提取视频URL
    video_base_url = video_data.get('baseUrl', '')
    video_backup_urls = video_data.get('backupUrl', [])
    video_url = select_and_avoid_mcdn_url(video_base_url, video_backup_urls)
    
    # 提取音频URL
    audio_url = None
    if audio:
        audio_data = audio[0]
        audio_base_url = audio_data.get('baseUrl', '')
        audio_backup_urls = audio_data.get('backupUrl', [])
        audio_url = select_and_avoid_mcdn_url(audio_base_url, audio_backup_urls)
    
    return {'videoUrl': video_url, 'audioUrl': audio_url}


def download_b_file(url: str, full_file_name: str, progress_callback=None, bili_download_method: int = 0, video_download_concurrency: int = 1) -> Dict:
    """
    下载单个bili文件
    """
    if bili_download_method == 0:
        # 原生下载
        return normal_download_b_file(url, full_file_name, progress_callback)
    elif bili_download_method == 1:
        # Aria2下载（暂未实现，使用原生方式）
        _log("[BILI下载] Aria2下载方式暂未实现，使用原生下载")
        return normal_download_b_file(url, full_file_name, progress_callback)
    else:
        # axel/wget下载（暂未实现，使用原生方式）
        _log("[BILI下载] axel/wget下载方式暂未实现，使用原生下载")
        return normal_download_b_file(url, full_file_name, progress_callback)


def normal_download_b_file(url: str, full_file_name: str, progress_callback=None) -> Dict:
    """
    正常下载（原生方式）
    """
    import time
    
    # 确保目录存在
    file_path = Path(full_file_name)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    response = requests.get(url, headers=BILI_HEADER, stream=True)
    response.raise_for_status()
    
    total_len = int(response.headers.get('content-length', 0))
    current_len = 0
    
    # 用于计算速度的时间戳和下载量
    start_time = time.time()
    last_time = start_time
    last_len = 0
    chunk_size = 8192
    
    with open(full_file_name, 'wb') as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                current_len += len(chunk)
                
                if progress_callback and total_len > 0:
                    current_time = time.time()
                    elapsed_time = current_time - last_time
                    
                    # 每0.1秒更新一次进度（避免过于频繁）
                    if elapsed_time >= 0.1 or current_len >= total_len:
                        # 计算速度（字节/秒）
                        speed = (current_len - last_len) / elapsed_time if elapsed_time > 0 else 0
                        
                        # 计算剩余时间
                        remaining_bytes = total_len - current_len
                        eta_seconds = remaining_bytes / speed if speed > 0 else 0
                        
                        # 调用回调，传递详细信息
                        progress_callback(
                            progress=current_len / total_len,
                            current=current_len,
                            total=total_len,
                            speed=speed,
                            eta=eta_seconds
                        )
                        
                        last_time = current_time
                        last_len = current_len
    
    return {
        'fullFileName': full_file_name,
        'totalLen': total_len
    }


def merge_file_to_mp4(v_full_file_name: str, a_full_file_name: str, output_file_name: str, should_delete: bool = True) -> Dict:
    """
    合并视频和音频（使用ffmpeg-python库）
    """
    import ffmpeg
    
    # 确保输出目录存在
    output_path = Path(output_file_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # 使用ffmpeg-python合并视频和音频
        video_input = ffmpeg.input(str(v_full_file_name))
        audio_input = ffmpeg.input(str(a_full_file_name))
        
        # 使用copy编码器进行快速合并（不重新编码）
        output = ffmpeg.output(
            video_input,
            audio_input,
            str(output_file_name),
            vcodec='copy',
            acodec='copy'
        )
        
        # 覆盖输出文件（-y参数）
        output = ffmpeg.overwrite_output(output)
        
        # 执行合并，隐藏输出
        ffmpeg.run(output, quiet=True, overwrite_output=True)
        
        # 删除临时文件
        if should_delete:
            try:
                Path(v_full_file_name).unlink(missing_ok=True)
                Path(a_full_file_name).unlink(missing_ok=True)
            except Exception as e:
                _log(f"[BILI下载] 删除临时文件失败: {e}")
        
        return {'outputFileName': output_file_name}
    except ffmpeg.Error as e:
        error_msg = f"ffmpeg执行失败: {e.stderr.decode() if e.stderr else str(e)}"
        _log(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"合并视频失败: {str(e)}"
        _log(error_msg)
        raise Exception(error_msg)


def get_scan_code_data(qrcode_save_path: str = 'qrcode.png', detect_time: int = 10, hook=None) -> Dict[str, str]:
    """
    扫码登录获取SESSDATA
    """
    try:
        response = requests.get(BILI_SCAN_CODE_GENERATE, headers=BILI_HEADER)
        data = response.json()
        scan_url = data['data']['url']
        qrcode_key = data['data']['qrcode_key']
        
        # 生成二维码图片
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(scan_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(qrcode_save_path)
        
        if hook:
            hook(qrcode_save_path, scan_url)
        
        code = 1
        attempt_count = 0
        max_attempts = 3
        login_resp = None
        
        while code != 0 and attempt_count < max_attempts:
            detect_url = BILI_SCAN_CODE_DETECT.replace("{}", qrcode_key)
            login_resp = requests.get(detect_url, headers=BILI_HEADER)
            login_data = login_resp.json()
            code = login_data['data']['code']
            
            if code == 0:
                break
            
            time.sleep(detect_time)
            attempt_count += 1
        
        if code != 0:
            return {'SESSDATA': '', 'refresh_token': ''}
        
        refresh_token = login_resp.json()['data'].get('refresh_token', '')
        cookies = login_resp.headers.get('Set-Cookie', '')
        
        sessdata = ''
        for cookie in cookies.split(','):
            if 'SESSDATA=' in cookie:
                sessdata = cookie.split('SESSDATA=')[1].split(';')[0]
                break
        
        return {
            'SESSDATA': sessdata,
            'refresh_token': refresh_token
        }
    except Exception as e:
        _log(f"扫码登录失败: {e}")
        return {'SESSDATA': '', 'refresh_token': ''}


def get_resolution_labels(selected_value: int) -> str:
    """
    拼接分辨率标签
    """
    filtered_resolutions = [r for r in BILI_RESOLUTION_LIST if r['value'] >= selected_value]
    return ', '.join([r['label'] for r in filtered_resolutions])

