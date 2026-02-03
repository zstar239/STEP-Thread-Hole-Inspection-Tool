import sys
import os
import csv

# --- 1. PyQt5 Imports ---
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                             QFileDialog, QHeaderView, QSplitter, QMessageBox, QLabel, QFrame)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon

# --- 2. PythonOCC Imports ---
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IGESControl import IGESControl_Reader
from OCC.Core.StlAPI import StlAPI_Reader
from OCC.Core.IFSelect import IFSelect_RetDone

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.GeomAbs import GeomAbs_Cylinder

from OCC.Core.gp import gp_Pnt
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeSphere
from OCC.Core.TopoDS import TopoDS_Shape

from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB

# --- 3. Backend 配置 ---
from OCC.Display.backend import load_backend
load_backend("pyqt5")
from OCC.Display.qtDisplay import qtViewer3d


def qcolor(r, g, b):
    """0~1 RGB -> Quantity_Color"""
    return Quantity_Color(float(r), float(g), float(b), Quantity_TOC_RGB)


def first_ais(ret):
    """
    pythonOCC 的 DisplayShape 在不同版本里可能返回：
    - AIS_InteractiveObject
    - [AIS_InteractiveObject]
    - (AIS_InteractiveObject, ...) 之类
    这里统一取第一个 AIS。
    """
    if ret is None:
        return None
    if isinstance(ret, (list, tuple)):
        return ret[0] if len(ret) > 0 else None
    return ret


class ScrewInspectorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STEP螺纹孔检测工具")
        self.setWindowIcon(QIcon("logo.png"))
        self.resize(1600, 900)

        # 核心数据
        self.current_shape = None
        self.holes_data = []
        self.current_fmt = None  # step/iges/stl

        # ===== 运行时显示句柄（用于高亮/管理）=====
        self._hole_line_ais = []
        self._hole_center_ais = []
        self._selected_idx = None

        # 模型透明度（0~1；越大越透明）
        self.model_transparency = 0.6

        self.init_ui()

    def init_ui(self):
        # 主窗口容器
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # === 1. 主分割器 (左侧3D | 右侧控制区) ===
        self.splitter = QSplitter(Qt.Horizontal)

        # --- 左侧：3D 视图 ---
        self.canvas = qtViewer3d(self)
        self.splitter.addWidget(self.canvas)

        # --- 右侧：控制面板 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # A. 右侧上方：按钮区域
        btn_layout = QVBoxLayout()

        self.btn_load = QPushButton("📂 加载 CAD 文件 (STEP/IGES/STL)")
        self.btn_load.setMinimumHeight(40)
        self.btn_load.clicked.connect(self.load_file_dialog)

        self.btn_clear = QPushButton("🗑️ 清除模型")
        self.btn_clear.setMinimumHeight(40)
        self.btn_clear.clicked.connect(self.clear_all)

        # ===== 新增：删除选中孔、导出CSV =====
        self.btn_delete = QPushButton("❌ 删除选中孔")
        self.btn_delete.setMinimumHeight(36)
        self.btn_delete.clicked.connect(self.delete_selected_hole)

        self.btn_export = QPushButton("💾 导出表格数据 (CSV)")
        self.btn_export.setMinimumHeight(36)
        self.btn_export.clicked.connect(self.export_table_csv)

        self.lbl_status = QLabel("状态: 等待文件...")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: gray; font-size: 12px;")

        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_export)
        btn_layout.addWidget(self.lbl_status)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        btn_layout.addWidget(line)

        right_layout.addLayout(btn_layout)

        # B. 右侧下方：数据表格
        self.table = QTableWidget()
        self.setup_table()
        right_layout.addWidget(self.table)

        # 将右侧面板加入分割器
        self.splitter.addWidget(right_panel)

        # 设置分割比例 (2:1)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.splitter)

        # 初始化 3D 环境
        self.canvas.InitDriver()
        self.display = self.canvas._display

        # 初始化就清场 + 画轴
        self.reset_scene()
        self.draw_axes()
        self.display.Repaint()

        # 强制初始化时就是 2:1
        QTimer.singleShot(0, self.apply_initial_splitter_sizes)

    def apply_initial_splitter_sizes(self):
        total = self.splitter.size().width()
        if total <= 0:
            total = self.width()
        left = int(total * 2 / 3)
        right = max(1, total - left)
        self.splitter.setSizes([left, right])

    def setup_table(self):
        """配置表格"""
        self.columns = ["ID", "半径(mm)", "Loc X", "Loc Y", "Loc Z", "Dir X", "Dir Y", "Dir Z"]
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        self.table.setAlternatingRowColors(True)
        self.table.setColumnWidth(0, 40)

        # —— 选中一行并触发高亮
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_table_select)

    # ====== 关键：真正清场（把 Context 里对象 Remove 掉）======
    def reset_scene(self):
        try:
            ctx = self.display.Context
            ctx.RemoveAll(False)
            ctx.UpdateCurrentViewer()
        except Exception:
            try:
                self.display.EraseAll()
            except Exception:
                pass

        self._hole_line_ais = []
        self._hole_center_ais = []
        self._selected_idx = None

    def draw_axes(self):
        """绘制坐标轴（避免 DisplayMessage 文字残留）"""
        origin_pnt = gp_Pnt(0, 0, 0)
        self.display.DisplayShape(BRepBuilderAPI_MakeVertex(origin_pnt).Vertex(),
                                 color="BLACK", update=False)

        axis_len = 50.0
        self.display.DisplayShape(BRepBuilderAPI_MakeEdge(origin_pnt, gp_Pnt(axis_len, 0, 0)).Edge(),
                                 color="RED", update=False)
        self.display.DisplayShape(BRepBuilderAPI_MakeEdge(origin_pnt, gp_Pnt(0, axis_len, 0)).Edge(),
                                 color="GREEN", update=False)
        self.display.DisplayShape(BRepBuilderAPI_MakeEdge(origin_pnt, gp_Pnt(0, 0, axis_len)).Edge(),
                                 color="BLUE", update=False)

    def shape_has_faces(self, shape) -> bool:
        """判断 shape 是否包含面；用于决定是否应用透明度（线框透明会很难看）"""
        if shape is None or shape.IsNull():
            return False
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        return exp.More()

    # ========== 多格式文件选择 ==========
    def load_file_dialog(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 CAD 文件",
            "",
            "CAD Files (*.stp *.step *.igs *.iges *.stl);;STEP (*.stp *.step);;IGES (*.igs *.iges);;STL (*.stl);;All Files (*)",
            options=options
        )
        if file_path:
            self.process_file(file_path)

    # ========== 多格式读取 Shape（修复 IGES 显示：TransferRoots + OneShape + IsNull 检查） ==========
    def load_shape(self, filename):
        ext = os.path.splitext(filename)[1].lower()

        # STEP
        if ext in [".stp", ".step"]:
            reader = STEPControl_Reader()
            status = reader.ReadFile(filename)
            if status != IFSelect_RetDone:
                return None, "STEP 文件读取失败", None

            try:
                reader.TransferRoots()
            except Exception:
                try:
                    reader.TransferRoot()
                except Exception:
                    return None, "STEP 转换失败", None

            shape = reader.OneShape()
            if shape.IsNull():
                return None, "STEP 转换结果为空（OneShape 为 Null）", None
            return shape, "STEP 加载成功", "step"

        # IGES
        if ext in [".igs", ".iges"]:
            reader = IGESControl_Reader()
            status = reader.ReadFile(filename)
            if status != IFSelect_RetDone:
                return None, "IGES 文件读取失败", None

            try:
                reader.TransferRoots(False)
            except TypeError:
                try:
                    reader.TransferRoots()
                except Exception:
                    return None, "IGES 转换失败（TransferRoots 调用失败）", None

            shape = reader.OneShape()
            if shape.IsNull():
                try:
                    n = reader.NbShapes()
                except Exception:
                    n = -1
                return None, f"IGES 转换结果为空（OneShape 为 Null，NbShapes={n}）", None

            return shape, "IGES 加载成功", "iges"

        # STL（网格）
        if ext in [".stl"]:
            stl_reader = StlAPI_Reader()
            shape = TopoDS_Shape()
            ok = False
            try:
                ok = stl_reader.Read(shape, filename)
            except TypeError:
                try:
                    ok = stl_reader.Read(filename, shape)
                except Exception:
                    ok = False

            if not ok or shape.IsNull():
                return None, "STL 文件读取失败 / 结果为空", None
            return shape, "STL 加载成功（网格模型：圆柱孔提取不可用）", "stl"

        return None, f"不支持的格式: {ext}", None

    def clear_all(self):
        """清除数据和视图"""
        self.reset_scene()
        self.draw_axes()
        self.display.Repaint()

        self.table.setRowCount(0)
        self.current_shape = None
        self.holes_data = []
        self.current_fmt = None
        self.lbl_status.setText("状态: 已清除")

    def process_file(self, filename):
        # 先硬清场
        self.reset_scene()
        self.draw_axes()
        self.display.Repaint()

        self.lbl_status.setText(f"处理中: {os.path.basename(filename)}")
        QApplication.processEvents()

        try:
            shape, msg, fmt = self.load_shape(filename)
            if shape is None:
                QMessageBox.critical(self, "错误", msg)
                return

            self.current_shape = shape
            self.current_fmt = fmt

            # STL：只显示，不提取孔
            if fmt == "stl":
                self.holes_data = []
                self.update_visualization()
                self.update_table()
                self.lbl_status.setText(msg)
                return

            # STEP/IGES：走圆柱孔检测
            self.holes_data = self.extract_holes_logic(self.current_shape)

            self.update_visualization()
            self.update_table()

            if fmt == "iges" and len(self.holes_data) == 0:
                self.lbl_status.setText("IGES 加载成功，但未检测到圆柱孔（可能被导出为 NURBS 曲面）")
            else:
                self.lbl_status.setText(f"{msg} | 检测到 {len(self.holes_data)} 个特征")

        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    def extract_holes_logic(self, shape):
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        holes = []
        processed_centers = []

        while explorer.More():
            face = explorer.Current()
            surf = BRepAdaptor_Surface(face, True)

            if surf.GetType() == GeomAbs_Cylinder:
                cylinder = surf.Cylinder()
                location = cylinder.Location()
                axis = cylinder.Axis().Direction()
                radius = cylinder.Radius()

                # 去重（按中心点）
                is_duplicate = False
                for p in processed_centers:
                    if location.Distance(p) < 0.01:
                        is_duplicate = True
                        break

                if not is_duplicate:
                    holes.append({
                        "location": (location.X(), location.Y(), location.Z()),
                        "direction": (axis.X(), axis.Y(), axis.Z()),
                        "radius": float(radius)
                    })
                    processed_centers.append(location)

            explorer.Next()

        holes.sort(key=lambda x: x['radius'])
        return holes

    def update_table(self):
        # 更新表格时，避免 selectionChanged 在中途触发
        self.table.blockSignals(True)

        self.table.setRowCount(0)
        for i, hole in enumerate(self.holes_data):
            self.table.insertRow(i)
            r = hole['radius']
            loc = hole['location']
            d = hole['direction']

            items = [f"#{i + 1}", f"{r:.2f}",
                     f"{loc[0]:.2f}", f"{loc[1]:.2f}", f"{loc[2]:.2f}",
                     f"{d[0]:.2f}", f"{d[1]:.2f}", f"{d[2]:.2f}"]

            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, col, item)

        self.table.blockSignals(False)

    def update_visualization(self):
        self.reset_scene()
        self.draw_axes()

        # 显示模型：如果含面 -> 半透明；仅线框/无面 -> 不透明（避免“看不到”）
        if self.current_shape is not None and (not self.current_shape.IsNull()):
            if self.shape_has_faces(self.current_shape):
                self.display.DisplayShape(self.current_shape, transparency=self.model_transparency,
                                         color=None, update=False)
            else:
                self.display.DisplayShape(self.current_shape, color=None, update=False)

        # 逐孔画方向线 + 孔中心球（用于高亮）
        self._hole_line_ais = []
        self._hole_center_ais = []

        for i, hole in enumerate(self.holes_data):
            loc = hole["location"]
            direction = hole["direction"]

            p1 = gp_Pnt(loc[0], loc[1], loc[2])
            line_len = 30.0
            p2 = gp_Pnt(loc[0] - direction[0] * line_len,
                        loc[1] - direction[1] * line_len,
                        loc[2] - direction[2] * line_len)

            edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
            ais_line = first_ais(self.display.DisplayShape(edge, color="RED", update=False))
            self._hole_line_ais.append(ais_line)

            center_radius = max(0.6, float(hole["radius"]) * 0.08)
            sphere = BRepPrimAPI_MakeSphere(p1, center_radius).Shape()
            ais_center = first_ais(self.display.DisplayShape(sphere, color="WHITE", update=False))
            self._hole_center_ais.append(ais_center)

        self.display.FitAll()
        self.display.Repaint()

    # ========== 表格选中 -> 高亮 ==========
    def on_table_select(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.holes_data):
            return
        self.highlight_hole(row)

    def highlight_hole(self, idx: int):
        ctx = self.display.Context

        # 还原上一次高亮
        if self._selected_idx is not None:
            old = self._selected_idx
            if 0 <= old < len(self._hole_line_ais):
                ais_line = self._hole_line_ais[old]
                if ais_line:
                    try:
                        ctx.SetColor(ais_line, qcolor(1, 0, 0), False)  # 红
                        ctx.SetWidth(ais_line, 1.0, False)
                    except Exception:
                        pass
            if 0 <= old < len(self._hole_center_ais):
                ais_c = self._hole_center_ais[old]
                if ais_c:
                    try:
                        ctx.SetColor(ais_c, qcolor(1, 1, 1), False)  # 白
                    except Exception:
                        pass

        # 设置新的高亮
        self._selected_idx = idx

        if 0 <= idx < len(self._hole_line_ais):
            ais_line = self._hole_line_ais[idx]
            if ais_line:
                try:
                    ctx.SetColor(ais_line, qcolor(1, 1, 0), False)  # 黄
                    ctx.SetWidth(ais_line, 3.0, False)
                except Exception:
                    pass

        if 0 <= idx < len(self._hole_center_ais):
            ais_c = self._hole_center_ais[idx]
            if ais_c:
                try:
                    ctx.SetColor(ais_c, qcolor(1, 1, 0), False)  # 黄
                except Exception:
                    pass

        try:
            ctx.UpdateCurrentViewer()
        except Exception:
            self.display.Repaint()

    # ========== 新增：删除选中孔 ==========
    def delete_selected_hole(self):
        if not self.holes_data:
            QMessageBox.information(self, "提示", "当前没有可删除的数据。")
            return

        row = self.table.currentRow()
        if row < 0 or row >= len(self.holes_data):
            QMessageBox.information(self, "提示", "请先在表格中选中一行。")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除选中的孔：#{row + 1} 吗？\n（删除后将重新编号）",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 删除数据
        self.holes_data.pop(row)

        # 刷新视图与表格
        self.update_visualization()
        self.update_table()

        # 重新选择一个合理的行
        if self.holes_data:
            new_row = min(row, len(self.holes_data) - 1)
            self.table.setCurrentCell(new_row, 0)
            self.highlight_hole(new_row)
        else:
            self._selected_idx = None

        self.lbl_status.setText(f"已删除 1 行，剩余 {len(self.holes_data)} 个特征")

    # ========== 新增：导出 CSV ==========
    def export_table_csv(self):
        if not self.holes_data:
            QMessageBox.information(self, "提示", "当前没有可导出的数据。")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出表格数据为 CSV",
            "holes.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        try:
            # utf-8-sig 方便 Excel 直接打开不乱码
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(self.columns)

                for i, hole in enumerate(self.holes_data):
                    r = hole["radius"]
                    loc = hole["location"]
                    d = hole["direction"]
                    writer.writerow([
                        f"#{i + 1}",
                        f"{r:.6f}",
                        f"{loc[0]:.6f}", f"{loc[1]:.6f}", f"{loc[2]:.6f}",
                        f"{d[0]:.6f}", f"{d[1]:.6f}", f"{d[2]:.6f}",
                    ])

            self.lbl_status.setText(f"导出成功: {os.path.basename(file_path)}")
            QMessageBox.information(self, "成功", f"已导出 CSV：\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScrewInspectorApp()
    window.show()
    sys.exit(app.exec_())
