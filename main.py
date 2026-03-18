import ctypes
import json
import math
import os
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtSvg, QtSvgWidgets, QtWidgets
from NodeGraphQt import BaseNode, NodeGraph, PropertiesBinWidget
from NodeGraphQt.constants import ViewerEnum


def build_interpolated_line_icon(size: int = 256) -> QtGui.QIcon:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)

    bg = QtGui.QLinearGradient(0, 0, 0, size)
    bg.setColorAt(0.0, QtGui.QColor(14, 18, 26, 255))
    bg.setColorAt(1.0, QtGui.QColor(28, 35, 46, 255))
    p.setBrush(QtGui.QBrush(bg))
    p.setPen(QtCore.Qt.NoPen)
    p.drawRoundedRect(QtCore.QRectF(10, 10, size - 20, size - 20), 36, 36)

    grad = QtGui.QLinearGradient(size * 0.2, size * 0.2, size * 0.8, size * 0.8)
    grad.setColorAt(0.0, QtGui.QColor(123, 217, 255))
    grad.setColorAt(0.5, QtGui.QColor(73, 164, 255))
    grad.setColorAt(1.0, QtGui.QColor(40, 102, 246))
    pen = QtGui.QPen(QtGui.QBrush(grad), max(8, int(size * 0.08)))
    pen.setCapStyle(QtCore.Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QtCore.QPointF(size * 0.2, size * 0.2), QtCore.QPointF(size * 0.8, size * 0.8))
    p.end()
    return QtGui.QIcon(pix)


def escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


class BlockField:
    def __init__(self, key: str, label: str, value: str = "") -> None:
        self.key = key
        self.label = label
        self.value = value
        self.value_block_id: Optional[str] = None


class Block:
    title: str = ""
    is_value: bool = False

    def __init__(self) -> None:
        self.fields: List[BlockField] = []

    def emit(self, ctx: "CodeGenContext", indent: int = 0) -> None:
        raise NotImplementedError

    def emit_value(self, ctx: "CodeGenContext") -> str:
        raise NotImplementedError


class CodeGenContext:
    def __init__(self) -> None:
        self.pre_lines: List[str] = []
        self.helper_lines: List[str] = []
        self.main_lines: List[str] = []
        self.after_lines: List[str] = []
        self.post_lines: List[str] = []

        self.window_var: str = "window"
        self.root_var: str = "root"
        self.form_created: bool = False

        self.value_map: Dict[str, str] = {}
        self.declared_vars: set[str] = set()
        self._timer_counter: int = 0

        self._pixel_counter: int = 0
        self._pixel_bitmap_var: Optional[str] = None
        self._pixel_image_var: Optional[str] = None

        self._click_flag_by_control: Dict[str, str] = {}
        self._click_consumer_by_control: Dict[str, str] = {}
        self._set_text_helper_emitted: bool = False
        self._terminal_ready_emitted: bool = False

    def add_pre(self, line: str, indent: int = 0) -> None:
        self.pre_lines.append("        " + "    " * indent + line)

    def add_main(self, line: str, indent: int = 0) -> None:
        self.main_lines.append("        " + "    " * indent + line)

    def add_helper(self, line: str, indent: int = 0) -> None:
        self.helper_lines.append("        " + "    " * indent + line)

    def add_after(self, line: str, indent: int = 0) -> None:
        self.after_lines.append("        " + "    " * indent + line)

    def add_post(self, line: str, indent: int = 0) -> None:
        self.post_lines.append("        " + "    " * indent + line)

    def next_while_name(self) -> str:
        self._timer_counter += 1
        return f"timer{self._timer_counter}"

    def resolve_field(self, fields: List[BlockField], key: str, default: str, quote: bool = False) -> str:
        field = next((f for f in fields if f.key == key), None)
        if field and field.value_block_id and field.value_block_id in self.value_map:
            return self.value_map[field.value_block_id]
        value = field.value if field and str(field.value) != "" else default
        if quote:
            return f"\"{escape(value)}\""
        return str(value)

    def build_code(self) -> str:
        lines: List[str] = []
        lines.append("using System;")
        lines.append("using System.Windows;")
        lines.append("using System.Windows.Controls;")
        lines.append("using System.Windows.Threading;")
        lines.append("using System.Windows.Media;")
        lines.append("using System.Windows.Media.Imaging;")
        lines.append("using System.Windows.Shapes;")
        lines.append("using System.Windows.Input;")
        lines.append("using System.Media;")
        lines.append("using System.Runtime.InteropServices;")
        lines.append("")
        lines.append("namespace GeneratedBlocks;")
        lines.append("")
        lines.append("internal static class Program")
        lines.append("{")
        lines.append('    [DllImport("kernel32.dll")]')
        lines.append("    private static extern bool AllocConsole();")
        lines.append('    [DllImport("kernel32.dll")]')
        lines.append("    private static extern IntPtr GetConsoleWindow();")
        lines.append("")
        lines.append("    [STAThread]")
        lines.append("    private static void Main()")
        lines.append("    {")
        lines.append("        var app = new Application();")
        lines.append("")

        if not self.form_created:
            lines.append("        var window = new Window();")
            lines.append("        window.Title = \"Hello from Blocks\";")
            lines.append("        window.Width = 1;")
            lines.append("        window.Height = 1;")
            lines.append("        window.WindowStyle = WindowStyle.None;")
            lines.append("        window.AllowsTransparency = true;")
            lines.append("        window.Opacity = 0;")
            lines.append("        window.ShowInTaskbar = false;")
            lines.append("        window.ShowActivated = false;")
            lines.append("        var root = new Canvas();")
            lines.append("        window.Content = root;")
            lines.append("")
            self.window_var = "window"
            self.root_var = "root"

        lines.extend(self.pre_lines)
        lines.extend(self.helper_lines)
        lines.extend(self.main_lines)
        lines.extend(self.after_lines)

        if not self.form_created and self.post_lines:
            lines.append("")
            lines.append("        window.Loaded += (_, __) =>")
            lines.append("        {")
            lines.extend([line.replace("        ", "            ", 1) for line in self.post_lines])
            lines.append("        };")

        lines.append("")
        lines.append(f"        app.Run({self.window_var});")
        lines.append("    }")
        lines.append("}")
        return "\n".join(lines)

    def ensure_pixel_surface(self, width_expr: str, height_expr: str) -> Tuple[str, str]:
        """
        Ensure a WriteableBitmap + Image exist and are added to the root canvas.
        Returns (bitmap_var, image_var).
        """
        if self._pixel_bitmap_var and self._pixel_image_var:
            return self._pixel_bitmap_var, self._pixel_image_var

        self._pixel_counter += 1
        bmp_var = f"pixelBmp{self._pixel_counter}"
        img_var = f"pixelImg{self._pixel_counter}"
        self._pixel_bitmap_var = bmp_var
        self._pixel_image_var = img_var

        self.add_main(
            f"var {bmp_var} = new WriteableBitmap({width_expr}, {height_expr}, 96, 96, PixelFormats.Bgra32, null);"
        )
        self.add_main(f"var {img_var} = new Image();")
        self.add_main(f"{img_var}.Source = {bmp_var};")
        self.add_main(f"{img_var}.Width = {width_expr};")
        self.add_main(f"{img_var}.Height = {height_expr};")
        self.add_main(f"Canvas.SetLeft({img_var}, 0);")
        self.add_main(f"Canvas.SetTop({img_var}, 0);")
        self.add_main(f"{self.root_var}.Children.Add({img_var});")
        return bmp_var, img_var

    def click_flag_for(self, control_name: str) -> str:
        if control_name in self._click_flag_by_control:
            return self._click_flag_by_control[control_name]
        flag = f"{control_name}_clicked"
        self._click_flag_by_control[control_name] = flag
        if flag not in self.declared_vars:
            self.add_pre(f"bool {flag} = false;")
            self.declared_vars.add(flag)
        return flag

    def ensure_click_consumer(self, control_name: str) -> str:
        """
        Emit a helper local function that consumes a click flag (return + reset).
        """
        if control_name in self._click_consumer_by_control:
            return self._click_consumer_by_control[control_name]

        flag = self.click_flag_for(control_name)
        func = f"ConsumeClick_{control_name}"
        self._click_consumer_by_control[control_name] = func

        self.add_helper(f"bool {func}()")
        self.add_helper("{")
        self.add_helper(f"    var v = {flag};")
        self.add_helper(f"    {flag} = false;")
        self.add_helper("    return v;")
        self.add_helper("}")
        return func

    def ensure_set_text_helper(self) -> str:
        """
        Emit a local helper to set text on either TextBox or ContentControl without
        causing compile-time pattern matching errors (when the variable is statically typed).
        """
        if self._set_text_helper_emitted:
            return "SetText"
        self._set_text_helper_emitted = True
        self.add_helper("void SetText(object ctrl, object value)")
        self.add_helper("{")
        self.add_helper("    if (ctrl is TextBox tb)")
        self.add_helper("    {")
        self.add_helper("        tb.Text = value?.ToString() ?? string.Empty;")
        self.add_helper("        return;")
        self.add_helper("    }")
        self.add_helper("    if (ctrl is ContentControl cc)")
        self.add_helper("    {")
        self.add_helper("        cc.Content = value;")
        self.add_helper("    }")
        self.add_helper("}")
        return "SetText"

    def ensure_terminal(self) -> None:
        if self._terminal_ready_emitted:
            return
        self._terminal_ready_emitted = True
        self.add_main("if (GetConsoleWindow() == IntPtr.Zero) AllocConsole();")


