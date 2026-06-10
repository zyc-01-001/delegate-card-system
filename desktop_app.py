#!/usr/bin/env python3
"""
代表证签到系统 - 桌面客户端
使用PyQt6构建，功能稳定优先
"""

import sys
import os
import requests
import json
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QStackedWidget, QFrame,
    QHeaderView, QCheckBox, QFileDialog, QDateEdit, QTabWidget,
    QTextEdit, QSpinBox, QGroupBox, QGridLayout, QSplitter
)
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QFont

# 服务器地址
SERVER_URL = "https://delegate-card-system.onrender.com"
# SERVER_URL = "http://localhost:5000"  # 本地开发用


class APIWorker(QThread):
    """后台API请求线程，避免界面卡顿"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, method, endpoint, data=None, params=None):
        super().__init__()
        self.method = method
        self.endpoint = endpoint
        self.data = data
        self.params = params

    def run(self):
        try:
            url = f"{SERVER_URL}{self.endpoint}"
            if self.method == 'GET':
                response = requests.get(url, params=self.params, timeout=10)
            elif self.method == 'POST':
                response = requests.post(url, json=self.data, timeout=10)
            else:
                response = requests.request(self.method, url, json=self.data, timeout=10)

            if response.status_code == 200:
                self.finished.emit(response.json())
            else:
                self.error.emit(f"服务器错误: {response.status_code}")
        except requests.exceptions.ConnectionError:
            self.error.emit("无法连接到服务器，请检查网络")
        except Exception as e:
            self.error.emit(f"请求失败: {str(e)}")


class LoginWidget(QWidget):
    """管理员登录界面"""
    login_success = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 标题
        title = QLabel("管理后台登录")
        title.setFont(QFont("Microsoft YaHei", 24, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 登录表单
        form_frame = QFrame()
        form_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        form_layout = QGridLayout()

        form_layout.addWidget(QLabel("用户名:"), 0, 0)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入用户名")
        form_layout.addWidget(self.username_input, 0, 1)

        form_layout.addWidget(QLabel("密码:"), 1, 0)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addWidget(self.password_input, 1, 1)

        form_frame.setLayout(form_layout)
        layout.addWidget(form_frame)

        # 登录按钮
        self.login_btn = QPushButton("登录")
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #C41E3A;
                color: white;
                padding: 12px;
                font-size: 16px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #a01830; }
        """)
        self.login_btn.clicked.connect(self.do_login)
        layout.addWidget(self.login_btn)

        # 快捷登录按钮
        quick_layout = QHBoxLayout()
        for i in range(1, 6):
            btn = QPushButton(f"admin0{i}")
            btn.setStyleSheet("padding: 6px; font-size: 12px;")
            btn.clicked.connect(lambda checked, u=f"admin0{i}", p=f"admin123": self.quick_login(u, p))
            quick_layout.addWidget(btn)
        layout.addLayout(quick_layout)

        self.setLayout(layout)

    def quick_login(self, username, password):
        self.username_input.setText(username)
        self.password_input.setText(password)
        self.do_login()

    def do_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "提示", "请输入用户名和密码")
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("登录中...")

        # 使用表单数据登录
        try:
            response = requests.post(
                f"{SERVER_URL}/admin/login",
                data={"username": username, "password": password},
                timeout=10,
                allow_redirects=False
            )
            if response.status_code == 302:
                self.login_success.emit()
            else:
                QMessageBox.warning(self, "错误", "用户名或密码错误")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"登录失败: {str(e)}")
        finally:
            self.login_btn.setEnabled(True)
            self.login_btn.setText("登录")


