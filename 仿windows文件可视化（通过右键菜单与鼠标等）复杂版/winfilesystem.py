import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

FILENAME_LEN = 256

class FileNode:
    def __init__(self, name, isdir, parent=None):
        self.name = name
        self.isdir = isdir
        self.parent = parent
        self.child = None
        self.sibling_prev = None
        self.sibling_next = None
        self.content = ""
        self.metadata = {
            'created': QDateTime.currentDateTime(),
            'modified': QDateTime.currentDateTime(),
            'size': 0
        }

    def full_path(self):
        path = []
        node = self
        while node.parent:
            path.append(node.name)
            node = node.parent
        return '/' + '/'.join(reversed(path)) if path else '/'

class FileSystemModel(QAbstractItemModel):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root
        self.current = root

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        
        parent_node = parent.internalPointer() if parent.isValid() else self.current
        child = parent_node.child
        for _ in range(row):
            child = child.sibling_next if child else None
        return self.createIndex(row, column, child) if child else QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        
        child = index.internalPointer()
        parent = child.parent
        if parent == self.root or parent == self.current:
            return QModelIndex()
        
        return self.createIndex(self.sibling_index(parent), 0, parent)

    def sibling_index(self, node):
        if not node.parent:
            return 0
        index = 0
        current = node.parent.child
        while current:
            if current == node:
                return index
            current = current.sibling_next
            index += 1
        return 0

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        parent_node = parent.internalPointer() if parent.isValid() else self.current
        count = 0
        child = parent_node.child
        while child:
            count += 1
            child = child.sibling_next
        return count

    def columnCount(self, parent=QModelIndex()):
        return 4

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        
        node = index.internalPointer()
        col = index.column()
        
        if role == Qt.DisplayRole:
            if col == 0:
                return node.name
            elif col == 1:
                return "目录" if node.isdir else "文件"
            elif col == 2:
                return node.metadata['modified'].toString(Qt.DefaultLocaleShortDate)
            elif col == 3:
                return self._format_size(node.metadata['size'])
        elif role == Qt.DecorationRole and col == 0:
            return QIcon('folder.png' if node.isdir else 'file.png')
        elif role == Qt.UserRole:
            return node
        
        return None

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def remove_node(self, parent_index, node):
        parent = parent_index.internalPointer() if parent_index.isValid() else self.current
        
        row = 0
        current = parent.child
        while current and current != node:
            current = current.sibling_next
            row += 1
        
        if not current:
            return False

        self.beginRemoveRows(parent_index, row, row)
        
        if node.sibling_prev:
            node.sibling_prev.sibling_next = node.sibling_next
        if node.sibling_next:
            node.sibling_next.sibling_prev = node.sibling_prev
        if parent.child == node:
            parent.child = node.sibling_next
        
        node.parent = None
        node.sibling_prev = None
        node.sibling_next = None
        
        self.endRemoveRows()
        return True