class CreateFormBlock(Block):
    title = "Create Form"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("formVar", "Window Variable", "window"),
            BlockField("formName", "Window Name", "MainWindow"),
            BlockField("caption", "Caption", "Hello from Blocks"),
            BlockField("width", "Width", "900"),
            BlockField("height", "Height", "600"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        form_var = ctx.resolve_field(self.fields, "formVar", "window")
        form_name = ctx.resolve_field(self.fields, "formName", "MainWindow", quote=True)
        caption = ctx.resolve_field(self.fields, "caption", "Hello from Blocks", quote=True)
        width = ctx.resolve_field(self.fields, "width", "900")
        height = ctx.resolve_field(self.fields, "height", "600")

        ctx.window_var = form_var
        ctx.form_created = True
        ctx.root_var = f"{form_var}Root"
        ctx.add_main(f"var {form_var} = new Window();", indent)
        ctx.add_main(f"{form_var}.Name = {form_name};", indent)
        ctx.add_main(f"{form_var}.Title = {caption};", indent)
        ctx.add_main(f"{form_var}.Width = {width};", indent)
        ctx.add_main(f"{form_var}.Height = {height};", indent)
        ctx.add_main(f"var {ctx.root_var} = new Canvas();", indent)
        ctx.add_main(f"{form_var}.Content = {ctx.root_var};", indent)


class ShowMessageBlock(Block):
    title = "Show Message"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("title", "Title", "Info"),
            BlockField("message", "Message", "Hello"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        title = ctx.resolve_field(self.fields, "title", "Info", quote=True)
        msg = ctx.resolve_field(self.fields, "message", "Hello", quote=True)
        ctx.add_main(f"MessageBox.Show({msg}, {title});", indent)


class BoolVarBlock(Block):
    title = "Bool Variable"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("name", "Name", "isReady"),
            BlockField("value", "Value", "false"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        # emitted by hoisting in generator
        return


class StringVarBlock(Block):
    title = "String Variable"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("name", "Name", "textValue"),
            BlockField("value", "Value", "hello"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class NumberVarBlock(Block):
    title = "Number Variable"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("name", "Name", "count"),
            BlockField("value", "Value", "0"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class BoolLiteralBlock(Block):
    title = "Bool Literal"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("value", "Value", "true")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        v = ctx.resolve_field(self.fields, "value", "true").strip().lower()
        return "true" if v in ("1", "true", "yes", "y") else "false"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class NumberLiteralBlock(Block):
    title = "Number Literal"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("value", "Value", "0")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        return ctx.resolve_field(self.fields, "value", "0")

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class StringLiteralBlock(Block):
    title = "String Literal"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("value", "Value", "text")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        return ctx.resolve_field(self.fields, "value", "", quote=True)

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class AddBlock(Block):
    title = "Add"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("a", "A", "0"), BlockField("b", "B", "0")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        a = ctx.resolve_field(self.fields, "a", "0")
        b = ctx.resolve_field(self.fields, "b", "0")
        return f"({a} + {b})"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class SubtractBlock(Block):
    title = "Subtract"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("a", "A", "0"), BlockField("b", "B", "0")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        a = ctx.resolve_field(self.fields, "a", "0")
        b = ctx.resolve_field(self.fields, "b", "0")
        return f"({a} - {b})"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class EqualsBlock(Block):
    title = "Equals"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("a", "A", ""), BlockField("b", "B", "")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        a = ctx.resolve_field(self.fields, "a", "null")
        b = ctx.resolve_field(self.fields, "b", "null")
        return f"({a} == {b})"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class RandomBlock(Block):
    title = "Random"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("from", "From", "0"), BlockField("to", "To", "10")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        a = ctx.resolve_field(self.fields, "from", "0")
        b = ctx.resolve_field(self.fields, "to", "10")
        return f"(new Random().NextDouble() * ({b} - {a}) + {a})"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class IfElseBlock(Block):
    title = "If / Else"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("condition", "Condition", "true")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        # handled in graph chain emitter
        return


class WhileBlock(Block):
    title = "While"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("condition", "Condition", "true")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class ForRangeBlock(Block):
    title = "For Range"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("var", "Var", "i"),
            BlockField("start", "Start", "0"),
            BlockField("end", "End", "10"),
            BlockField("step", "Step", "1"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class DelayBlock(Block):
    title = "Delay"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("interval", "Interval(ms)", "500")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class AddButtonBlock(Block):
    title = "Add Button"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("controlName", "Button Name", "button1"),
            BlockField("text", "Text", "Click me"),
            BlockField("x", "X", "30"),
            BlockField("y", "Y", "30"),
            BlockField("width", "Width", "120"),
            BlockField("height", "Height", "40"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "controlName", "button1")
        text = ctx.resolve_field(self.fields, "text", "Click me", quote=True)
        x = ctx.resolve_field(self.fields, "x", "30")
        y = ctx.resolve_field(self.fields, "y", "30")
        width = ctx.resolve_field(self.fields, "width", "120")
        height = ctx.resolve_field(self.fields, "height", "40")

        ctx.add_main(f"var {name} = new Button();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Content = {text};", indent)
        ctx.add_main(f"{name}.Width = {width};", indent)
        ctx.add_main(f"{name}.Height = {height};", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)


class AddLabelBlock(Block):
    title = "Add Label"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("controlName", "Label Name", "label1"),
            BlockField("text", "Text", "Label"),
            BlockField("x", "X", "30"),
            BlockField("y", "Y", "80"),
            BlockField("width", "Width", "160"),
            BlockField("height", "Height", "24"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "controlName", "label1")
        text = ctx.resolve_field(self.fields, "text", "Label", quote=True)
        x = ctx.resolve_field(self.fields, "x", "30")
        y = ctx.resolve_field(self.fields, "y", "80")
        width = ctx.resolve_field(self.fields, "width", "160")
        height = ctx.resolve_field(self.fields, "height", "24")

        ctx.add_main(f"var {name} = new Label();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Content = {text};", indent)
        ctx.add_main(f"{name}.Width = {width};", indent)
        ctx.add_main(f"{name}.Height = {height};", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)


class AddTextBoxBlock(Block):
    title = "Add TextBox"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("controlName", "TextBox Name", "textBox1"),
            BlockField("text", "Text", ""),
            BlockField("x", "X", "30"),
            BlockField("y", "Y", "120"),
            BlockField("width", "Width", "200"),
            BlockField("height", "Height", "28"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "controlName", "textBox1")
        text = ctx.resolve_field(self.fields, "text", "", quote=True)
        x = ctx.resolve_field(self.fields, "x", "30")
        y = ctx.resolve_field(self.fields, "y", "120")
        width = ctx.resolve_field(self.fields, "width", "200")
        height = ctx.resolve_field(self.fields, "height", "28")

        ctx.add_main(f"var {name} = new TextBox();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Text = {text};", indent)
        ctx.add_main(f"{name}.Width = {width};", indent)
        ctx.add_main(f"{name}.Height = {height};", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)


class AddCheckBoxBlock(Block):
    title = "Add CheckBox"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("controlName", "CheckBox Name", "checkBox1"),
            BlockField("text", "Text", "Check me"),
            BlockField("checked", "Checked", "false"),
            BlockField("x", "X", "30"),
            BlockField("y", "Y", "160"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "controlName", "checkBox1")
        text = ctx.resolve_field(self.fields, "text", "Check me", quote=True)
        checked = ctx.resolve_field(self.fields, "checked", "false")
        x = ctx.resolve_field(self.fields, "x", "30")
        y = ctx.resolve_field(self.fields, "y", "160")

        ctx.add_main(f"var {name} = new CheckBox();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Content = {text};", indent)
        ctx.add_main(f"{name}.IsChecked = {checked};", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)


class AddSliderBlock(Block):
    title = "Add Slider"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("controlName", "Slider Name", "slider1"),
            BlockField("min", "Min", "0"),
            BlockField("max", "Max", "100"),
            BlockField("value", "Value", "50"),
            BlockField("x", "X", "30"),
            BlockField("y", "Y", "200"),
            BlockField("width", "Width", "220"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "controlName", "slider1")
        min_v = ctx.resolve_field(self.fields, "min", "0")
        max_v = ctx.resolve_field(self.fields, "max", "100")
        value = ctx.resolve_field(self.fields, "value", "50")
        x = ctx.resolve_field(self.fields, "x", "30")
        y = ctx.resolve_field(self.fields, "y", "200")
        width = ctx.resolve_field(self.fields, "width", "220")

        ctx.add_main(f"var {name} = new Slider();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Minimum = {min_v};", indent)
        ctx.add_main(f"{name}.Maximum = {max_v};", indent)
        ctx.add_main(f"{name}.Value = {value};", indent)
        ctx.add_main(f"{name}.Width = {width};", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)


class AddProgressBarBlock(Block):
    title = "Add ProgressBar"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("controlName", "ProgressBar Name", "progressBar1"),
            BlockField("min", "Min", "0"),
            BlockField("max", "Max", "100"),
            BlockField("value", "Value", "25"),
            BlockField("x", "X", "30"),
            BlockField("y", "Y", "240"),
            BlockField("width", "Width", "220"),
            BlockField("height", "Height", "22"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "controlName", "progressBar1")
        min_v = ctx.resolve_field(self.fields, "min", "0")
        max_v = ctx.resolve_field(self.fields, "max", "100")
        value = ctx.resolve_field(self.fields, "value", "25")
        x = ctx.resolve_field(self.fields, "x", "30")
        y = ctx.resolve_field(self.fields, "y", "240")
        width = ctx.resolve_field(self.fields, "width", "220")
        height = ctx.resolve_field(self.fields, "height", "22")

        ctx.add_main(f"var {name} = new ProgressBar();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Minimum = {min_v};", indent)
        ctx.add_main(f"{name}.Maximum = {max_v};", indent)
        ctx.add_main(f"{name}.Value = {value};", indent)
        ctx.add_main(f"{name}.Width = {width};", indent)
        ctx.add_main(f"{name}.Height = {height};", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)


class AddImageBlock(Block):
    title = "Add Image"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("controlName", "Image Name", "image1"),
            BlockField("path", "Path", ""),
            BlockField("x", "X", "300"),
            BlockField("y", "Y", "30"),
            BlockField("width", "Width", "200"),
            BlockField("height", "Height", "200"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "controlName", "image1")
        path = ctx.resolve_field(self.fields, "path", "", quote=True)
        x = ctx.resolve_field(self.fields, "x", "300")
        y = ctx.resolve_field(self.fields, "y", "30")
        width = ctx.resolve_field(self.fields, "width", "200")
        height = ctx.resolve_field(self.fields, "height", "200")

        ctx.add_main(f"var {name} = new Image();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Width = {width};", indent)
        ctx.add_main(f"{name}.Height = {height};", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)
        ctx.add_main(
            f"if (!string.IsNullOrWhiteSpace({path})) {{ {name}.Source = new BitmapImage(new Uri({path}, UriKind.RelativeOrAbsolute)); }}",
            indent,
        )


class AddRectangleBlock(Block):
    title = "Add Rectangle"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("shapeName", "Rectangle Name", "rect1"),
            BlockField("x", "X", "300"),
            BlockField("y", "Y", "260"),
            BlockField("width", "Width", "120"),
            BlockField("height", "Height", "80"),
            BlockField("fill", "Fill", "#FF007ACC"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "shapeName", "rect1")
        x = ctx.resolve_field(self.fields, "x", "300")
        y = ctx.resolve_field(self.fields, "y", "260")
        width = ctx.resolve_field(self.fields, "width", "120")
        height = ctx.resolve_field(self.fields, "height", "80")
        fill = ctx.resolve_field(self.fields, "fill", "#FF007ACC", quote=True)

        ctx.add_main(f"var {name} = new Rectangle();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Width = {width};", indent)
        ctx.add_main(f"{name}.Height = {height};", indent)
        ctx.add_main(f"{name}.Fill = (Brush)new BrushConverter().ConvertFromString({fill});", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)


class AddEllipseBlock(Block):
    title = "Add Ellipse"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("shapeName", "Ellipse Name", "ellipse1"),
            BlockField("x", "X", "450"),
            BlockField("y", "Y", "260"),
            BlockField("width", "Width", "100"),
            BlockField("height", "Height", "100"),
            BlockField("fill", "Fill", "#FFFFC107"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "shapeName", "ellipse1")
        x = ctx.resolve_field(self.fields, "x", "450")
        y = ctx.resolve_field(self.fields, "y", "260")
        width = ctx.resolve_field(self.fields, "width", "100")
        height = ctx.resolve_field(self.fields, "height", "100")
        fill = ctx.resolve_field(self.fields, "fill", "#FFFFC107", quote=True)

        ctx.add_main(f"var {name} = new Ellipse();", indent)
        ctx.add_main(f"{name}.Name = \"{escape(name)}\";", indent)
        ctx.add_main(f"{name}.Width = {width};", indent)
        ctx.add_main(f"{name}.Height = {height};", indent)
        ctx.add_main(f"{name}.Fill = (Brush)new BrushConverter().ConvertFromString({fill});", indent)
        ctx.add_main(f"Canvas.SetLeft({name}, {x});", indent)
        ctx.add_main(f"Canvas.SetTop({name}, {y});", indent)
        ctx.add_main(f"{ctx.root_var}.Children.Add({name});", indent)


class DrawPixelBlock(Block):
    title = "Draw Pixel"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("x", "X", "0"),
            BlockField("y", "Y", "0"),
            BlockField("color", "Color", "#FFFFFFFF"),
            BlockField("surfaceWidth", "Surface Width", "256"),
            BlockField("surfaceHeight", "Surface Height", "256"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        x = ctx.resolve_field(self.fields, "x", "0")
        y = ctx.resolve_field(self.fields, "y", "0")
        color = ctx.resolve_field(self.fields, "color", "#FFFFFFFF", quote=True)
        w = ctx.resolve_field(self.fields, "surfaceWidth", "256")
        h = ctx.resolve_field(self.fields, "surfaceHeight", "256")

        bmp_var, _img_var = ctx.ensure_pixel_surface(w, h)
        ctx.add_main(f"var __c = (Color)ColorConverter.ConvertFromString({color});", indent)
        ctx.add_main("var __px = new byte[] { __c.B, __c.G, __c.R, __c.A };", indent)
        ctx.add_main(f"{bmp_var}.WritePixels(new Int32Rect((int){x}, (int){y}, 1, 1), __px, 4, 0);", indent)


class SetTextBlock(Block):
    title = "Set Text"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("controlName", "Control Name", "label1"),
            BlockField("text", "Text", "Hello"),
        ]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "controlName", "label1")
        value = ctx.resolve_field(self.fields, "text", "Hello", quote=True)
        helper = ctx.ensure_set_text_helper()
        ctx.add_main(f"{helper}({name}, {value});", indent)


class SetButtonTextBlock(Block):
    title = "Set Button Text"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("button", "Button", "button1"), BlockField("text", "Text", "Click")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        btn = ctx.resolve_field(self.fields, "button", "button1")
        text = ctx.resolve_field(self.fields, "text", "Click", quote=True)
        ctx.add_main(f"{btn}.Content = {text};", indent)


class SetLabelTextBlock(Block):
    title = "Set Label Text"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("label", "Label", "label1"), BlockField("text", "Text", "Label")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        lbl = ctx.resolve_field(self.fields, "label", "label1")
        text = ctx.resolve_field(self.fields, "text", "Label", quote=True)
        ctx.add_main(f"{lbl}.Content = {text};", indent)


class SetWindowTitleBlock(Block):
    title = "Set Window Title"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("title", "Title", "My App")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        title = ctx.resolve_field(self.fields, "title", "My App", quote=True)
        ctx.add_main(f"{ctx.window_var}.Title = {title};", indent)


class SetTextBoxTextBlock(Block):
    title = "Set TextBox Text"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("textbox", "TextBox", "textBox1"), BlockField("text", "Text", "Hello")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        tb = ctx.resolve_field(self.fields, "textbox", "textBox1")
        text = ctx.resolve_field(self.fields, "text", "Hello", quote=True)
        ctx.add_main(f"{tb}.Text = {text};", indent)


class SetCheckedBlock(Block):
    title = "Set Checked"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("checkbox", "CheckBox", "checkBox1"), BlockField("value", "Value", "true")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        cb = ctx.resolve_field(self.fields, "checkbox", "checkBox1")
        v = ctx.resolve_field(self.fields, "value", "true")
        ctx.add_main(f"{cb}.IsChecked = {v};", indent)


class SetSliderValueBlock(Block):
    title = "Set Slider Value"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("slider", "Slider", "slider1"), BlockField("value", "Value", "50")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        sl = ctx.resolve_field(self.fields, "slider", "slider1")
        v = ctx.resolve_field(self.fields, "value", "50")
        ctx.add_main(f"{sl}.Value = {v};", indent)


class SetProgressBarValueBlock(Block):
    title = "Set ProgressBar Value"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("progressBar", "ProgressBar", "progressBar1"), BlockField("value", "Value", "50")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        pb = ctx.resolve_field(self.fields, "progressBar", "progressBar1")
        v = ctx.resolve_field(self.fields, "value", "50")
        ctx.add_main(f"{pb}.Value = {v};", indent)


class SetImageSourceBlock(Block):
    title = "Set Image Source"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("image", "Image", "image1"), BlockField("path", "Path", "")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        img = ctx.resolve_field(self.fields, "image", "image1")
        path = ctx.resolve_field(self.fields, "path", "", quote=True)
        ctx.add_main(
            f"if (!string.IsNullOrWhiteSpace({path})) {{ {img}.Source = new BitmapImage(new Uri({path}, UriKind.RelativeOrAbsolute)); }}",
            indent,
        )


class SetBackgroundBlock(Block):
    title = "Set Background"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("color", "Color", "#FF202020")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        c = ctx.resolve_field(self.fields, "color", "#FF202020", quote=True)
        ctx.add_main(f"{ctx.window_var}.Background = (Brush)new BrushConverter().ConvertFromString({c});", indent)


class SetShapeFillBlock(Block):
    title = "Set Shape Fill"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("shape", "Shape", "rect1"), BlockField("fill", "Fill", "#FFFFFFFF")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        sh = ctx.resolve_field(self.fields, "shape", "rect1")
        fill = ctx.resolve_field(self.fields, "fill", "#FFFFFFFF", quote=True)
        ctx.add_main(f"{sh}.Fill = (Brush)new BrushConverter().ConvertFromString({fill});", indent)


class ClearFormBlock(Block):
    title = "Clear Form"

    def __init__(self) -> None:
        super().__init__()
        self.fields = []

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        ctx.add_main(f"{ctx.root_var}.Children.Clear();", indent)


class PlaySoundBlock(Block):
    title = "Play Sound"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("sound", "Sound", "Asterisk")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        s = ctx.resolve_field(self.fields, "sound", "Asterisk")
        mapping = {
            "Asterisk": "SystemSounds.Asterisk.Play();",
            "Beep": "SystemSounds.Beep.Play();",
            "Exclamation": "SystemSounds.Exclamation.Play();",
            "Hand": "SystemSounds.Hand.Play();",
            "Question": "SystemSounds.Question.Play();",
        }
        ctx.add_main(mapping.get(s, "SystemSounds.Asterisk.Play();"), indent)


class PrintBlock(Block):
    title = "Print"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("value", "Value", "text")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        value = ctx.resolve_field(self.fields, "value", "text", quote=True)
        ctx.ensure_terminal()
        ctx.add_main(f"Console.Write({value});", indent)


class PrintLnBlock(Block):
    title = "PrintLn"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("value", "Value", "text")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        value = ctx.resolve_field(self.fields, "value", "text", quote=True)
        ctx.ensure_terminal()
        ctx.add_main(f"Console.WriteLine({value});", indent)


class ClearTerminalBlock(Block):
    title = "Clear Terminal"

    def __init__(self) -> None:
        super().__init__()
        self.fields = []

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        ctx.ensure_terminal()
        ctx.add_main("Console.Clear();", indent)


class OnClickBlock(Block):
    title = "On Click"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("button", "Button", "button1")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class SetBoolBlock(Block):
    title = "Set Bool"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("name", "Name", "isReady"), BlockField("value", "Value", "true")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "name", "isReady")
        value = ctx.resolve_field(self.fields, "value", "true")
        ctx.add_main(f"{name} = {value};", indent)


class SetStringBlock(Block):
    title = "Set String"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("name", "Name", "textValue"), BlockField("value", "Value", "hello")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "name", "textValue")
        value = ctx.resolve_field(self.fields, "value", "hello", quote=True)
        ctx.add_main(f"{name} = {value};", indent)


class SetNumberBlock(Block):
    title = "Set Number"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("name", "Name", "count"), BlockField("value", "Value", "0")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "name", "count")
        value = ctx.resolve_field(self.fields, "value", "0")
        ctx.add_main(f"{name} = {value};", indent)


class ChangeByBlock(Block):
    title = "Change By"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("name", "Name", "count"), BlockField("delta", "Delta", "1")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "name", "count")
        delta = ctx.resolve_field(self.fields, "delta", "1")
        ctx.add_main(f"{name} += {delta};", indent)


class AddNumberBlock(Block):
    title = "Add Number"

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("name", "Name", "count"), BlockField("value", "Value", "1")]

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        name = ctx.resolve_field(self.fields, "name", "count")
        value = ctx.resolve_field(self.fields, "value", "1")
        ctx.add_main(f"{name} = {name} + {value};", indent)