class CheckinWidget(QWidget):
    """签到核销界面"""
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 标题
        title = QLabel("⚡ 快速核销签到")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        layout.addWidget(title)

        # 方式一：学号/姓名搜索
        group1 = QGroupBox("方式一：搜索核销（推荐）")
        g1_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入学号或姓名，回车核销...")
        self.search_input.returnPressed.connect(self.search_and_checkin)
        g1_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("🔍 查找")
        self.search_btn.clicked.connect(self.search_and_checkin)
        g1_layout.addWidget(self.search_btn)
        group1.setLayout(g1_layout)
        layout.addWidget(group1)

        # 方式二：代表证编号
        group2 = QGroupBox("方式二：代表证编号核销")
        g2_layout = QHBoxLayout()
        self.card_input = QLineEdit()
        self.card_input.setPlaceholderText("输入代表证编号（如：20250001）")
        self.card_input.returnPressed.connect(self.checkin_by_card)
        g2_layout.addWidget(self.card_input)

        self.card_btn = QPushButton("核销签到")
        self.card_btn.clicked.connect(self.checkin_by_card)
        g2_layout.addWidget(self.card_btn)
        group2.setLayout(g2_layout)
        layout.addWidget(group2)

        # 结果显示区域
        self.result_frame = QFrame()
        self.result_frame.setStyleSheet("background-color: #f0f0f0; padding: 20px; border-radius: 10px;")
        self.result_layout = QVBoxLayout()
        self.result_label = QLabel("等待核销...")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_layout.addWidget(self.result_label)
        self.result_frame.setLayout(self.result_layout)
        self.result_frame.setVisible(False)
        layout.addWidget(self.result_frame)

        # 最近核销记录
        layout.addWidget(QLabel("最近核销记录:"))
        self.recent_table = QTableWidget()
        self.recent_table.setColumnCount(4)
        self.recent_table.setHorizontalHeaderLabels(["姓名", "学号", "时间", "状态"])
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.recent_table)

        self.setLayout(layout)

    def search_and_checkin(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            return

        self.search_btn.setEnabled(False)
        try:
            response = requests.get(
                f"{SERVER_URL}/api/search-delegate",
                params={"keyword": keyword},
                timeout=10
            )
            data = response.json()
            if data.get('success') and data.get('results'):
                if len(data['results']) == 1:
                    # 只有一个结果，直接核销
                    self.do_checkin(data['results'][0]['id'], data['results'][0]['name'])
                else:
                    # 多个结果，显示选择对话框
                    self.show_select_dialog(data['results'])
            else:
                self.show_result("未找到该学生", "error")
        except Exception as e:
            self.show_result(f"查询失败: {str(e)}", "error")
        finally:
            self.search_btn.setEnabled(True)
            self.search_input.setFocus()
            self.search_input.selectAll()

    def show_select_dialog(self, results):
        """显示多选对话框"""
        from PyQt6.QtWidgets import QDialog, QListWidget, QListWidgetItem

        dialog = QDialog(self)
        dialog.setWindowTitle("选择学生")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout()

        list_widget = QListWidget()
        for r in results:
            item = QListWidgetItem(f"{r['name']} ({r['student_id']}) - {r['delegation']}")
            item.setData(Qt.ItemDataRole.UserRole, r['id'])
            list_widget.addItem(item)

        layout.addWidget(list_widget)

        btn = QPushButton("确认核销")
        btn.clicked.connect(lambda: self.on_select(dialog, list_widget))
        layout.addWidget(btn)

        dialog.setLayout(layout)
        dialog.exec()

    def on_select(self, dialog, list_widget):
        item = list_widget.currentItem()
        if item:
            delegate_id = item.data(Qt.ItemDataRole.UserRole)
            self.do_checkin(delegate_id, item.text().split('(')[0].strip())
        dialog.accept()

    def checkin_by_card(self):
        card_number = self.card_input.text().strip()
        if not card_number:
            return

        self.card_btn.setEnabled(False)
        try:
            response = requests.post(
                f"{SERVER_URL}/api/checkin-by-card",
                json={"card_number": card_number},
                timeout=10
            )
            data = response.json()
            if data.get('success'):
                if data.get('already'):
                    self.show_result(f"{data['delegate']['name']} 今日已签到", "warning")
                else:
                    self.show_result(f"✅ {data['message']}", "success")
                    self.add_recent_record(data['delegate']['name'], data['delegate']['student_id'], "成功")
            else:
                self.show_result(data.get('message', '核销失败'), "error")
        except Exception as e:
            self.show_result(f"核销失败: {str(e)}", "error")
        finally:
            self.card_btn.setEnabled(True)
            self.card_input.setFocus()
            self.card_input.selectAll()

    def do_checkin(self, delegate_id, name):
        """执行核销"""
        try:
            response = requests.post(
                f"{SERVER_URL}/api/checkin-by-id",
                json={"delegate_id": delegate_id},
                timeout=10
            )
            data = response.json()
            if data.get('success'):
                if data.get('already'):
                    self.show_result(f"{name} 今日已签到", "warning")
                else:
                    self.show_result(f"✅ {data['message']}", "success")
                    self.add_recent_record(data['delegate']['name'], data['delegate']['student_id'], "成功")
            else:
                self.show_result(data.get('message', '核销失败'), "error")
        except Exception as e:
            self.show_result(f"核销失败: {str(e)}", "error")

    def show_result(self, message, msg_type):
        self.result_frame.setVisible(True)
        self.result_label.setText(message)

        colors = {
            "success": "background-color: #d4edda; color: #155724;",
            "warning": "background-color: #fff3cd; color: #856404;",
            "error": "background-color: #f8d7da; color: #721c24;"
        }
        self.result_frame.setStyleSheet(colors.get(msg_type, "") + " padding: 20px; border-radius: 10px;")

    def add_recent_record(self, name, student_id, status):
        row = self.recent_table.rowCount()
        self.recent_table.insertRow(0)
        self.recent_table.setItem(0, 0, QTableWidgetItem(name))
        self.recent_table.setItem(0, 1, QTableWidgetItem(student_id))
        self.recent_table.setItem(0, 2, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))
        self.recent_table.setItem(0, 3, QTableWidgetItem(status))

        # 只保留最近20条
        while self.recent_table.rowCount() > 20:
            self.recent_table.removeRow(self.recent_table.rowCount() - 1)