class FileEditor(QDialog):
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle(f"编辑文件 - {node.name}")
        self.setMinimumSize(800, 600)
        
        layout = QVBoxLayout()
        
        # 文本编辑区域
        self.editor = QTextEdit()
        self.editor.setPlainText(node.content)
        self.original_content = node.content
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("就绪")
        
        # 按钮组
        btn_box = QDialogButtonBox()
        self.save_btn = btn_box.addButton("保存", QDialogButtonBox.AcceptRole)
        self.save_btn.clicked.connect(self.save_content)
        btn_box.addButton(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        
        # 布局
        layout.addWidget(self.editor)
        layout.addWidget(btn_box)
        layout.addWidget(self.status_bar)
        self.setLayout(layout)
        
        # 文本变化监测
        self.editor.textChanged.connect(self.update_save_state)

    def update_save_state(self):
        modified = self.editor.toPlainText() != self.original_content
        self.save_btn.setEnabled(modified)
        self.status_bar.showMessage("* 已修改" if modified else "未修改")

    def save_content(self):
        try:
            new_content = self.editor.toPlainText()
            self.node.content = new_content
            self.node.metadata.update({
                'modified': QDateTime.currentDateTime(),
                'size': len(new_content.encode('utf-8'))
            })
            self.original_content = new_content
            self.status_bar.showMessage("保存成功！", 3000)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存错误", str(e))

class FileManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = FileNode("", True)
        self.current = self.root
        self.initUI()
        self.initFileSystem()
        self.history = []
        self.future = []

    def initFileSystem(self):
        home = self._create_node("ROOT", True, self.root)

    def initUI(self):
        self.setWindowTitle('文件管理系统')
        self.setGeometry(300, 300, 1024, 768)
        
        main_widget = QWidget()
        layout = QHBoxLayout()
        
        # 目录树
        self.tree = QTreeView()
        self.model = FileSystemModel(self.root)
        self.tree.setModel(self.model)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.showContextMenu)
        self.tree.doubleClicked.connect(self.navigateTree)
        
        # 文件列表
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.showContextMenu)
        self.list.doubleClicked.connect(self.open_selected_file)
        
        # 分割视图
        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.list)
        layout.addWidget(splitter)
        
        # 工具栏
        toolbar = QToolBar()
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("输入路径...")
        toolbar.addWidget(self.address_bar)
        self.address_bar.returnPressed.connect(self.navigateAddress)
        
        # 导航按钮
        nav_btns = [
            ('back.png', '后退', self.navigateBack),
            ('forward.png', '前进', self.navigateForward),
            ('up.png', '上级目录', self.navigateUp),
            ('refresh.png', '刷新', self.refresh_view)
        ]
        
        for icon, tip, handler in nav_btns:
            btn = QAction(QIcon(icon), tip, self)
            btn.triggered.connect(handler)
            toolbar.addAction(btn)
        
        self.addToolBar(toolbar)
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

    def _create_node(self, name, isdir, parent):
        node = FileNode(name, isdir, parent)
        if parent.child is None:
            parent.child = node
        else:
            last = parent.child
            while last.sibling_next:
                last = last.sibling_next
            last.sibling_next = node
            node.sibling_prev = last
        return node

    def resolve_path(self, path):
        if path.startswith('~'):
            path = '/Home' + path[1:]
        
        current = self.root if path.startswith('/') else self.current
        parts = [p for p in path.split('/') if p]
        
        for part in parts:
            if part == '.':
                continue
            if part == '..':
                if current.parent:
                    current = current.parent
                continue
            
            found = None
            child = current.child
            while child:
                if child.name == part:
                    found = child
                    break
                child = child.sibling_next
            
            if not found:
                raise FileNotFoundError(f"路径不存在: {path}")
            current = found
        return current

    def refresh_view(self):
        self.model.layoutChanged.emit()
        self.tree.expandAll()

    def navigateTree(self, index):
        node = index.data(Qt.UserRole)
        if node and node.isdir:
            self.history.append(self.current)
            self.future.clear()
            self.current = node
            self.address_bar.setText(node.full_path())
            self.refresh_view()

    def open_selected_file(self, index):
        node = index.data(Qt.UserRole)
        if node and not node.isdir:
            self.open_file(node)

    def navigateAddress(self):
        try:
            node = self.resolve_path(self.address_bar.text())
            self.history.append(self.current)
            self.future.clear()
            self.current = node
            self.refresh_view()
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    def navigateBack(self):
        if self.history:
            self.future.append(self.current)
            self.current = self.history.pop()
            self.address_bar.setText(self.current.full_path())
            self.refresh_view()

    def navigateForward(self):
        if self.future:
            self.history.append(self.current)
            self.current = self.future.pop()
            self.address_bar.setText(self.current.full_path())
            self.refresh_view()

    def navigateUp(self):
        if self.current.parent:
            self.history.append(self.current)
            self.current = self.current.parent
            self.address_bar.setText(self.current.full_path())
            self.refresh_view()

    def showContextMenu(self, pos):
        menu = QMenu()
        source = self.sender()
        index = source.indexAt(pos)
        node = index.data(Qt.UserRole) if index.isValid() else self.current
        
        if node.isdir:
            menu.addAction("新建文件夹", lambda: self.create_item(node, True))
            menu.addAction("新建文件", lambda: self.create_item(node, False))
            menu.addSeparator()
        else:
            menu.addAction("打开", lambda: self.open_file(node))
            menu.addSeparator()
        
        if node != self.root:
            menu.addAction("删除", lambda: self.delete_item(node))
            menu.addAction("重命名", lambda: self.rename_item(node))
            menu.addSeparator()
        
        menu.addAction("属性", lambda: self.show_properties(node))
        menu.exec_(source.viewport().mapToGlobal(pos))

    def create_item(self, parent_node, isdir):
        name, ok = QInputDialog.getText(self, "新建", "名称:")
        if not ok or not name:
            return
        
        try:
            child = parent_node.child
            while child:
                if child.name == name:
                    raise FileExistsError("名称已存在")
                child = child.sibling_next
            
            new_node = self._create_node(name, isdir, parent_node)
            if not isdir:
                self.open_file(new_node)  # 创建后直接打开编辑
            self.refresh_view()
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    def open_file(self, node):
        if node.isdir:
            return
        
        editor = FileEditor(node, self)
        if editor.exec_() == QDialog.Accepted:
            # 更新文件属性
            index = self.model.index(0, 0, self.model.parent(self.model.createIndex(0, 0, node)))
            self.model.dataChanged.emit(
                index,
                index.sibling(index.row(), 3)
            )

    def delete_item(self, node):
        if node == self.root:
            QMessageBox.critical(self, "错误", "不能删除根目录")
            return
        
        if node.isdir and node.child:
            reply = QMessageBox.question(self, "确认删除", 
                                       "目录包含内容，确认删除？",
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        try:
            parent = node.parent
            parent_index = self.model.index(self.model.sibling_index(parent), 0, 
                                          self.model.parent(self.model.createIndex(0, 0, parent)))
            
            self._delete_node(node, parent_index)
            
            self.history = [n for n in self.history if n != node]
            self.future = [n for n in self.future if n != node]
            
            if self.current == node:
                self.current = self.root
                self.address_bar.setText(self.current.full_path())
            
            self.refresh_view()
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    def _delete_node(self, node, parent_index):
        child = node.child
        while child:
            next_child = child.sibling_next
            self._delete_node(child, self.model.index(0, 0, parent_index))
            child = next_child
        
        self.model.remove_node(parent_index, node)

    def rename_item(self, node):
        new_name, ok = QInputDialog.getText(self, "重命名", 
                                          "新名称:", text=node.name)
        if not ok or not new_name:
            return
        
        try:
            sibling = node.parent.child
            while sibling:
                if sibling != node and sibling.name == new_name:
                    raise FileExistsError("名称已存在")
                sibling = sibling.sibling_next
            node.name = new_name
            self.refresh_view()
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    def show_properties(self, node):
        dialog = QDialog(self)
        dialog.setWindowTitle("属性")
        layout = QFormLayout()
        
        info = [
            ("名称", node.name),
            ("类型", "目录" if node.isdir else "文件"),
            ("路径", node.full_path()),
            ("创建时间", node.metadata['created'].toString(Qt.DefaultLocaleLongDate)),
            ("修改时间", node.metadata['modified'].toString(Qt.DefaultLocaleLongDate))
        ]
        
        if not node.isdir:
            info.extend([
                ("大小", self.model._format_size(node.metadata['size'])),
                ("内容预览", node.content[:100] + ("..." if len(node.content)>100 else ""))
            ])
        
        for label, value in info:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"<b>{label}:</b>"))
            row.addWidget(QLabel(str(value)))
            layout.addRow(row)
        
        dialog.setLayout(layout)
        dialog.exec_()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    fm = FileManager()
    fm.show()
    sys.exit(app.exec_())