class JoinBlock(Block):
    title = "Join"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [
            BlockField("a", "A", ""),
            BlockField("b", "B", ""),
            BlockField("c", "C", ""),
            BlockField("d", "D", ""),
        ]

    def emit_value(self, ctx: CodeGenContext) -> str:
        a = ctx.resolve_field(self.fields, "a", "", quote=True)
        b = ctx.resolve_field(self.fields, "b", "", quote=True)
        c = ctx.resolve_field(self.fields, "c", "", quote=True)
        d = ctx.resolve_field(self.fields, "d", "", quote=True)
        return f"string.Concat({a}, {b}, {c}, {d})"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class GetTextBoxTextBlock(Block):
    title = "Get TextBox Text"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("textbox", "TextBox", "textBox1")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        tb = ctx.resolve_field(self.fields, "textbox", "textBox1")
        return f"{tb}.Text"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class IsCheckedBlock(Block):
    title = "Is Checked"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("checkbox", "CheckBox", "checkBox1")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        cb = ctx.resolve_field(self.fields, "checkbox", "checkBox1")
        return f"({cb}.IsChecked == true)"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class GetSliderValueBlock(Block):
    title = "Get Slider Value"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("slider", "Slider", "slider1")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        sl = ctx.resolve_field(self.fields, "slider", "slider1")
        return f"{sl}.Value"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class ReadProgressBarValueBlock(Block):
    title = "Read ProgressBar Value"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("progressBar", "ProgressBar", "progressBar1")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        pb = ctx.resolve_field(self.fields, "progressBar", "progressBar1")
        return f"{pb}.Value"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class MouseXBlock(Block):
    title = "Mouse X"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = []

    def emit_value(self, ctx: CodeGenContext) -> str:
        return f"Mouse.GetPosition({ctx.window_var}).X"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class MouseYBlock(Block):
    title = "Mouse Y"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = []

    def emit_value(self, ctx: CodeGenContext) -> str:
        return f"Mouse.GetPosition({ctx.window_var}).Y"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class BoolVarRefBlock(Block):
    title = "Bool Var"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("name", "Name", "isReady")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        return ctx.resolve_field(self.fields, "name", "isReady")

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class StringVarRefBlock(Block):
    title = "String Var"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("name", "Name", "textValue")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        return ctx.resolve_field(self.fields, "name", "textValue")

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class NumberVarRefBlock(Block):
    title = "Number Var"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("name", "Name", "count")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        return ctx.resolve_field(self.fields, "name", "count")

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