class DelegateListWidget(QWidget):
    """代表列表界面"""
    def __init__(self):
        super().__init__()
        self.delegates = []
        self.init_ui()
        self.load_delegates()

    def init_ui(self):
        layout = QVBoxLayout()

        # 标题和统计
        header_layout = QHBoxLayout()
        self.title_label = QLabel("代表申报列表")
        self.title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        header_layout.addWidget(self.title_label)

        self.stats_label = QLabel("加载中...")
        header_layout.addStretch()
        header_layout.addWidget(self.stats_label)
        layout.addLayout(header_layout)

        # 筛选和操作按钮
        btn_layout = QHBoxLayout()

        self.filter_all = QPushButton("全部")
        self.filter_all.clicked.connect(lambda: self.filter_status('all'))
        btn_layout.addWidget(self.filter_all)

        self.filter_pending = QPushButton("待审核")
        self.filter_pending.clicked.connect(lambda: self.filter_status('pending'))
        btn_layout.addWidget(self.filter_pending)

        self.filter_approved = QPushButton("已通过")
        self.filter_approved.clicked.connect(lambda: self.filter_status('approved'))
        btn_layout.addWidget(self.filter_approved)

        self.filter_checked = QPushButton("已签到")
        self.filter_checked.clicked.connect(lambda: self.filter_status('checked'))
        btn_layout.addWidget(self.filter_checked)

        self.filter_unchecked = QPushButton("未签到")
        self.filter_unchecked.clicked.connect(lambda: self.filter_status('unchecked'))
        btn_layout.addWidget(self.filter_unchecked)

        btn_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self.load_delegates)
        btn_layout.addWidget(self.refresh_btn)

        self.export_btn = QPushButton("📊 导出数据")
        self.export_btn.clicked.connect(self.export_data)
        btn_layout.addWidget(self.export_btn)

        self.reset_btn = QPushButton("🔄 重置签到")
        self.reset_btn.clicked.connect(self.reset_checkin)
        btn_layout.addWidget(self.reset_btn)

        layout.addLayout(btn_layout)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "ID", "姓名", "学号", "代表团", "类型", "状态", "签到", "签到时间", "操作"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_delegates(self):
        """加载代表列表"""
        try:
            response = requests.get(f"{SERVER_URL}/api/delegates", timeout=10)
            data = response.json()
            if data.get('success'):
                self.delegates = data.get('delegates', [])
                self.update_table()
                self.update_stats(data.get('stats', {}))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载数据失败: {str(e)}")

    def update_table(self):
        self.table.setRowCount(len(self.delegates))
        for i, d in enumerate(self.delegates):
            self.table.setItem(i, 0, QTableWidgetItem(str(d['id'])))
            self.table.setItem(i, 1, QTableWidgetItem(d['name']))
            self.table.setItem(i, 2, QTableWidgetItem(d['student_id']))
            self.table.setItem(i, 3, QTableWidgetItem(d['delegation']))
            self.table.setItem(i, 4, QTableWidgetItem(d['delegation_type']))

            status_text = {"pending": "待审核", "approved": "已通过", "rejected": "已拒绝"}
            status_item = QTableWidgetItem(status_text.get(d['status'], d['status']))
            self.table.setItem(i, 5, status_item)

            checkin_text = "✅ 已签到" if d.get('checked_in') else "未签到"
            self.table.setItem(i, 6, QTableWidgetItem(checkin_text))

            self.table.setItem(i, 7, QTableWidgetItem(d.get('check_in_time', '') or ''))

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(2, 2, 2, 2)

            if d['status'] == 'pending':
                approve_btn = QPushButton("通过")
                approve_btn.setStyleSheet("background-color: #28a745; color: white; padding: 2px 8px;")
                approve_btn.clicked.connect(lambda checked, id=d['id']: self.approve_delegate(id))
                btn_layout.addWidget(approve_btn)

                reject_btn = QPushButton("拒绝")
                reject_btn.setStyleSheet("background-color: #dc3545; color: white; padding: 2px 8px;")
                reject_btn.clicked.connect(lambda checked, id=d['id']: self.reject_delegate(id))
                btn_layout.addWidget(reject_btn)

            if d['status'] == 'approved' and not d.get('checked_in'):
                checkin_btn = QPushButton("补签")
                checkin_btn.setStyleSheet("background-color: #ffc107; color: #333; padding: 2px 8px;")
                checkin_btn.clicked.connect(lambda checked, id=d['id'], name=d['name']: self.manual_checkin(id, name))
                btn_layout.addWidget(checkin_btn)

            btn_widget.setLayout(btn_layout)
            self.table.setCellWidget(i, 8, btn_widget)

    def update_stats(self, stats):
        text = f"总: {stats.get('total', 0)} | 待审: {stats.get('pending', 0)} | 通过: {stats.get('approved', 0)} | 已签到: {stats.get('checked_in', 0)}"
        self.stats_label.setText(text)

    def filter_status(self, status):
        """筛选状态"""
        for i, d in enumerate(self.delegates):
            show = True
            if status == 'pending' and d['status'] != 'pending':
                show = False
            elif status == 'approved' and d['status'] != 'approved':
                show = False
            elif status == 'checked' and not d.get('checked_in'):
                show = False
            elif status == 'unchecked' and (d.get('checked_in') or d['status'] != 'approved'):
                show = False

            self.table.setRowHidden(i, not show)

    def approve_delegate(self, delegate_id):
        """审核通过"""
        try:
            response = requests.get(f"{SERVER_URL}/admin/approve/{delegate_id}", timeout=10)
            QMessageBox.information(self, "成功", "审核通过！")
            self.load_delegates()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"操作失败: {str(e)}")

    def reject_delegate(self, delegate_id):
        """拒绝"""
        reply = QMessageBox.question(self, "确认", "确定拒绝该申请？")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                response = requests.get(f"{SERVER_URL}/admin/reject/{delegate_id}", timeout=10)
                QMessageBox.information(self, "成功", "已拒绝！")
                self.load_delegates()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"操作失败: {str(e)}")

    def manual_checkin(self, delegate_id, name):
        """手动补签"""
        reply = QMessageBox.question(self, "确认", f"确定为 {name} 补签吗？")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                response = requests.post(
                    f"{SERVER_URL}/api/checkin-by-id",
                    json={"delegate_id": delegate_id},
                    timeout=10
                )
                data = response.json()
                if data.get('success'):
                    QMessageBox.information(self, "成功", data.get('message', '补签成功'))
                    self.load_delegates()
                else:
                    QMessageBox.warning(self, "提示", data.get('message', '补签失败'))
            except Exception as e:
                QMessageBox.critical(self, "错误", f"补签失败: {str(e)}")

    def reset_checkin(self):
        """重置签到"""
        reply = QMessageBox.question(
            self, "确认",
            "确定重置所有签到状态吗？\n历史记录仍会保留。"
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                response = requests.post(f"{SERVER_URL}/api/reset-checkin", timeout=10)
                data = response.json()
                if data.get('success'):
                    QMessageBox.information(self, "成功", data.get('message', '重置成功'))
                    self.load_delegates()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"重置失败: {str(e)}")

    def export_data(self):
        """导出数据"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出数据", f"代表名单_{datetime.now().strftime('%Y%m%d')}.csv",
            "CSV文件 (*.csv)"
        )
        if not file_path:
            return

        try:
            import csv
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['ID', '姓名', '学号', '性别', '代表团', '类型', '状态', '签到', '签到时间'])
                for d in self.delegates:
                    writer.writerow([
                        d['id'], d['name'], d['student_id'],
                        d.get('gender', ''), d['delegation'], d['delegation_type'],
                        d['status'], '是' if d.get('checked_in') else '否',
                        d.get('check_in_time', '')
                    ])
            QMessageBox.information(self, "成功", f"数据已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")


class DateCheckinWidget(QWidget):
    """按日期查看签到记录"""
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 标题
        title = QLabel("📅 按日期查看签到记录")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # 日期选择
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("选择日期:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        date_layout.addWidget(self.date_edit)

        self.query_btn = QPushButton("查询")
        self.query_btn.clicked.connect(self.load_records)
        date_layout.addWidget(self.query_btn)

        date_layout.addStretch()
        layout.addLayout(date_layout)

        # 统计
        self.stats_label = QLabel("")
        layout.addWidget(self.stats_label)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["姓名", "学号", "代表团", "签到时间", "操作员"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_records(self):
        date = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            response = requests.get(
                f"{SERVER_URL}/api/checkin-by-date",
                params={"date": date},
                timeout=10
            )
            data = response.json()
            if data.get('success'):
                stats = data.get('stats', {})
                self.stats_label.setText(
                    f"总通过: {stats.get('total_approved', 0)} | "
                    f"已签到: {stats.get('checkin_count', 0)} | "
                    f"未签到: {stats.get('not_checkin', 0)} | "
                    f"签到率: {stats.get('total_approved', 0) and round(stats['checkin_count']/stats['total_approved']*100)}%"
                )

                records = data.get('records', [])
                self.table.setRowCount(len(records))
                for i, r in enumerate(records):
                    self.table.setItem(i, 0, QTableWidgetItem(r['name']))
                    self.table.setItem(i, 1, QTableWidgetItem(r['student_id']))
                    self.table.setItem(i, 2, QTableWidgetItem(r['delegation']))
                    self.table.setItem(i, 3, QTableWidgetItem(r.get('check_time', '')))
                    self.table.setItem(i, 4, QTableWidgetItem(r.get('admin_user', 'admin')))
            else:
                QMessageBox.warning(self, "提示", data.get('message', '查询失败'))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"查询失败: {str(e)}")


class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("代表证签到系统 - 桌面客户端")
        self.setMinimumSize(1200, 800)
        self.init_ui()

    def init_ui(self):
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        # 左侧导航栏
        nav_widget = QWidget()
        nav_widget.setMaximumWidth(200)
        nav_widget.setStyleSheet("background-color: #2c3e50;")
        nav_layout = QVBoxLayout()
        nav_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 标题
        nav_title = QLabel("代表证签到系统")
        nav_title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        nav_title.setStyleSheet("color: white; padding: 20px;")
        nav_layout.addWidget(nav_title)

        # 导航按钮
        self.nav_buttons = []
        nav_items = [
            ("⚡ 签到核销", 0),
            ("📋 代表列表", 1),
            ("📅 日期查询", 2),
        ]

        for text, index in nav_items:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    color: white;
                    background-color: transparent;
                    border: none;
                    padding: 15px;
                    text-align: left;
                    font-size: 14px;
                }
                QPushButton:hover { background-color: #34495e; }
                QPushButton:checked { background-color: #C41E3A; }
            """)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, idx=index: self.switch_page(idx))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        nav_layout.addStretch()

        # 退出按钮
        logout_btn = QPushButton("🚪 退出登录")
        logout_btn.setStyleSheet("""
            QPushButton {
                color: white;
                background-color: #e74c3c;
                border: none;
                padding: 12px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        logout_btn.clicked.connect(self.logout)
        nav_layout.addWidget(logout_btn)

        nav_widget.setLayout(nav_layout)
        main_layout.addWidget(nav_widget)

        # 右侧内容区域
        self.stack = QStackedWidget()

        # 登录页面
        self.login_widget = LoginWidget()
        self.login_widget.login_success.connect(self.on_login_success)
        self.stack.addWidget(self.login_widget)

        # 功能页面（先创建，登录后显示）
        self.checkin_widget = CheckinWidget()
        self.delegate_list_widget = DelegateListWidget()
        self.date_checkin_widget = DateCheckinWidget()

        self.stack.addWidget(self.checkin_widget)
        self.stack.addWidget(self.delegate_list_widget)
        self.stack.addWidget(self.date_checkin_widget)

        main_layout.addWidget(self.stack)

        # 默认显示登录页
        self.show_login()

    def show_login(self):
        """显示登录页"""
        self.stack.setCurrentIndex(0)
        for btn in self.nav_buttons:
            btn.setVisible(False)

    def on_login_success(self):
        """登录成功"""
        for btn in self.nav_buttons:
            btn.setVisible(True)
        self.switch_page(0)

    def switch_page(self, index):
        """切换页面"""
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.stack.setCurrentIndex(index + 1)  # +1 因为0是登录页

    def logout(self):
        """退出登录"""
        reply = QMessageBox.question(self, "确认", "确定退出登录吗？")
        if reply == QMessageBox.StandardButton.Yes:
            self.show_login()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # 设置全局字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
