import sys
import os
import json
import ctypes
import traceback
import resources  # 图标文件资源
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QGroupBox, QFileDialog, QMessageBox, QTextEdit,
    QComboBox, QDialog
)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from m4s import *
import download

# 获取Windows特殊文件夹路径
def get_special_folder_path(folder_id):
    """获取 Windows Videos路径"""
    SHGFP_TYPE_CURRENT = 0
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, folder_id, None, SHGFP_TYPE_CURRENT, buf)
    return Path(buf.value)

def get_directory():
    """获取脚本文件所在目录"""
    if getattr(sys,'frozen',False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent

# 配置管理器类
class ConfigManager:
    def __init__(self, config_file="config.json", parent=None):
        script_dir = get_directory()
        self.config_file = script_dir / config_file
        self.parent = parent  # 用于显示消息框
        self.config = self.load_config()
    
    def log_message(self, message):
        """输出日志信息"""
        if self.parent and hasattr(self.parent, 'log_message'):
            self.parent.log_message(message)
        # 在打包后的exe中，不输出到控制台，避免弹出终端
    
    def load_config(self):
        """加载配置文件，处理各种异常情况"""
        # 定义默认配置
        try:
            videos_folder = get_special_folder_path(14)  # 14 = CSIDL_MYVIDEO
            default_input_path = videos_folder / "bilibili"
            default_output_path = videos_folder / "bili_output"
        except:
            videos_folder = Path.home() / "Videos"
            default_input_path = videos_folder / "bilibili"
            default_output_path = videos_folder / "bili_output"
        
        default_config = {
            "input_path": str(default_input_path),
            "output_path": str(default_output_path),
            "sessdata": "",
            "refresh_token": "",
            "quality_index": 6  # 默认选择1080P高清
        }
        
        # 如果配置文件不存在，创建默认配置文件
        if not self.config_file.exists():
            self.log_message("配置文件不存在，将创建默认配置")
            self.save_default_config(default_config)
            return default_config
        
        # 配置文件存在，尝试加载
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            # 验证配置文件格式
            if not isinstance(loaded_config, dict):
                raise ValueError("配置文件格式错误")
            
            # 检查必要字段，使用默认值补全缺失字段
            for key in ["input_path", "output_path", "sessdata", "refresh_token", "quality_index"]:
                if key not in loaded_config:
                    loaded_config[key] = default_config[key]
                    self.log_message(f"配置文件中缺少 {key}，使用默认值")
            
            # 验证路径是否存在（只检查输入路径，输出路径不存在会自动创建）
            if "input_path" in loaded_config:
                input_path = Path(loaded_config["input_path"])
                if not input_path.exists():
                    self.log_message(f"警告: 保存的输入路径不存在: {input_path}")
            
            return loaded_config
            
        except json.JSONDecodeError as e:
            error_msg = f"配置文件JSON格式错误: {e}"
            self.log_message(error_msg)
            if self.parent:
                # 这里不能直接显示消息框，因为界面可能还没初始化
                # 我们将在稍后显示消息
                pass
            
            # 备份损坏的配置文件
            self.backup_corrupted_config()
            
            # 创建默认配置文件
            self.save_default_config(default_config)
            return default_config
            
        except (IOError, ValueError, PermissionError) as e:
            error_msg = f"读取配置文件失败: {e}"
            self.log_message(error_msg)
            # 使用默认配置
            return default_config
    
    def save_default_config(self, default_config):
        """保存默认配置到文件"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            self.log_message(f"已创建默认配置文件: {self.config_file.absolute()}")
            return True
        except Exception as e:
            self.log_message(f"创建默认配置文件失败: {e}")
            return False
    
    def backup_corrupted_config(self):
        """备份损坏的配置文件"""
        if self.config_file.exists():
            try:
                backup_file = self.config_file.with_suffix('.json.bak')
                counter = 1
                while backup_file.exists():
                    backup_file = self.config_file.with_suffix(f'.json.bak{counter}')
                    counter += 1
                
                import shutil
                shutil.copy2(self.config_file, backup_file)
                self.log_message(f"已备份损坏的配置文件到: {backup_file.name}")
            except Exception as e:
                self.log_message(f"备份配置文件失败: {e}")
    
    def save_config(self, input_path=None, output_path=None, quality_index=None):
        """保存配置到文件"""
        if input_path:
            self.config["input_path"] = str(input_path)
        if output_path:
            self.config["output_path"] = str(output_path)
        if quality_index is not None:
            self.config["quality_index"] = quality_index
        
        try:
            # 确保目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入配置文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            return True
            
        except PermissionError:
            error_msg = f"无权限写入配置文件: {self.config_file}"
            if self.parent:
                QMessageBox.warning(self.parent, "保存失败", 
                                  f"无权限写入配置文件，请检查文件权限")
            return False
            
        except IOError as e:
            error_msg = f"保存配置文件失败: {e}"
            if self.parent:
                QMessageBox.warning(self.parent, "保存失败", 
                                  f"保存配置文件时出错: {str(e)}")
            return False
    
    def get_input_path(self):
        """获取保存的输入路径"""
        return self.config.get("input_path", "")
    
    def get_output_path(self):
        """获取保存的输出路径"""
        return self.config.get("output_path", "")
    
    def get_sessdata(self):
        """获取保存的SESSDATA"""
        return self.config.get("sessdata", "")
    
    def get_refresh_token(self):
        """获取保存的refresh_token"""
        return self.config.get("refresh_token", "")
    
    def save_session(self, sessdata=None, refresh_token=None):
        """保存session信息"""
        if sessdata is not None:
            self.config["sessdata"] = sessdata
        if refresh_token is not None:
            self.config["refresh_token"] = refresh_token
        return self.save_config()
    
    def get_quality_index(self):
        """获取保存的画质索引"""
        return self.config.get("quality_index", 6)  # 默认1080P高清
    
    def save_quality_index(self, quality_index):
        """保存画质索引"""
        return self.save_config(quality_index=quality_index)

# 主界面类
class M4SProcessorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        # 先设置窗口基础属性
        self.setWindowTitle('A+1 Tool')
        self.setGeometry(300, 300, 800, 600)
        self.setWindowIcon(QIcon(":/icon.ico"))
        
        # 先初始化UI，再初始化配置管理器
        self.initUI()
        
        # 初始化配置管理器
        self.config_manager = ConfigManager(parent=self)
        
        # 设置download模块的日志回调
        download.set_log_callback(self.log_message)
        
        # 更新界面显示
        self.update_paths_from_config()
        
        # 显示配置文件信息
        self.show_config_info()
    
    def initUI(self):
        """初始化UI组件"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        
        # ========== 1. 输入文件夹设置 ==========
        input_group = QGroupBox("输入设置")
        input_layout = QVBoxLayout()
        
        # 输入文件夹选择
        input_folder_layout = QHBoxLayout()
        input_label = QLabel("输入文件夹:")
        
        # 创建输入路径编辑框，稍后更新值
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setPlaceholderText("请选择或输入输入文件夹路径")
        
        input_browse_btn = QPushButton("浏览...")
        input_browse_btn.clicked.connect(self.browse_input_folder)

        self.input_open_btn = QPushButton("打开...")
        self.input_open_btn.clicked.connect(self.open_input_folder)
        
        input_folder_layout.addWidget(input_label)
        input_folder_layout.addWidget(self.input_path_edit)
        input_folder_layout.addWidget(input_browse_btn)
        input_folder_layout.addWidget(self.input_open_btn)
        
        input_layout.addLayout(input_folder_layout)
        input_group.setLayout(input_layout)
        
        # ========== 2. 输出文件夹设置 ==========
        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout()
        
        # 输出文件夹选择
        output_folder_layout = QHBoxLayout()
        output_label = QLabel("输出文件夹:")
        
        # 创建输出路径编辑框，稍后更新值
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("请选择或输入输出文件夹路径")
        
        output_browse_btn = QPushButton("浏览...")
        output_browse_btn.clicked.connect(self.browse_output_folder)

        self.output_open_btn = QPushButton("打开...")
        self.output_open_btn.clicked.connect(self.open_output_folder)
        
        output_folder_layout.addWidget(output_label)
        output_folder_layout.addWidget(self.output_path_edit)
        output_folder_layout.addWidget(output_browse_btn)
        output_folder_layout.addWidget(self.output_open_btn)
        
        output_layout.addLayout(output_folder_layout)
        output_group.setLayout(output_layout)
        
        # ========== 3. 控制按钮区域 ==========
        control_layout = QHBoxLayout()
        
        # 处理按钮
        self.process_btn = QPushButton("开始处理")
        self.process_btn.clicked.connect(self.start_processing)
        
        # 清空按钮
        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.clicked.connect(self.clear_log)
        
        # 重置配置按钮
        self.reset_config_btn = QPushButton("重置配置")
        self.reset_config_btn.clicked.connect(self.reset_config)
        self.reset_config_btn.setToolTip("恢复默认配置并删除配置文件")
        
        control_layout.addStretch()
        control_layout.addWidget(self.process_btn)
        control_layout.addWidget(self.clear_btn)
        control_layout.addWidget(self.reset_config_btn)
        control_layout.addStretch()
        
        # ========== 4. B站下载设置 ==========
        download_group = QGroupBox("B站视频下载")
        download_layout = QVBoxLayout()
        
        # 链接输入
        url_layout = QHBoxLayout()
        url_label = QLabel("视频链接/BV号/番剧EP:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("支持: BV号、AV号、视频链接、番剧EP号(ep123456)、番剧链接")
        self.url_clear_btn = QPushButton("清空")
        self.url_clear_btn.clicked.connect(self.clear_url_input)
        self.url_clear_btn.setMaximumWidth(60)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.url_clear_btn)
        download_layout.addLayout(url_layout)
        
        # 画质选择和下载按钮（同一行）
        quality_layout = QHBoxLayout()
        quality_label = QLabel("画质选择:")
        self.quality_combo = QComboBox()
        for resolution in download.BILI_RESOLUTION_LIST:
            self.quality_combo.addItem(resolution['label'], resolution['qn'])
        # 画质索引将在update_paths_from_config中从配置加载
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.quality_combo)
        # 连接画质选择变化信号，自动保存
        self.quality_combo.currentIndexChanged.connect(self.on_quality_changed)
        quality_layout.addStretch()
        
        # 下载和登录按钮
        self.download_btn = QPushButton("开始下载")
        self.download_btn.clicked.connect(self.start_download)
        self.login_btn = QPushButton("扫码登录")
        self.login_btn.clicked.connect(self.show_qr_login)
        self.open_output_btn = QPushButton("打开...")
        self.open_output_btn.clicked.connect(self.open_output_folder)
        quality_layout.addWidget(self.download_btn)
        quality_layout.addWidget(self.login_btn)
        quality_layout.addWidget(self.open_output_btn)
        
        download_layout.addLayout(quality_layout)
        download_group.setLayout(download_layout)
        
        # ========== 5. 日志输出区域 ==========
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        # ========== 添加到主布局 ==========
        main_layout.addWidget(input_group)
        main_layout.addWidget(output_group)
        main_layout.addLayout(control_layout)
        main_layout.addWidget(download_group)
        main_layout.addWidget(log_group, 1)
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
        # 设置手动编辑后的自动保存
        self.setup_connections()

    def update_paths_from_config(self):
        """从配置文件更新路径显示"""
        # 这里只是初始化控件，配置管理器会在之后初始化
        pass
    
    def on_quality_changed(self, index):
        """画质选择变化时的回调"""
        if hasattr(self, 'config_manager'):
            self.config_manager.save_quality_index(index)
    
    def setup_connections(self):
        """设置信号连接"""
        # 当输入路径被手动编辑后，失去焦点时保存
        self.input_path_edit.editingFinished.connect(self.save_input_path_on_edit)
        self.output_path_edit.editingFinished.connect(self.save_output_path_on_edit)
    
    def show_config_info(self):
        """显示配置文件信息"""
        config_path = self.config_manager.config_file.absolute()
        self.log_message(f"配置文件位置: {config_path}")
        self.log_message(f"当前配置:")
        self.log_message(f"输入路径: {self.config_manager.config.get('input_path', '未设置')}")
        self.log_message(f"输出路径: {self.config_manager.config.get('output_path', '未设置')}")
        
        # 更新界面显示
        self.input_path_edit.setText(self.config_manager.config.get("input_path", ""))
        self.output_path_edit.setText(self.config_manager.config.get("output_path", ""))
        # 恢复画质选择
        quality_index = self.config_manager.get_quality_index()
        if 0 <= quality_index < self.quality_combo.count():
            # 临时阻止信号，避免触发保存
            self.quality_combo.blockSignals(True)
            self.quality_combo.setCurrentIndex(quality_index)
            self.quality_combo.blockSignals(False)
    
    def save_input_path_on_edit(self):
        """手动编辑输入路径后保存"""
        path = self.input_path_edit.text().strip()
        if path:
            success = self.config_manager.save_config(input_path=path)
            if success:
                self.log_message(f"输入路径已保存: {path}")
    
    def save_output_path_on_edit(self):
        """手动编辑输出路径后保存"""
        path = self.output_path_edit.text().strip()
        if path:
            success = self.config_manager.save_config(output_path=path)
            if success:
                self.log_message(f"输出路径已保存: {path}")
    
    def browse_input_folder(self):
        """选择输入文件夹"""
        current_path = self.input_path_edit.text()
        folder = QFileDialog.getExistingDirectory(
            self, 
            "选择输入文件夹",
            current_path,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder:
            self.input_path_edit.setText(folder)
            # 保存到配置文件
            success = self.config_manager.save_config(input_path=folder)
            if success:
                self.log_message(f"输入文件夹已选择并保存: {folder}")
    
    def browse_output_folder(self):
        """选择输出文件夹"""
        current_path = self.output_path_edit.text()
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择输出文件夹",
            current_path,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder:
            self.output_path_edit.setText(folder)
            # 保存到配置文件
            success = self.config_manager.save_config(output_path=folder)
            if success:
                self.log_message(f"输出文件夹已选择并保存: {folder}")
    
    def open_input_folder(self):
        path = self.input_path_edit.text().strip()
        if not path:
            return
        folder_path = Path(path)
        if not folder_path.exists():
            try:
                folder_path.mkdir(parents=True,exist_ok=True)
            except Exception as e:
                self.log_message(f"错误: 无法创建文件夹: {str(e)}")
                return
        try:
            if sys.platform.startswith('win'):
                os.startfile(folder_path)
        except Exception as e:
            error_msg = f"打开文件夹失败: {e}"
            self.log_message(error_msg)

    def open_output_folder(self):
        path = self.output_path_edit.text().strip()
        if not path:
            return
        folder_path = Path(path)
        if not folder_path.exists():
            return
        try:
            if sys.platform.startswith('win'):
                os.startfile(folder_path)
        except Exception as e:
            error_msg = f"打开文件夹失败: {e}"
            self.log_message(error_msg)

    def start_processing(self):
        """开始处理M4S文件"""
        input_path = Path(self.input_path_edit.text())
        output_path = Path(self.output_path_edit.text())
        
        # 验证路径
        if not input_path.exists():
            QMessageBox.warning(self, "错误", f"输入文件夹不存在: {input_path}")
            return
        
        # 创建输出文件夹（如果不存在）
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建输出文件夹: {str(e)}")
            return
        
        # 创建临时文件夹（在当前目录或系统临时目录）
        try:
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "m4s_processor_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建临时文件夹: {str(e)}")
            return
        
        # 更新状态
        self.process_btn.setEnabled(False)
        self.process_btn.setText("处理中...")
        self.statusBar().showMessage("正在处理...")
        
        try:
            self.log_message("=" * 50)
            self.log_message(f"开始处理M4S文件...")
            self.log_message(f"输入文件夹: {input_path}")
            self.log_message(f"输出文件夹: {output_path}")
            self.log_message(f"临时文件夹: {temp_dir}")
            
            # 查找m4s文件对
            file_pairs = find_m4s_pairs(input_path)
            
            if not file_pairs:
                self.log_message("未找到需要处理的m4s文件对")
                QMessageBox.information(self, "信息", "未找到需要处理的m4s文件对")
                return
            
            self.log_message(f"找到 {len(file_pairs)} 个文件对需要处理")
            
            # 处理每个文件对
            for i, (file1, file2) in enumerate(file_pairs, 1):
                self.log_message(f"\n处理文件对 {i}/{len(file_pairs)}:")
                self.log_message(f"  - {file1.name}")
                self.log_message(f"  - {file2.name}")
                
                # 更新UI以显示进度
                QApplication.processEvents()
                
                # 处理文件对
                try:
                    process_file_pair(file1, file2, temp_dir, output_path)
                    self.log_message(f"✅ 文件对处理完成")
                except Exception as e:
                    self.log_message(f"❌ 处理失败: {e}")
                    # 可以选择继续处理下一个或停止
                    continue
            
            self.log_message("\n" + "=" * 50)
            self.log_message(f"🎉 所有文件处理完成！")
            self.log_message(f"输出文件位于: {output_path}")
            
        except Exception as e:
            error_msg = f"处理出错: {str(e)}"
            self.log_message(error_msg)
            self.log_message(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"处理过程中出现错误:\n{str(e)}")
        
        finally:
            # 清理临时文件
            try:
                if temp_dir.exists():
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    self.log_message(f"已清理临时文件夹: {temp_dir}")
            except Exception as e:
                self.log_message(f"清理临时文件夹失败: {e}")
            
            # 恢复按钮状态
            self.process_btn.setEnabled(True)
            self.process_btn.setText("开始处理")
            self.statusBar().showMessage("就绪")
    
    def reset_config(self):
        """重置配置文件"""
        reply = QMessageBox.question(
            self, 
            "重置配置",
            "确定要重置配置文件吗？这将恢复所有默认设置。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # 删除配置文件
                if self.config_manager.config_file.exists():
                    self.config_manager.config_file.unlink()
                    self.log_message("已删除配置文件")
                
                # 重新初始化配置管理器
                self.config_manager = ConfigManager(parent=self)
                
                # 更新界面显示
                self.input_path_edit.setText(self.config_manager.config.get("input_path", ""))
                self.output_path_edit.setText(self.config_manager.config.get("output_path", ""))
                
                self.log_message("配置已重置为默认值")
                QMessageBox.information(self, "成功", "配置文件已重置")
                
            except Exception as e:
                error_msg = f"重置配置失败: {e}"
                self.log_message(error_msg)
                QMessageBox.critical(self, "错误", error_msg)
    
    def log_message(self, message, update_last=False):
        """添加日志消息
        
        Args:
            message: 日志消息
            update_last: 如果为True，更新最后一行而不是追加新行
        """
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        if update_last:
            # 更新最后一行
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.End)
            # 移动到当前行的开始
            cursor.movePosition(cursor.StartOfLine)
            # 选择到行尾
            cursor.movePosition(cursor.EndOfLine, cursor.KeepAnchor)
            # 替换选中文本
            cursor.insertText(f"[{timestamp}] {message}")
        else:
            # 追加新行
            self.log_text.append(f"[{timestamp}] {message}")
        
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
    
    def clear_url_input(self):
        """清空URL输入框"""
        self.url_input.clear()
    
    def show_qr_login(self):
        """显示二维码登录窗口"""
        dialog = QRLoginDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            sessdata = dialog.get_sessdata()
            refresh_token = dialog.get_refresh_token()
            if sessdata:
                self.config_manager.save_session(sessdata=sessdata, refresh_token=refresh_token)
                self.log_message("登录成功，SESSDATA已保存")
                QMessageBox.information(self, "登录成功", "登录信息已保存到配置文件")
            else:
                self.log_message("登录失败或已取消")
    
    def start_download(self):
        """开始下载视频（支持普通视频和番剧）"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "错误", "请输入视频链接、BV号或番剧EP号")
            return
        
        # 检测是否是番剧URL或EP号
        import re
        is_bangumi = False
        ep_match = re.search(r'bangumi/play/ep(\d+)', url)
        ep_id = None
        
        if ep_match:
            # 番剧URL
            is_bangumi = True
            ep_id = ep_match.group(1)
            if not url.startswith('http'):
                url = f"https://www.bilibili.com{url}" if url.startswith('/') else f"https://www.bilibili.com/bangumi/play/ep{ep_id}"
        elif re.match(r'^ep\d+$', url, re.IGNORECASE):
            # 直接输入EP号
            is_bangumi = True
            ep_id = re.search(r'\d+', url).group()
            url = f"https://www.bilibili.com/bangumi/play/ep{ep_id}"
        elif url.upper().startswith('BV') or url.upper().startswith('AV'):
            # 普通视频BV/AV号
            url = f"https://www.bilibili.com/video/{url}"
        
        quality_index = self.quality_combo.currentIndex()
        qn = self.quality_combo.itemData(quality_index)
        
        sessdata = self.config_manager.get_sessdata()
        if not sessdata:
            reply = QMessageBox.question(
                self, 
                "未登录",
                "未检测到登录信息，部分视频可能需要登录才能下载。\n是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        # 获取输出路径
        output_path = Path(self.config_manager.get_output_path())
        output_path.mkdir(parents=True, exist_ok=True)
        
        self.log_message("=" * 50)
        if is_bangumi:
            self.log_message(f"开始下载番剧...")
            self.log_message(f"EP ID: {ep_id}")
        else:
            self.log_message(f"开始下载视频...")
        self.log_message(f"链接: {url}")
        self.log_message(f"画质: {self.quality_combo.currentText()}")
        
        # 禁用下载按钮
        self.download_btn.setEnabled(False)
        self.download_btn.setText("下载中...")
        
        try:
            # 获取视频/番剧信息
            self.log_message("正在获取视频信息...")
            if is_bangumi:
                # 番剧信息获取
                ep_info = download.get_bangumi_video_info(ep_id)
                if not ep_info:
                    raise Exception(f"无法获取番剧信息，EP ID: {ep_id}")
                title = ep_info.get('title', f"EP{ep_id}")
                duration = ep_info.get('duration', 0)
                self.log_message(f"番剧: {ep_info.get('season_title', '未知番剧')}")
                self.log_message(f"集数: {ep_info.get('ep_title', f'EP{ep_id}')}")
            else:
                # 普通视频信息获取
                video_info = download.get_video_info(url)
                title = video_info.get('title', '未知标题')
                duration = video_info.get('duration', 0)
            
            self.log_message(f"标题: {title}")
            
            # 获取下载链接
            self.log_message("正在获取下载链接...")
            download_urls = download.get_download_url(
                url=url,
                sessdata=sessdata or '',
                qn=qn,
                duration=duration,
                smart_resolution=False,
                file_size_limit=100,
                preferred_codec='auto'
            )
            
            video_url = download_urls.get('videoUrl')
            audio_url = download_urls.get('audioUrl')
            
            if not video_url:
                raise Exception("无法获取视频下载链接")
            
            # 创建临时目录
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "bili_download_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # 清理文件名
            def sanitize_filename(name):
                import re
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
                return name[:200].rstrip()
            
            safe_title = sanitize_filename(title)
            video_file = temp_dir / f"{safe_title}_video.m4s"
            audio_file = temp_dir / f"{safe_title}_audio.m4s" if audio_url else None
            output_file = output_path / f"{safe_title}.mp4"
            
            # 下载视频
            self.log_message("正在下载视频文件...")
            self._progress_line_exists = False
            
            def progress_callback(progress=None, current=0, total=0, speed=0, eta=0):
                """下载进度回调，在一行中更新显示"""
                # 格式化速度
                if speed > 0:
                    if speed >= 1024 * 1024:  # MB/s
                        speed_str = f"{speed / (1024 * 1024):.1f}MB/s"
                    else:  # KB/s
                        speed_str = f"{speed / 1024:.1f}KB/s"
                else:
                    speed_str = "计算中..."
                
                # 格式化剩余时间 - 格式：ETA: Xd XXh XXm XXs
                if eta > 0 and speed > 0:
                    days = int(eta // 86400)
                    hours = int((eta % 86400) // 3600)
                    minutes = int((eta % 3600) // 60)
                    seconds = int(eta % 60)
                    eta_str = f"ETA: {days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"
                else:
                    eta_str = "ETA: 计算中..."
                
                # 计算进度百分比
                if total > 0:
                    progress_pct = (current / total) * 100
                else:
                    progress_pct = 0
                
                # 更新日志（在同一行）- 速度和ETA靠左显示，使用----引导
                progress_msg = f"下载进度: {progress_pct:.1f}% ---- {speed_str} ---- {eta_str}"
                self.log_message(progress_msg, update_last=True)
                self._progress_line_exists = True
                QApplication.processEvents()
            
            download.download_b_file(video_url, str(video_file), progress_callback)
            # 清除进度行，显示完成消息
            if self._progress_line_exists:
                self.log_message("视频文件下载完成")
            
            # 下载音频（如果有）
            if audio_url:
                self.log_message("正在下载音频文件...")
                self._progress_line_exists = False
                download.download_b_file(audio_url, str(audio_file), progress_callback)
                if self._progress_line_exists:
                    self.log_message("音频文件下载完成")
                
                # 合并视频和音频
                self.log_message("正在合并视频和音频...")
                download.merge_file_to_mp4(
                    str(video_file),
                    str(audio_file),
                    str(output_file),
                    should_delete=True
                )
                self.log_message("合并完成")
            else:
                # 只有视频（番剧DURL格式或单文件视频）
                # 检查文件扩展名，如果是mp4格式可以直接使用，否则需要转换
                video_ext = Path(video_file).suffix.lower()
                if video_ext == '.mp4':
                    # 直接移动
                    import shutil
                    shutil.move(str(video_file), str(output_file))
                    self.log_message("视频文件已保存")
                else:
                    # 需要转换格式，使用ffmpeg
                    self.log_message("正在转换视频格式...")
                    try:
                        import ffmpeg
                        input_stream = ffmpeg.input(str(video_file))
                        output_stream = ffmpeg.output(
                            input_stream,
                            str(output_file),
                            vcodec='copy',
                            acodec='copy'
                        )
                        ffmpeg.run(ffmpeg.overwrite_output(output_stream), quiet=True, overwrite_output=True)
                        Path(video_file).unlink(missing_ok=True)
                        self.log_message("视频格式转换完成")
                    except Exception as e:
                        # 转换失败，直接重命名
                        import shutil
                        output_file = output_path / f"{safe_title}{video_ext}"
                        shutil.move(str(video_file), str(output_file))
                        self.log_message(f"格式转换失败，已保存为原始格式: {video_ext}")
            
            # 清理临时目录
            try:
                if temp_dir.exists():
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
            
            self.log_message("=" * 50)
            self.log_message(f"✅ 下载完成！")
            self.log_message(f"文件保存位置: {output_file}")
            
        except Exception as e:
            error_msg = f"下载失败: {str(e)}"
            self.log_message(error_msg)
            self.log_message(traceback.format_exc())
            QMessageBox.critical(self, "下载失败", error_msg)
        finally:
            # 恢复按钮状态
            self.download_btn.setEnabled(True)
            self.download_btn.setText("开始下载")


# 二维码登录对话框
class QRLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessdata = ""
        self.refresh_token = ""
        self.qr_thread = None
        self.initUI()
    
    def initUI(self):
        """初始化二维码登录对话框UI"""
        self.setWindowTitle("B站扫码登录")
        self.setGeometry(300, 300, 400, 500)
        
        layout = QVBoxLayout()
        
        # 提示文字
        tip_label = QLabel("请使用B站APP扫描下方二维码登录")
        tip_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip_label)
        
        # 二维码显示区域
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        self.qr_label.setStyleSheet("border: 1px solid gray;")
        layout.addWidget(self.qr_label)
        
        # 状态标签
        self.status_label = QLabel("正在生成二维码...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新二维码")
        self.refresh_btn.clicked.connect(self.refresh_qr)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 开始生成二维码
        self.refresh_qr()
    
    def refresh_qr(self):
        """刷新二维码"""
        if self.qr_thread and self.qr_thread.isRunning():
            return
        
        self.status_label.setText("正在生成二维码...")
        self.refresh_btn.setEnabled(False)
        
        self.qr_thread = QRLoginThread()
        self.qr_thread.qr_ready.connect(self.on_qr_ready)
        self.qr_thread.login_success.connect(self.on_login_success)
        self.qr_thread.login_failed.connect(self.on_login_failed)
        self.qr_thread.start()
    
    def on_qr_ready(self, qr_path, scan_url):
        """二维码生成完成"""
        pixmap = QPixmap(qr_path)
        scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.qr_label.setPixmap(scaled_pixmap)
        self.status_label.setText("请使用B站APP扫描二维码")
        self.refresh_btn.setEnabled(True)
    
    def on_login_success(self, sessdata, refresh_token):
        """登录成功"""
        self.sessdata = sessdata
        self.refresh_token = refresh_token
        self.status_label.setText("登录成功！")
        self.accept()
    
    def on_login_failed(self, message):
        """登录失败"""
        self.status_label.setText(f"登录失败: {message}")
        self.refresh_btn.setEnabled(True)
    
    def get_sessdata(self):
        """获取SESSDATA"""
        return self.sessdata
    
    def get_refresh_token(self):
        """获取refresh_token"""
        return self.refresh_token


# 二维码登录线程
class QRLoginThread(QThread):
    qr_ready = pyqtSignal(str, str)  # qr_path, scan_url
    login_success = pyqtSignal(str, str)  # sessdata, refresh_token
    login_failed = pyqtSignal(str)  # message
    
    def run(self):
        """在线程中执行登录流程"""
        try:
            import tempfile
            temp_dir = Path(tempfile.gettempdir())
            qr_path = str(temp_dir / "bili_qrcode.png")
            
            def qr_hook(path, url):
                self.qr_ready.emit(path, url)
            
            result = download.get_scan_code_data(
                qrcode_save_path=qr_path,
                detect_time=3,
                hook=qr_hook
            )
            
            if result.get('SESSDATA'):
                self.login_success.emit(result['SESSDATA'], result.get('refresh_token', ''))
            else:
                self.login_failed.emit("未获取到登录信息")
        except Exception as e:
            self.login_failed.emit(str(e))

# 主函数
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("A+1 Tool")
    
    window = M4SProcessorGUI()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()