class IsClickedValueBlock(Block):
    title = "Is Clicked"
    is_value = True

    def __init__(self) -> None:
        super().__init__()
        self.fields = [BlockField("button", "Button", "button1")]

    def emit_value(self, ctx: CodeGenContext) -> str:
        btn = ctx.resolve_field(self.fields, "button", "button1")
        func = ctx.ensure_click_consumer(btn)
        return f"{func}()"

    def emit(self, ctx: CodeGenContext, indent: int = 0) -> None:
        return


BLOCKS: Dict[str, type] = {
    "Create Form": CreateFormBlock,
    "Add Button": AddButtonBlock,
    "Add Label": AddLabelBlock,
    "Add TextBox": AddTextBoxBlock,
    "Add CheckBox": AddCheckBoxBlock,
    "Add Slider": AddSliderBlock,
    "Add ProgressBar": AddProgressBarBlock,
    "Add Image": AddImageBlock,
    "Add Rectangle": AddRectangleBlock,
    "Add Ellipse": AddEllipseBlock,
    "Draw Pixel": DrawPixelBlock,
    "Set Text": SetTextBlock,
    "Set Button Text": SetButtonTextBlock,
    "Set Label Text": SetLabelTextBlock,
    "Set Window Title": SetWindowTitleBlock,
    "Set TextBox Text": SetTextBoxTextBlock,
    "Set Checked": SetCheckedBlock,
    "Set Slider Value": SetSliderValueBlock,
    "Set ProgressBar Value": SetProgressBarValueBlock,
    "Set Image Source": SetImageSourceBlock,
    "Set Background": SetBackgroundBlock,
    "Set Shape Fill": SetShapeFillBlock,
    "Clear Form": ClearFormBlock,
    "Show Message": ShowMessageBlock,
    "Play Sound": PlaySoundBlock,
    "Print": PrintBlock,
    "PrintLn": PrintLnBlock,
    "Clear Terminal": ClearTerminalBlock,
    "On Click": OnClickBlock,
    "If / Else": IfElseBlock,
    "While": WhileBlock,
    "For Range": ForRangeBlock,
    "Delay": DelayBlock,
    "Bool Variable": BoolVarBlock,
    "String Variable": StringVarBlock,
    "Number Variable": NumberVarBlock,
    "Set Bool": SetBoolBlock,
    "Set String": SetStringBlock,
    "Set Number": SetNumberBlock,
    "Change By": ChangeByBlock,
    "Add Number": AddNumberBlock,
    "Bool Literal": BoolLiteralBlock,
    "Number Literal": NumberLiteralBlock,
    "String Literal": StringLiteralBlock,
    "Add": AddBlock,
    "Subtract": SubtractBlock,
    "Equals": EqualsBlock,
    "Random": RandomBlock,
    "Join": JoinBlock,
    "Get TextBox Text": GetTextBoxTextBlock,
    "Is Checked": IsCheckedBlock,
    "Get Slider Value": GetSliderValueBlock,
    "Read ProgressBar Value": ReadProgressBarValueBlock,
    "Mouse X": MouseXBlock,
    "Mouse Y": MouseYBlock,
    "Bool Var": BoolVarRefBlock,
    "String Var": StringVarRefBlock,
    "Number Var": NumberVarRefBlock,
    "Is Clicked": IsClickedValueBlock,
}


