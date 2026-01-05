import sys
import json
import ctypes
import traceback
import resources  # 图标文件资源
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QGroupBox, QFileDialog, QMessageBox, QTextEdit
)
from PyQt5.QtGui import QIcon
from m4s import *

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
        else:
            print(f"[ConfigManager] {message}")
    
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
            "output_path": str(default_output_path)
        }
        
        # 如果配置文件不存在，创建默认配置文件
        if not self.config_file.exists():
            print(f"配置文件不存在，将创建默认配置")
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
            for key in ["input_path", "output_path"]:
                if key not in loaded_config:
                    loaded_config[key] = default_config[key]
                    print(f"配置文件中缺少 {key}，使用默认值")
            
            # 验证路径是否存在（只检查输入路径，输出路径不存在会自动创建）
            if "input_path" in loaded_config:
                input_path = Path(loaded_config["input_path"])
                if not input_path.exists():
                    print(f"警告: 保存的输入路径不存在: {input_path}")
            
            return loaded_config
            
        except json.JSONDecodeError as e:
            error_msg = f"配置文件JSON格式错误: {e}"
            print(error_msg)
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
            print(error_msg)
            # 使用默认配置
            return default_config
    
    def save_default_config(self, default_config):
        """保存默认配置到文件"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            print(f"已创建默认配置文件: {self.config_file.absolute()}")
            return True
        except Exception as e:
            print(f"创建默认配置文件失败: {e}")
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
                print(f"已备份损坏的配置文件到: {backup_file.name}")
            except Exception as e:
                print(f"备份配置文件失败: {e}")
    
    def save_config(self, input_path=None, output_path=None):
        """保存配置到文件"""
        if input_path:
            self.config["input_path"] = str(input_path)
        if output_path:
            self.config["output_path"] = str(output_path)
        
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
        
        # ========== 4. 日志输出区域 ==========
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
        main_layout.addWidget(log_group, 1)
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
        # 设置手动编辑后的自动保存
        self.setup_connections()

    def update_paths_from_config(self):
        """从配置文件更新路径显示"""
        # 这里只是初始化控件，配置管理器会在之后初始化
        pass
    
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
    
    def log_message(self, message):
        """添加日志消息"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear_log(self):
        """清空日志"""
        self.log_text.clear()

# 主函数
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("A+1 Tool")
    
    window = M4SProcessorGUI()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()