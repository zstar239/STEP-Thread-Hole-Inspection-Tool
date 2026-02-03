# STEP 螺纹孔检测工具 (PyQt5 + pythonOCC)

一个基于 **PyQt5** 与 **pythonocc-core（OpenCASCADE）** 的桌面工具，用于加载 CAD 模型并自动识别圆柱螺纹孔（基于圆柱面特征），支持表格/三维联动高亮、误检孔删除、数据导出、模型半透明显示，以及 PyInstaller 打包发布。

---

## ✨ 功能特性

* ✅ 支持加载 **STEP / IGES / STL**

  * **STEP / IGES**：可进行圆柱孔识别（基于 `GeomAbs_Cylinder`）
  * **STL**：可显示模型，但由于是三角网格格式，通常无法提取圆柱孔（结果为 0 属正常现象）
* ✅ 模型 **半透明显示**
* ✅ 自动提取圆柱孔参数：位置 `(X,Y,Z)`、方向 `(DirX,DirY,DirZ)`、半径 `R`
* ✅ 表格选中行 → 3D 视图对应孔/方向线 **高亮联动**
* ✅ 支持删除误检孔（删除选中行，自动重新编号）
* ✅ 支持导出表格数据为 **CSV**
* ✅ 支持 PyInstaller 一键打包（单文件、带图标、无控制台窗口）

---

## 🧩 环境要求

* 操作系统：Windows / Linux
* Python：建议 3.8 ~ 3.11（以 `pythonocc-core` 在你平台的可用版本为准）
* Conda：Miniconda / Anaconda（推荐）

---

## 🚀 安装与运行

### 1) 创建并激活 Conda 环境（推荐）

```bash
conda create -n screw_inspector python=3.10 -y
conda activate screw_inspector
```

### 2) 安装依赖

#### 安装 pythonOCC（必须使用 conda-forge）

```bash
conda install -c conda-forge pythonocc-core
```

#### 安装 PyQt5

```bash
pip install pyQt5
```

> 注：`csv` 等为 Python 标准库，无需额外安装。

### 3) 运行程序

确保仓库根目录包含入口文件（例如 `main.py`）：

```bash
python main.py
```

---

## 📦 打包发布（PyInstaller）

### 1) 安装 PyInstaller

```bash
pip install pyinstaller
```

### 2) 打包命令（单文件 + 图标 + 窗口模式）

在项目根目录执行：

```bash
pyinstaller -F -i .\\logo.ico -w .\\main.py
```

参数说明：

* `-F`：打包为单文件可执行程序
* `-i .\\logo.ico`：指定应用图标（Windows）
* `-w`：窗口模式（不弹出控制台窗口）

打包完成后可执行文件通常位于：

* `dist/main.exe`

---

## 📁 项目结构（示例）

```text
.
├── main.py          # 程序入口
├── logo.ico         # 打包图标（用于 PyInstaller）
├── README.md
└── ...
```

---

## ⚠️ 格式与孔识别说明（重要）

* **STEP / IGES** 是 CAD/B-Rep 格式，保留解析曲面信息（如圆柱面、圆锥面），因此可以通过 `GeomAbs_Cylinder` 识别圆柱孔。
* **STL** 是三角网格格式，只包含三角面片，解析曲面信息丢失，因此通常无法通过“圆柱面类型判断”提取孔特征（显示正常但识别为 0 属正常现象）。
* 如果 **IGES 能显示但识别为 0**：常见原因是 CAD 导出 IGES 时将解析圆柱面转换为 NURBS/BSpline 曲面，从而 `GetType()` 不再是 Cylinder。

---

## 🛠️ 常见问题

### Q1：为什么 STL 可以显示但提取不到孔？

A：STL 是网格模型，缺少 CAD 曲面拓扑信息；当前算法依赖 `GeomAbs_Cylinder`（圆柱面）判断，因此 STL 通常提取结果为 0。

### Q2：IGES 文件无法显示/显示为空怎么办？

A：请确认 IGES 文件本身有效，并尽量使用“保留解析曲面（Analytic Surfaces）”的导出选项；也可尝试先将 IGES 转换为 STEP 再导入。功能开发不完善，很可能识别失败。


## 🙌 致谢

* OpenCASCADE / pythonocc-core
* PyQt5
* PyInstaller