def flow_outputs_for(title: str) -> List[str]:
    if title == "If / Else":
        return ["true", "false"]
    if title in ("While", "For Range"):
        return ["loop", "next"]
    return ["next"]


def make_node_class(title: str, block_cls: type) -> type:
    class DynamicNode(BaseNode):
        __identifier__ = "blocks"
        NODE_NAME = title

        def __init__(self):
            super().__init__()
            block = block_cls()

            if not getattr(block, "is_value", False):
                self.add_input("in")
                for out_name in flow_outputs_for(title):
                    self.add_output(out_name)
            else:
                self.add_output("value")

            for field in block.fields:
                self.add_input(f"val_{field.key}")
                self.add_text_input(f"p_{field.key}", field.label, text=field.value)

            self.set_color(60, 60, 60)

    DynamicNode.__name__ = f"{title.replace(' ', '').replace('/', '').replace('-', '')}Node"
    return DynamicNode


@dataclass
class _BlockItem:
    id: str
    block: object
    y: float


def block_category(title: str) -> str:
    if title in (
        "Add",
        "Subtract",
        "Equals",
        "Random",
        "Number Literal",
        "Add Number",
        "Change By",
    ):
        return "Math"
    if title in ("If / Else", "While", "For Range", "Delay"):
        return "Control"
    if title in (
        "Create Form",
        "Add Button",
        "Add Label",
        "Add TextBox",
        "Add CheckBox",
        "Add Slider",
        "Add ProgressBar",
        "Add Image",
        "Add Rectangle",
        "Add Ellipse",
        "Draw Pixel",
        "Set Text",
        "Set Button Text",
        "Set Label Text",
        "Set Window Title",
        "Set TextBox Text",
        "Set Checked",
        "Set Slider Value",
        "Set ProgressBar Value",
        "Set Image Source",
        "Set Background",
        "Set Shape Fill",
        "Clear Form",
        "Show Message",
    ):
        return "UI"
    if title in (
        "Bool Variable",
        "String Variable",
        "Number Variable",
        "Set Bool",
        "Set String",
        "Set Number",
        "Bool Var",
        "String Var",
        "Number Var",
    ):
        return "Variables"
    if title in ("String Literal", "Join", "Get TextBox Text"):
        return "Text"
    if title in (
        "Is Checked",
        "Get Slider Value",
        "Read ProgressBar Value",
        "Mouse X",
        "Mouse Y",
        "On Click",
        "Is Clicked",
    ):
        return "Input"
    if title in ("Play Sound",):
        return "Sound"
    if title in ("Print", "PrintLn", "Clear Terminal"):
        return "Terminal"
    return "Other"


class BlockPaletteWidget(QtWidgets.QWidget):
    def __init__(self, titles: List[str], create_node_cb):
        super().__init__()
        self._create_node_cb = create_node_cb
        self._titles = sorted(titles, key=str.lower)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search blocks...")
        layout.addWidget(self.search)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._lists: Dict[str, QtWidgets.QListWidget] = {}
        cats = ["All", "UI", "Control", "Math", "Variables", "Text", "Input", "Sound", "Terminal", "Other"]
        for cat in cats:
            lw = _PaletteListWidget()
            lw.setUniformItemSizes(True)
            lw.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            lw.itemDoubleClicked.connect(self._on_item_double_clicked)
            self._lists[cat] = lw
            self.tabs.addTab(lw, cat)

        self._populate()
        self.search.textChanged.connect(self._apply_filter)

    def _populate(self) -> None:
        for lw in self._lists.values():
            lw.clear()

        for title in self._titles:
            cat = block_category(title)
            item = QtWidgets.QListWidgetItem(title)
            item.setData(QtCore.Qt.UserRole, title)
            self._lists["All"].addItem(QtWidgets.QListWidgetItem(item))
            if cat in self._lists:
                self._lists[cat].addItem(QtWidgets.QListWidgetItem(item))
            else:
                self._lists["Other"].addItem(QtWidgets.QListWidgetItem(item))

        for lw in self._lists.values():
            lw.sortItems()

    def _apply_filter(self, text: str) -> None:
        q = text.strip().lower()
        for lw in self._lists.values():
            for i in range(lw.count()):
                it = lw.item(i)
                t = (it.data(QtCore.Qt.UserRole) or it.text()).lower()
                it.setHidden(bool(q) and q not in t)

    def _on_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        title = item.data(QtCore.Qt.UserRole) or item.text()
        self._create_node_cb(str(title))


class _PaletteListWidget(QtWidgets.QListWidget):
    """
    Simple drag source that carries the block title as text.
    """

    MIME = "application/x-block-title"

    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self.setDefaultDropAction(QtCore.Qt.CopyAction)

    def startDrag(self, supportedActions):  # noqa: N802 (Qt API)
        item = self.currentItem()
        if not item:
            return
        title = item.data(QtCore.Qt.UserRole) or item.text()
        if not title:
            return

        mime = QtCore.QMimeData()
        mime.setData(self.MIME, str(title).encode("utf-8"))
        mime.setText(str(title))

        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._drag_pixmap(str(title)))
        drag.setHotSpot(QtCore.QPoint(12, 12))
        drag.exec_(QtCore.Qt.CopyAction)

    def _drag_pixmap(self, title: str) -> QtGui.QPixmap:
        font = QtGui.QFont(self.font())
        font.setBold(True)
        metrics = QtGui.QFontMetrics(font)
        pad_x = 16
        pad_y = 10
        w = metrics.horizontalAdvance(title) + pad_x * 2
        h = metrics.height() + pad_y * 2

        pm = QtGui.QPixmap(max(1, w), max(1, h))
        pm.fill(QtCore.Qt.transparent)

        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        rect = QtCore.QRectF(0, 0, pm.width(), pm.height())
        bg = QtGui.QColor(40, 40, 40, 180)  # semi-transparent
        border = QtGui.QColor(200, 200, 200, 130)
        p.setBrush(bg)
        p.setPen(QtGui.QPen(border, 1.0))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

        p.setFont(font)
        p.setPen(QtGui.QColor(240, 240, 240, 220))
        p.drawText(QtCore.QRectF(pad_x, pad_y, pm.width() - pad_x * 2, pm.height() - pad_y * 2), title)
        p.end()

        return pm


def check_dotnet_sdk() -> bool:
    try:
        check = subprocess.run(
            ["dotnet", "--list-sdks"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
        )
    except Exception:
        return False
    if check.returncode != 0:
        return False
    return bool((check.stdout or "").strip())


def _state_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    path = base / "DotNetBlocksEditor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _restart_marker_path() -> Path:
    return _state_dir() / "restart_required.json"


def _current_boot_id() -> str:
    try:
        up_ms = int(ctypes.windll.kernel32.GetTickCount64())
        boot_epoch = max(0.0, time.time() - (up_ms / 1000.0))
        return datetime.fromtimestamp(boot_epoch).strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return "unknown"


def mark_restart_required() -> None:
    data = {
        "boot_id": _current_boot_id(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        _restart_marker_path().write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    except Exception:
        pass


def is_restart_required() -> bool:
    path = _restart_marker_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return True
    installed_boot = str(data.get("boot_id") or "")
    current_boot = _current_boot_id()
    if installed_boot and installed_boot != "unknown" and current_boot != "unknown" and installed_boot != current_boot:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return False
    return True


def prompt_restart_if_required(parent=None) -> bool:
    if not is_restart_required():
        return True
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Warning)
    box.setWindowTitle("Wymagany Restart")
    box.setText("Po instalacji .NET 10 SDK wymagany jest restart systemu.")
    box.setInformativeText("Czy zrestartowac komputer teraz?")
    restart_btn = box.addButton("Restart teraz", QtWidgets.QMessageBox.AcceptRole)
    box.addButton("Pozniej", QtWidgets.QMessageBox.RejectRole)
    box.exec_()
    if box.clickedButton() == restart_btn:
        subprocess.Popen(["shutdown", "/r", "/t", "0"])
        return False
    return False


class FloatingDotsWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(72)
        self._phase = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def stop(self) -> None:
        self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._phase += 0.18
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QtCore.Qt.transparent)

        w = self.width()
        h = self.height()
        mid_y = h * 0.5
        count = 7
        spacing = max(18.0, min(36.0, w / 12.0))
        total = spacing * (count - 1)
        start_x = (w - total) * 0.5

        for i in range(count):
            x = start_x + i * spacing
            wave = math.sin(self._phase + i * 0.6)
            y = mid_y + wave * 14.0
            size = 8.0 + (wave + 1.0) * 2.6
            alpha = int(140 + (wave + 1.0) * 55)
            color = QtGui.QColor(80, 175, 255, max(80, min(255, alpha)))
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(
                QtCore.QRectF(
                    x - size * 0.5,
                    y - size * 0.5,
                    size,
                    size,
                )
            )


class DotnetInstallDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instalowanie zaleznosci (.NET 10 SDK)")
        self.resize(520, 260)
        self._success = False
        self._finished = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self.info = QtWidgets.QLabel(
            "Brak .NET 10 SDK. Instalowanie Microsoft.DotNet.SDK.10..."
        )
        self.info.setWordWrap(True)
        self.info.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.info)

        self.anim = FloatingDotsWidget(self)
        layout.addWidget(self.anim)

        self.anim_label = QtWidgets.QLabel("Instalowanie, prosze czekac...")
        self.anim_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.anim_label)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(3)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        layout.addWidget(self.progress)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(84)
        self.log.setPlaceholderText("Log instalacji winget...")
        self.log.setFont(QtGui.QFont("Consolas", 8))
        layout.addWidget(self.log)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QtWidgets.QPushButton("Anuluj")
        self.cancel_btn.clicked.connect(self._cancel)
        row.addWidget(self.cancel_btn)
        layout.addLayout(row)

        self.proc = QtCore.QProcess(self)
        self.proc.readyReadStandardOutput.connect(self._read_stdout)
        self.proc.readyReadStandardError.connect(self._read_stderr)
        self.proc.finished.connect(self._finished_proc)
        self.proc.errorOccurred.connect(self._error_proc)

        self._progress_value = 3
        self._install_started = time.monotonic()
        self._progress_timer = QtCore.QTimer(self)
        self._progress_timer.timeout.connect(self._tick_progress)
        self._progress_timer.start(160)

        self._log_queue = deque()
        self._last_log_at = time.monotonic()
        self._log_timer = QtCore.QTimer(self)
        self._log_timer.timeout.connect(self._drain_log_queue)
        self._log_timer.start(70)

        QtCore.QTimer.singleShot(0, self._start_install)

    def was_successful(self) -> bool:
        return self._success

    def _start_install(self) -> None:
        args = [
            "install",
            "--id",
            "Microsoft.DotNet.SDK.10",
            "--exact",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
        self.proc.start("winget", args)
        if not self.proc.waitForStarted(3000):
            self._finalize(False)

    def _finished_proc(self, exit_code: int, _status) -> None:
        self._finalize(exit_code == 0)

    def _error_proc(self, _err) -> None:
        pass

    def _append_log(self, text: str) -> None:
        text = (text or "").replace("\r", "\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return
        for line in lines:
            self._log_queue.append(line)
        self._last_log_at = time.monotonic()

    def _drain_log_queue(self) -> None:
        appended = 0
        while self._log_queue and appended < 2:
            self.log.appendPlainText(self._log_queue.popleft())
            appended += 1
        if appended:
            sb = self.log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _read_stdout(self) -> None:
        raw = bytes(self.proc.readAllStandardOutput())
        self._append_log(raw.decode("utf-8", errors="replace"))

    def _read_stderr(self) -> None:
        raw = bytes(self.proc.readAllStandardError())
        self._append_log(raw.decode("utf-8", errors="replace"))

    def _tick_progress(self) -> None:
        if self._finished:
            return
        if (time.monotonic() - self._last_log_at) > 1.8:
            self.progress.setValue(self._progress_value)
            return
        # Time-shaped progress: starts calmly, then moves steadily, never reaches 100% before finish.
        elapsed = max(0.0, time.monotonic() - self._install_started)
        if elapsed < 8.0:
            target = 5 + int(elapsed * 3.0)
        elif elapsed < 25.0:
            target = 29 + int((elapsed - 8.0) * 2.0)
        else:
            target = 63 + int((elapsed - 25.0) * 0.9)
        target = max(5, min(95, target))
        if self._progress_value < target:
            self._progress_value += 1
        self.progress.setValue(self._progress_value)

    def _finalize(self, ok: bool) -> None:
        if self._finished:
            return
        self._finished = True
        self._success = ok
        self.anim.stop()
        self._progress_timer.stop()
        self._log_timer.stop()
        self.progress.setValue(100 if ok else min(self._progress_value, 97))
        self.cancel_btn.setText("Zamknij")
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self.accept)
        if ok:
            mark_restart_required()
            self.info.setText("Instalacja zakonczona powodzeniem.")
            self.anim_label.setText("Gotowe.")
        else:
            self.info.setText(
                "Instalacja nie powiodla sie. Pobierz recznie: https://dotnet.microsoft.com/download/dotnet/10.0"
            )
            self.anim_label.setText("Nie udalo sie zainstalowac automatycznie.")

    def _cancel(self) -> None:
        if self.proc.state() != QtCore.QProcess.NotRunning:
            self.proc.kill()
            self.proc.waitForFinished(1500)
        self.anim.stop()
        self._progress_timer.stop()
        self._log_timer.stop()
        self.reject()


class BlocksGraphWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("visual blocks ide")
        self.setWindowIcon(build_interpolated_line_icon())
        self.resize(1500, 900)

        self.graph = NodeGraph()
        self.graph.set_grid_mode(ViewerEnum.GRID_DISPLAY_LINES.value)

        self.type_to_title: Dict[str, str] = {}
        self.title_to_type: Dict[str, str] = {}
        node_classes: List[type] = []
        for title, cls in BLOCKS.items():
            node_cls = make_node_class(title, cls)
            node_classes.append(node_cls)
            type_name = f"blocks.{node_cls.__name__}"
            self.type_to_title[type_name] = title
            self.title_to_type[title] = type_name
        self.graph.register_nodes(node_classes)

        self.palette = BlockPaletteWidget(list(BLOCKS.keys()), self._create_node_by_title)
        self.prop_bin = PropertiesBinWidget(node_graph=self.graph)
        self.graph.add_properties_bin(self.prop_bin)
        self._tweak_nodegraph_ui()

        self.code_view = QtWidgets.QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setMinimumHeight(180)
        self.code_view.setFont(QtGui.QFont("Consolas", 10))

        self.console = QtWidgets.QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(170)
        self.console.setFont(QtGui.QFont("Consolas", 10))

        code_container = QtWidgets.QWidget()
        code_layout = QtWidgets.QVBoxLayout(code_container)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(6)

        code_bar = QtWidgets.QHBoxLayout()
        code_bar.addWidget(QtWidgets.QLabel("Live C#"))
        code_bar.addStretch(1)
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._run_code)
        code_bar.addWidget(self.run_btn)

        code_layout.addLayout(code_bar)
        code_layout.addWidget(self.code_view)
        code_layout.addWidget(QtWidgets.QLabel("Build Output"))
        code_layout.addWidget(self.console)

        graph_split = QtWidgets.QSplitter()
        graph_split.addWidget(self.palette)
        graph_split.addWidget(self.graph.widget)
        graph_split.addWidget(self.prop_bin)
        graph_split.setStretchFactor(0, 0)
        graph_split.setStretchFactor(1, 1)
        graph_split.setStretchFactor(2, 0)

        main_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        main_split.addWidget(graph_split)
        main_split.addWidget(code_container)
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 0)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(main_split)
        self.setCentralWidget(central)

        self._setup_live_generation()
        self._setup_shortcuts()
        self._build_menu()
        self._setup_drag_drop()
        self._dotnet_warning_shown = False

        self.graph.create_node("blocks.CreateFormNode", pos=(0, 0))
        self._generate_code()

    def _check_dotnet_sdk(self) -> bool:
        return check_dotnet_sdk()

    def _show_dotnet_missing_dialog(self, source: str) -> bool:
        if source == "startup" and self._dotnet_warning_shown:
            return False
        self._dotnet_warning_shown = True

        was_visible = self.isVisible()
        if was_visible:
            self.hide()
        installer = DotnetInstallDialog(None)
        installer.exec_()
        if was_visible:
            self.show()
            self.raise_()
            self.activateWindow()
        if installer.was_successful() and self._check_dotnet_sdk():
            return prompt_restart_if_required(self)

        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle(".NET SDK Required")
        box.setText("Nie wykryto .NET 10 SDK.")
        box.setInformativeText(
            'Zainstaluj recznie: <a href="https://dotnet.microsoft.com/download/dotnet/10.0">https://dotnet.microsoft.com/download/dotnet/10.0</a>'
        )
        box.setTextFormat(QtCore.Qt.RichText)
        box.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec_()
        return False

    def _create_node_by_title(self, title: str) -> None:
        type_name = self.title_to_type.get(title)
        if not type_name:
            return
        viewer = self.graph.viewer()
        center = viewer.viewport().rect().center()
        scene_pos = viewer.mapToScene(center)
        self.graph.create_node(type_name, pos=(scene_pos.x(), scene_pos.y()))

    def _setup_drag_drop(self) -> None:
        viewer = self.graph.viewer()
        viewer.setAcceptDrops(True)
        viewer.viewport().setAcceptDrops(True)
        viewer.installEventFilter(self)
        viewer.viewport().installEventFilter(self)

    def _tweak_nodegraph_ui(self) -> None:
        # Remove NodeGraphQt "Lock"/"Clear" buttons from the properties bin
        # to keep the UI simple for this project.
        for btn in self.prop_bin.findChildren(QtWidgets.QPushButton):
            if btn.text().strip().lower() in ("lock", "clear"):
                btn.hide()
        # Hide "2" spinbox controls shown by default in the properties bin.
        for spin in self.prop_bin.findChildren(QtWidgets.QSpinBox):
            spin.hide()

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("File")
        act_save = QtGui.QAction("Save", self)
        act_load = QtGui.QAction("Load", self)
        act_gen = QtGui.QAction("Generate C#", self)
        act_run = QtGui.QAction("Run", self)
        act_save.triggered.connect(self._save_graph)
        act_load.triggered.connect(self._load_graph)
        act_gen.triggered.connect(self._generate_code)
        act_run.triggered.connect(self._run_code)
        menu.addAction(act_save)
        menu.addAction(act_load)
        menu.addSeparator()
        menu.addAction(act_gen)
        menu.addAction(act_run)

        edit = self.menuBar().addMenu("Edit")
        edit.addAction(self._delete_action)

    def _setup_live_generation(self) -> None:
        self._regen_timer = QtCore.QTimer(self)
        self._regen_timer.setSingleShot(True)
        self._regen_timer.timeout.connect(self._generate_code)

        def _schedule(*_args):
            self._regen_timer.start(120)

        self.graph.node_created.connect(_schedule)
        self.graph.nodes_deleted.connect(_schedule)
        self.graph.port_connected.connect(_schedule)
        self.graph.port_disconnected.connect(_schedule)
        self.graph.property_changed.connect(_schedule)
        self.graph.node_selection_changed.connect(_schedule)

    def _setup_shortcuts(self) -> None:
        # Use an event filter for Delete/Backspace because the NodeGraph viewer
        # may consume key events before QAction shortcuts trigger.
        viewer = self.graph.viewer()
        viewer.installEventFilter(self)
        viewer.viewport().installEventFilter(self)
        self.graph.widget.installEventFilter(self)

        self._delete_action = QtGui.QAction("Delete", self)
        self._delete_action.triggered.connect(self._delete_selection)

        # LMB background panning state
        self._panning = False
        self._pan_prev_pos = QtCore.QPoint()

    def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
        # Accept block drags from our palette and create nodes on drop.
        if event.type() == QtCore.QEvent.DragEnter:
            if event.mimeData().hasFormat(_PaletteListWidget.MIME):
                event.acceptProposedAction()
                return True
            return False

        if event.type() == QtCore.QEvent.DragMove:
            if event.mimeData().hasFormat(_PaletteListWidget.MIME):
                event.acceptProposedAction()
                return True
            return False

        if event.type() == QtCore.QEvent.Drop:
            if event.mimeData().hasFormat(_PaletteListWidget.MIME):
                raw = bytes(event.mimeData().data(_PaletteListWidget.MIME))
                title = raw.decode("utf-8", errors="replace").strip()
                if title:
                    type_name = self.title_to_type.get(title)
                    if type_name:
                        viewer = self.graph.viewer()
                        # Drop position is in viewport coords.
                        drop_pos = event.position().toPoint()
                        scene_pos = viewer.mapToScene(drop_pos)
                        self.graph.create_node(type_name, pos=(scene_pos.x(), scene_pos.y()))
                event.acceptProposedAction()
                return True
            return False

        # Pan the graph view with LMB drag on empty space.
        if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
            viewer = self.graph.viewer()
            if obj in (viewer, viewer.viewport()):
                item = viewer.itemAt(event.position().toPoint())
                if item is None:
                    self._panning = True
                    self._pan_prev_pos = event.position().toPoint()
                    viewer.viewport().setCursor(QtCore.Qt.ClosedHandCursor)
                    event.accept()
                    return True

        if event.type() == QtCore.QEvent.MouseMove and self._panning:
            viewer = self.graph.viewer()
            if obj in (viewer, viewer.viewport()):
                prev_scene = viewer.mapToScene(self._pan_prev_pos)
                curr_pos = event.position().toPoint()
                curr_scene = viewer.mapToScene(curr_pos)
                delta = prev_scene - curr_scene
                viewer._set_viewer_pan(delta.x(), delta.y())
                self._pan_prev_pos = curr_pos
                event.accept()
                return True

        if event.type() == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton and self._panning:
            viewer = self.graph.viewer()
            if obj in (viewer, viewer.viewport()):
                self._panning = False
                viewer.viewport().unsetCursor()
                event.accept()
                return True

        if event.type() == QtCore.QEvent.KeyPress and event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            fw = QtWidgets.QApplication.focusWidget()
            if isinstance(fw, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
                return False
            self._delete_selection()
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def _delete_selection(self) -> None:
        fw = QtWidgets.QApplication.focusWidget()
        if isinstance(fw, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            return
        nodes = self.graph.selected_nodes()
        if nodes:
            self.graph.delete_nodes(nodes)

    def _save_graph(self) -> None:
        base = Path(__file__).parent
        path = self.graph.save_dialog(current_dir=str(base), ext="json", parent=self)
        if path:
            self.graph.save_session(path)

    def _load_graph(self) -> None:
        base = Path(__file__).parent
        path = self.graph.load_dialog(current_dir=str(base), ext="json", parent=self)
        if path:
            self.graph.load_session(path)

    def _build_block_instances(
        self,
    ) -> Tuple[Dict[str, object], Dict[str, Tuple[float, float]], Dict[str, Dict[str, str]]]:
        session = self.graph.serialize_session()
        nodes = session.get("nodes", {})
        connections = session.get("connections", [])

        block_items: Dict[str, object] = {}
        node_pos: Dict[str, Tuple[float, float]] = {}

        for node_id, data in nodes.items():
            node_type = data.get("type_") or data.get("type")
            title = self.type_to_title.get(node_type)
            if not title or title not in BLOCKS:
                continue

            block = BLOCKS[title]()
            custom = data.get("custom", {})
            for field in block.fields:
                prop_key = f"p_{field.key}"
                if prop_key in custom:
                    field.value = str(custom.get(prop_key, field.value))

            # Backward compatibility: old graphs used "Show Message" with a single "text" field.
            if title == "Show Message":
                has_message = any(f.key == "message" for f in block.fields)
                if has_message and "p_message" not in custom and "p_text" in custom:
                    for field in block.fields:
                        if field.key == "message":
                            field.value = str(custom.get("p_text", field.value))
                            break

            block_items[node_id] = block
            node_pos[node_id] = tuple(data.get("pos", (0, 0)))  # type: ignore[assignment]

        # value connections: val_<key> input -> other node output
        for conn in connections:
            out_id, _out_port = conn["out"]
            in_id, in_port = conn["in"]
            if not str(in_port).startswith("val_"):
                continue
            key = str(in_port).replace("val_", "", 1)
            block = block_items.get(in_id)
            if not block:
                continue
            for field in block.fields:
                if field.key == key:
                    field.value_block_id = out_id
                    break

        # flow connections: out_port -> in
        conn_map: Dict[str, Dict[str, str]] = {}
        for conn in connections:
            out_id, out_port = conn["out"]
            in_id, in_port = conn["in"]
            if in_port != "in":
                continue
            if out_port not in ("next", "true", "false", "loop"):
                continue
            conn_map.setdefault(out_id, {})[out_port] = in_id

        return block_items, node_pos, conn_map

    def _compute_value(self, node_id: str, ctx: CodeGenContext, block_items: Dict[str, object]) -> str:
        if node_id in ctx.value_map:
            return ctx.value_map[node_id]
        block = block_items.get(node_id)
        if not block or not getattr(block, "is_value", False):
            ctx.value_map[node_id] = "null"
            return "null"

        for field in block.fields:
            if getattr(field, "value_block_id", None):
                self._compute_value(field.value_block_id, ctx, block_items)

        value = block.emit_value(ctx)
        ctx.value_map[node_id] = value
        return value

    def _emit_chain(
        self,
        start_id: str,
        ctx: CodeGenContext,
        conn_map: Dict[str, Dict[str, str]],
        id_map: Dict[str, _BlockItem],
        visited: set[str],
        indent: int,
        hoisted_vars: set[str],
    ) -> None:
        current_id = start_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            item = id_map.get(current_id)
            if not item:
                return

            if current_id in hoisted_vars:
                current_id = conn_map.get(current_id, {}).get("next")
                continue

            block = item.block
            title = block.title

            if title == "If / Else":
                condition = ctx.resolve_field(block.fields, "condition", "true")
                ctx.add_main(f"if ({condition})", indent)
                ctx.add_main("{", indent)
                true_id = conn_map.get(current_id, {}).get("true")
                if true_id:
                    self._emit_chain(true_id, ctx, conn_map, id_map, visited, indent + 1, hoisted_vars)
                ctx.add_main("}", indent)

                false_id = conn_map.get(current_id, {}).get("false")
                if false_id:
                    ctx.add_main("else", indent)
                    ctx.add_main("{", indent)
                    self._emit_chain(false_id, ctx, conn_map, id_map, visited, indent + 1, hoisted_vars)
                    ctx.add_main("}", indent)
                return

            if title == "While":
                condition = ctx.resolve_field(block.fields, "condition", "true")
                ctx.add_main(f"while ({condition})", indent)
                ctx.add_main("{", indent)

                loop_id = conn_map.get(current_id, {}).get("loop")
                loop_visited: set[str] = set()
                if loop_id:
                    self._emit_chain(loop_id, ctx, conn_map, id_map, loop_visited, indent + 1, hoisted_vars)
                ctx.add_main("}", indent)

                next_id = conn_map.get(current_id, {}).get("next")
                next_visited: set[str] = set()
                if next_id:
                    self._emit_chain(next_id, ctx, conn_map, id_map, next_visited, indent, hoisted_vars)

                visited.update(loop_visited)
                visited.update(next_visited)
                return

            if title == "For Range":
                var_name = ctx.resolve_field(block.fields, "var", "i")
                start = ctx.resolve_field(block.fields, "start", "0")
                end = ctx.resolve_field(block.fields, "end", "10")
                step = ctx.resolve_field(block.fields, "step", "1")

                if var_name in ctx.declared_vars:
                    ctx.add_main(f"{var_name} = {start};", indent)
                else:
                    ctx.add_main(f"double {var_name} = {start};", indent)
                    ctx.declared_vars.add(var_name)

                ctx.add_main(f"if ({step} == 0)", indent + 1)
                ctx.add_main("{", indent + 1)
                ctx.add_main("// step 0 would never progress, skip loop body.", indent + 2)
                ctx.add_main("}", indent + 1)
                ctx.add_main("else", indent + 1)
                ctx.add_main("{", indent + 1)
                ctx.add_main(
                    f"for (; ({step} > 0 && {var_name} <= {end}) || ({step} < 0 && {var_name} >= {end}); {var_name} += {step})",
                    indent + 2,
                )
                ctx.add_main("{", indent + 2)

                loop_id = conn_map.get(current_id, {}).get("loop")
                loop_visited: set[str] = set()
                if loop_id:
                    self._emit_chain(loop_id, ctx, conn_map, id_map, loop_visited, indent + 3, hoisted_vars)
                ctx.add_main("}", indent + 2)

                next_id = conn_map.get(current_id, {}).get("next")
                next_visited: set[str] = set()
                if next_id:
                    self._emit_chain(next_id, ctx, conn_map, id_map, next_visited, indent + 1, hoisted_vars)
                ctx.add_main("}", indent + 1)

                visited.update(loop_visited)
                visited.update(next_visited)
                return

            if title == "Delay":
                interval = ctx.resolve_field(block.fields, "interval", "500")
                timer_name = ctx.next_while_name()
                ctx.add_main(f"var {timer_name} = new DispatcherTimer();", indent)
                ctx.add_main(f"{timer_name}.Interval = TimeSpan.FromMilliseconds({interval});", indent)
                ctx.add_main(f"{timer_name}.Tick += (_, __) =>", indent)
                ctx.add_main("{", indent)
                ctx.add_main(f"{timer_name}.Stop();", indent + 1)
                next_id = conn_map.get(current_id, {}).get("next")
                next_visited: set[str] = set()
                if next_id:
                    self._emit_chain(next_id, ctx, conn_map, id_map, next_visited, indent + 1, hoisted_vars)
                ctx.add_main("};", indent)
                ctx.add_main(f"{timer_name}.Start();", indent)
                visited.update(next_visited)
                return

            if title == "On Click":
                button = ctx.resolve_field(block.fields, "button", "button1")
                flag = ctx.click_flag_for(button)

                ctx.add_main(f"{button}.Click += (_, __) =>", indent)
                ctx.add_main("{", indent)
                ctx.add_main(f"{flag} = true;", indent + 1)

                handler_id = conn_map.get(current_id, {}).get("next")
                handler_visited: set[str] = set()
                if handler_id:
                    self._emit_chain(handler_id, ctx, conn_map, id_map, handler_visited, indent + 1, hoisted_vars)
                ctx.add_main("};", indent)

                visited.update(handler_visited)
                return

            block.emit(ctx, indent)
            current_id = conn_map.get(current_id, {}).get("next")

    def _generate_code(self) -> str:
        block_items, node_pos, conn_map = self._build_block_instances()
        ctx = CodeGenContext()

        for node_id, block in block_items.items():
            if getattr(block, "is_value", False):
                self._compute_value(node_id, ctx, block_items)

        flow_items: List[_BlockItem] = []
        for node_id, block in block_items.items():
            if not getattr(block, "is_value", False):
                y = float(node_pos.get(node_id, (0, 0))[1])
                flow_items.append(_BlockItem(id=node_id, block=block, y=y))

        hoisted_vars: set[str] = set()
        for item in flow_items:
            if isinstance(item.block, BoolVarBlock):
                name = ctx.resolve_field(item.block.fields, "name", "isReady")
                value = ctx.resolve_field(item.block.fields, "value", "false")
                ctx.add_pre(f"bool {name} = {value};")
                ctx.declared_vars.add(name)
                hoisted_vars.add(item.id)
            elif isinstance(item.block, StringVarBlock):
                name = ctx.resolve_field(item.block.fields, "name", "textValue")
                value = ctx.resolve_field(item.block.fields, "value", "hello", quote=True)
                ctx.add_pre(f"string {name} = {value};")
                ctx.declared_vars.add(name)
                hoisted_vars.add(item.id)
            elif isinstance(item.block, NumberVarBlock):
                name = ctx.resolve_field(item.block.fields, "name", "count")
                value = ctx.resolve_field(item.block.fields, "value", "0")
                ctx.add_pre(f"double {name} = {value};")
                ctx.declared_vars.add(name)
                hoisted_vars.add(item.id)

        id_map: Dict[str, _BlockItem] = {item.id: item for item in flow_items}
        visited: set[str] = set()

        start_id: Optional[str] = None
        for item in flow_items:
            if item.block.title == "Create Form":
                start_id = item.id
                break
        if not start_id and flow_items:
            start_id = sorted(flow_items, key=lambda i: i.y)[0].id

        if start_id:
            self._emit_chain(start_id, ctx, conn_map, id_map, visited, indent=0, hoisted_vars=hoisted_vars)

        for item in sorted(flow_items, key=lambda i: i.y):
            if item.id not in visited:
                self._emit_chain(item.id, ctx, conn_map, id_map, visited, indent=0, hoisted_vars=hoisted_vars)

        code = ctx.build_code()
        self.code_view.setPlainText(code)
        return code

    def _run_code(self) -> None:
        if not self._check_dotnet_sdk():
            if not self._show_dotnet_missing_dialog("run"):
                return

        code = self._generate_code()
        if not code:
            QtWidgets.QMessageBox.warning(self, "Run", "No code generated.")
            return

        base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        run_dir = base_dir / "_run"
        run_dir.mkdir(exist_ok=True)
        program_path = run_dir / "Program.cs"
        csproj_path = run_dir / "GeneratedBlocks.csproj"
        log_path = run_dir / "build.log"

        program_path.write_text(code, encoding="utf-8")
        csproj_path.write_text(
            """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <AssemblyName>GeneratedBlocks</AssemblyName>
    <TargetFramework>net10.0-windows</TargetFramework>
    <UseWPF>true</UseWPF>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
""",
            encoding="utf-8",
        )

        progress = QtWidgets.QProgressDialog("Preparing...", None, 0, 4, self)
        progress.setWindowTitle("Run")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setAutoClose(True)
        progress.setAutoReset(True)
        progress.setValue(0)
        progress.show()
        QtWidgets.QApplication.processEvents()

        self.console.clear()

        def _append_console(text: str) -> None:
            if text:
                self.console.appendPlainText(text.rstrip())

        progress.setLabelText("Closing previous app...")
        progress.setValue(1)
        QtWidgets.QApplication.processEvents()
        subprocess.run(
            ["taskkill", "/F", "/IM", "GeneratedBlocks.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        progress.setLabelText("Building...")
        progress.setValue(2)
        QtWidgets.QApplication.processEvents()
        build = subprocess.run(
            ["dotnet", "build"],
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        log_path.write_text((build.stdout or "") + "\n" + (build.stderr or ""), encoding="utf-8")
        _append_console(build.stdout or "")
        _append_console(build.stderr or "")
        if build.returncode != 0:
            progress.close()
            QtWidgets.QMessageBox.critical(self, "Run", f"Build failed. Log: {log_path}")
            return

        progress.setLabelText("Launching...")
        progress.setValue(3)
        QtWidgets.QApplication.processEvents()
        subprocess.Popen(["dotnet", "run", "--no-build"], cwd=str(run_dir))
        progress.setValue(4)

def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("visual blocks ide")
    app.setApplicationDisplayName("visual blocks ide")
    app.setWindowIcon(build_interpolated_line_icon())
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor(30, 30, 30))
    pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(230, 230, 230))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor(20, 20, 20))
    pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(30, 30, 30))
    pal.setColor(QtGui.QPalette.Text, QtGui.QColor(230, 230, 230))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor(45, 45, 45))
    pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(230, 230, 230))
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(0, 120, 215))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))
    app.setPalette(pal)

    if not prompt_restart_if_required(None):
        return

    if not check_dotnet_sdk():
        installer = DotnetInstallDialog(None)
        installer.exec_()
        if installer.was_successful():
            if not prompt_restart_if_required(None):
                return
        if not check_dotnet_sdk():
            box = QtWidgets.QMessageBox()
            box.setIcon(QtWidgets.QMessageBox.Warning)
            box.setWindowTitle(".NET SDK Required")
            box.setText("Nie wykryto .NET 10 SDK.")
            box.setInformativeText(
                'Zainstaluj recznie: <a href="https://dotnet.microsoft.com/download/dotnet/10.0">https://dotnet.microsoft.com/download/dotnet/10.0</a>'
            )
            box.setTextFormat(QtCore.Qt.RichText)
            box.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
            box.setStandardButtons(QtWidgets.QMessageBox.Ok)
            box.exec_()
            return

    win = BlocksGraphWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
