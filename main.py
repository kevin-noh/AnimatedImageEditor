'''
TODO LIST:
    1. Frame duration 조정 기능
'''

import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QMessageBox, QFrame, QSizePolicy, QSpinBox, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QMimeData, QRect, QSize
from PyQt6.QtGui import QPixmap, QDrag, QCursor
from PyQt6.QtWidgets import QRubberBand
from PIL import Image, ImageSequence
from PIL.ImageQt import ImageQt
import os

MODE_MERGE = 0
MODE_CONCAT = 1

# HELPER FUNCTIONS
def custom_round(op):
    from math import modf, isclose
    
    fractional_part, integer_part = modf(op)
    
    if fractional_part > 0.5 or isclose(fractional_part, 0.5000, abs_tol=1e-4):
        integer_part += 1
        fractional_part = 0.0

    return integer_part, fractional_part

def deleteItemsOfLayout(layout):
    if layout is not None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                deleteItemsOfLayout(item.layout())

class ResizePopup(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resize")

        layout = QVBoxLayout()
        self.setLayout(layout)

        w_area = QHBoxLayout()
        w_area.addWidget(QLabel("New height?"))

        self.integer_spin_box = QSpinBox()
        self.integer_spin_box.setMinimum(1)
        self.integer_spin_box.setMaximum(4000)
        self.integer_spin_box.setSingleStep(5)
        self.integer_spin_box.setValue(50)
        #self.integer_spin_box.setSuffix("")
        w_area.addWidget(self.integer_spin_box)

        layout.addLayout(w_area)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)  # Closes the dialog and sets result to Accepted
        layout.addWidget(ok_button)

class MainDropLabel(QLabel):
    def __init__(self, parent, MDL_index):
        super().__init__()
        self.parent = parent
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Drag and drop the animated image you want to edit here")
        self.setStyleSheet("border: 2px dashed #666; font-size: 18px;")
        
        self.MDL_index = MDL_index
        self.frames = []
        self.current_frame_index = 0
        self.is_playing = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.play_next_frame)
        self.selected_indices = set()

    def reset(self):
        self.setText("Drag and drop the animated image you want to edit here")
        self.setStyleSheet("border: 2px dashed #666; font-size: 18px;")
        for f in self.frames:
            f.close()
        if hasattr(self, 'frames'):
            self.frames.clear()
        if hasattr(self, 'durations'):
            self.durations.clear()
        self.durations = []
        self.current_frame_index = 0
        self.is_playing = False
        self.selected_indices.clear()

    def load_animation(self, file_path):
        if self.frames:
            box = QMessageBox(self)
            box.setWindowTitle("Replace or Merge?")
            box.setText("An animation is already loaded. Would you like to replace it or merge/concatenate with the new one?")
            replace_btn = box.addButton("Replace", QMessageBox.ButtonRole.YesRole)
            merge_btn = box.addButton("Merge", QMessageBox.ButtonRole.NoRole)
            concat_btn = box.addButton("Concatenate", QMessageBox.ButtonRole.NoRole)
            box.setIcon(QMessageBox.Icon.Question)
            box.exec()
            
            if box.clickedButton() == merge_btn:
                try:
                    AIE = self.parent.parent.parent.parent
                    if AIE.isDualModeOn:
                        return
                    AIE.enable_dual_mode(file_path, MODE_MERGE)
                    return
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to load second image: {str(e)}")
                    return
            elif box.clickedButton() == concat_btn:
                try:
                    AIE = self.parent.parent.parent.parent
                    if AIE.isDualModeOn:
                        return
                    AIE.enable_dual_mode(file_path, MODE_CONCAT)
                    return
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to load second image: {str(e)}")
                    return
                
        self.ext = os.path.splitext(file_path)[-1].lower()
        if self.ext not in [".gif", ".webp", ".jpg", ".jpeg", ".png"]:
            QMessageBox.critical(self, "Unsupported File", "Only image files are supported.")
            return

        try:
            self.reset()
            self.setStyleSheet("")
            img = Image.open(file_path)
            for frame in ImageSequence.Iterator(img):
                self.frames.append(frame.convert("RGBA"))
                self.durations.append(frame.info.get("duration", 100))
            self.current_frame_index = 0
            self.display_frame(self.current_frame_index)
            self.populate_frame_area()

            # INSERTION LINE
            if not hasattr(self, 'insertion_line'):
                self.insertion_line = QFrame(self.parent.parent.parent.itemAt(2).itemAt(self.MDL_index).widget().widget())
                self.insertion_line.setFrameShape(QFrame.Shape.VLine)
                self.insertion_line.setStyleSheet("color: blue; background-color: blue;")
                self.insertion_line.setFixedWidth(2)
                self.insertion_line.hide()

            if not hasattr(self, 'buttons'):
                self.buttons = QHBoxLayout()

                self.integer_spin_box = QSpinBox()
                self.integer_spin_box.setMinimum(-10000)
                self.integer_spin_box.setMaximum(10000)
                self.integer_spin_box.setSingleStep(5)
                self.integer_spin_box.setValue(20) # Initial value
                self.integer_spin_box.setSuffix(" ms")
                self.buttons.addWidget(self.integer_spin_box)
                self.update_button = QPushButton("Update")
                self.update_button.clicked.connect(self.update_frame_durations)
                self.buttons.addWidget(self.update_button, alignment=Qt.AlignmentFlag.AlignCenter)

                self.reverse_button = QPushButton("Reverse")
                self.reverse_button.clicked.connect(self.reverse_frames)
                self.buttons.addWidget(self.reverse_button, alignment=Qt.AlignmentFlag.AlignCenter)

                self.pendulum_button = QPushButton("Pendulum")
                self.pendulum_button.clicked.connect(self.pendulum_frames)
                self.buttons.addWidget(self.pendulum_button, alignment=Qt.AlignmentFlag.AlignCenter)

                self.resize_button = QPushButton("Resize")
                self.resize_button.clicked.connect(self.handle_resizing)
                self.buttons.addWidget(self.resize_button, alignment=Qt.AlignmentFlag.AlignCenter)

                self.parent.addLayout(self.buttons)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {str(e)}")

    def handle_resizing(self):
        dialog = ResizePopup(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            height = dialog.integer_spin_box.value()
            self.resize_frames(height)
            self.display_frame(self.current_frame_index)

    def resize_frames(self, height):
        w, h = self.frames[0].size
        aspect_ratio = h / w
        new_h = height
        new_w = int(new_h / aspect_ratio)

        for idx, f in enumerate(self.frames):
            resized = f.resize((new_w, new_h), Image.LANCZOS)
            f.close()
            self.frames[idx] = resized

    def update_frame_durations(self):
        if not self.selected_indices:
            return

        self.parent.parent.parent.parent.save_state(self.MDL_index)
        val = self.integer_spin_box.value()
        duration_sum = 0
        for idx in self.selected_indices:
            if val > 0:
                self.durations[idx] += val
            else:
                self.durations[idx] = max(1, self.durations[idx] + val)
            duration_sum += self.durations[idx]

        frame_info_label = self.parent.itemAt(1).widget()
        idx = sorted(self.selected_indices)[0]
        w, h = self.frames[idx].size
        frame_info_label.setText(f"Displaying frame {idx + 1} of {len(self.frames)} ({sum(self.durations)} ms in total)\n{w} x {h}" \
                                 + f"\nduration of selected frames: {str(duration_sum)} ms")
        self.populate_frame_area()

    def populate_frame_area(self):
        self.highlighted_thumbs = []
        frame_layout = self.parent.parent.parent.itemAt(2).itemAt(self.MDL_index).widget().widget().layout()

        for i in reversed(range(frame_layout.count())):
            item = frame_layout.itemAt(i)
            widget = item.widget()
            if widget:
                widget.deleteLater()
                
        # update frame indices so thumbnail labels reflect new order
        for idx, frame in enumerate(self.frames):
            pixmap = QPixmap.fromImage(ImageQt(frame))
            thumb = FrameThumbnail(self, idx, pixmap)
            thumb.parent = self.parent.parent.parent.itemAt(2).itemAt(self.MDL_index).widget()
            frame_layout.addWidget(thumb)
            self.highlighted_thumbs.append(thumb)
            if idx in self.selected_indices:
                thumb.setStyleSheet("border: 2px solid blue;")
            else:
                thumb.setStyleSheet("")
    
    def reverse_frames(self):
        if not self.frames:
            QMessageBox.warning(self, "Warning", "No frames to reverse.")
            return
        self.parent.parent.parent.parent.save_state(self.MDL_index)
        self.frames.reverse()
        if hasattr(self, 'durations'):
            self.durations.reverse()
        self.selected_indices = {len(self.frames) - 1 - i for i in self.selected_indices}
        self.current_frame_index = len(self.frames) - 1 - self.current_frame_index
        self.populate_frame_area()
        self.display_frame(self.current_frame_index)

    def pendulum_frames(self):
        if not self.frames:
            QMessageBox.warning(self, "Warning", "No frames to reverse.")
            return
        
        self.parent.parent.parent.parent.save_state(self.MDL_index)
        self.frames.extend(self.frames[::-1])
        if hasattr(self, 'durations'):
            self.durations.extend(self.durations[::-1])
        self.populate_frame_area()
        self.display_frame(self.current_frame_index)


    def frame_clicked(self, index):
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ShiftModifier and self.selected_indices:
            last_selected = sorted(self.selected_indices)[-1]
            start = min(last_selected, index)
            end = max(last_selected, index)
            self.selected_indices = set(range(start, end + 1))
        elif modifiers == Qt.KeyboardModifier.ControlModifier:
            if index in self.selected_indices:
                self.selected_indices.remove(index)
            else:
                self.selected_indices.add(index)
            self.current_frame_index = index
            self.display_frame(index)
        else:
            self.selected_indices = {index}
            self.current_frame_index = index
            self.display_frame(index)
        self.highlight_selected_frames()

    def highlight_selected_frames(self):
        frame_layout = self.parent.parent.parent.itemAt(2).itemAt(self.MDL_index).widget().widget().layout()

        duration_sum = 0
        for i in range(frame_layout.count()):
            thumb = frame_layout.itemAt(i).widget()
            if i in self.selected_indices:
                duration_sum += self.durations[i]
                thumb.setStyleSheet("border: 2px solid blue;")
            else:
                thumb.setStyleSheet("")

        
        idx = sorted(self.selected_indices)[0] if self.selected_indices else 0
        w, h = self.frames[idx].size
        frame_info_label = self.parent.itemAt(1).widget()
        frame_info_label.setText(f"Displaying frame {idx + 1} of {len(self.frames)} ({sum(self.durations)} ms in total)\n{w} x {h}"\
                                  + f"\nduration of selected frames: {str(duration_sum)} ms")
    
    def reorder_frames(self, source_index, target_index):
        self.parent.parent.parent.parent.save_state(self.MDL_index)

        if not self.selected_indices:
            self.selected_indices = {source_index}

        selected = sorted(self.selected_indices)
        moving = [self.frames[i] for i in selected]
        moving_durations = [self.durations[i] for i in selected]

        for i in reversed(selected):
            del self.frames[i]
            del self.durations[i]

        insert_pos = target_index
        for i, (f, d) in enumerate(zip(moving, moving_durations)):
            self.frames.insert(insert_pos + i, f)
            self.durations.insert(insert_pos + i, d)

        self.selected_indices = set(range(insert_pos, insert_pos + len(moving)))
        self.populate_frame_area()
        self.display_frame(self.current_frame_index)

    def play_next_frame(self):
        self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
        self.display_frame(self.current_frame_index)

    def display_frame(self, index):
        if not self.frames:
            self.reset()
            return

        if 0 <= index < len(self.frames):
            self.imageqt_ref = ImageQt(self.frames[index])  # prevent GC
            pixmap = QPixmap.fromImage(self.imageqt_ref)
            scaled_pixmap = pixmap.scaled(self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled_pixmap)
            w, h = self.frames[index].size
            frame_info_label = self.parent.itemAt(1).widget()
            frame_info_label.setText(f"Displaying frame {index + 1} of {len(self.frames)} ({sum(self.durations)} ms in total)\n{w} x {h}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        file_path = event.mimeData().urls()[0].toLocalFile()
        self.load_animation(file_path)


    # CROPPING FUNCTIONS
    def mousePressEvent(self, event):
        if not self.frames:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.pos()
            self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if hasattr(self, 'rubber_band'):
            rect = QRect(self.origin, event.pos()).normalized()
            self.rubber_band.setGeometry(rect)

    def mouseReleaseEvent(self, event):
        if not self.frames:
            return
        if hasattr(self, 'rubber_band'):
            self.rubber_band.hide()
            rect = self.rubber_band.geometry()
            if rect.width() < 20 or rect.height() < 20:
                return
            
            label_width = self.width()
            label_height = self.height()
            image = self.frames[self.current_frame_index]
            img_width, img_height = image.size
            scale = min(label_width / img_width, label_height / img_height)

            x_offset = (label_width - img_width * scale) / 2
            y_offset = (label_height - img_height * scale) / 2

            left = int((rect.left() - x_offset) / scale)
            top = int((rect.top() - y_offset) / scale)
            right = int((rect.right() - x_offset) / scale)
            bottom = int((rect.bottom() - y_offset) / scale)

            left = max(0, min(left, img_width))
            top = max(0, min(top, img_height))
            right = max(left + 1, min(right, img_width))
            bottom = max(top + 1, min(bottom, img_height))

            preview_img = image.copy().crop((left, top, right, bottom))
            pixmap_preview = QPixmap.fromImage(ImageQt(preview_img))
            preview_box = QMessageBox(self)
            preview_box.setIconPixmap(pixmap_preview.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio))
            w, h = preview_img.size
            preview_box.setWindowTitle("Crop Preview")
            preview_box.setText(f"Crop image to selected area?\n({w}, {h})")
            preview_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            reply = preview_box.exec()

            if reply == QMessageBox.StandardButton.Yes:
                crop_box = (left, top, right, bottom)
                self.parent.parent.parent.parent.save_state(self.MDL_index)
                self.frames = [f.crop(crop_box) for f in self.frames]
                self.display_frame(self.current_frame_index)
                self.populate_frame_area()

    # FRAME MODIFICATION FUNCTIONS
    def duplicate_frame(self, index):
        self.parent.parent.parent.parent.save_state(self.MDL_index)

        if 0 <= index < len(self.frames):
            duplicated = self.frames[index].copy()
            self.frames.insert(index + 1, duplicated)
            if hasattr(self, 'durations'):
                self.durations.insert(index + 1, self.durations[index])
            self.populate_frame_area()

    def delete_frame(self, index):
        self.parent.parent.parent.parent.save_state(self.MDL_index)

        if index in self.selected_indices:
            self.selected_indices.remove(index)
        if 0 <= index < len(self.frames) and len(self.frames) > 1:
            del self.frames[index]
            if self.current_frame_index >= len(self.frames):
                self.current_frame_index = len(self.frames) - 1
            self.populate_frame_area()
            self.display_frame(self.current_frame_index)

    def deleteSelectedFrames(self):
        self.parent.parent.parent.parent.save_state(self.MDL_index)
        if hasattr(self, 'selected_indices') and self.selected_indices:
            to_delete = sorted(self.selected_indices, reverse=True)
            for index in to_delete:
                if 0 <= index < len(self.frames):
                    del self.frames[index]
                    if hasattr(self, 'durations'):
                        del self.durations[index]
            self.selected_indices.clear()
            self.current_frame_index = min(self.current_frame_index, len(self.frames) - 1)
            self.populate_frame_area()
            self.display_frame(self.current_frame_index)
    
    # UNDO / REDO RELATED FUNCTIONS
    def get_current_state(self):
        return (self.MDL_index, self.frames.copy(), self.durations.copy(), self.current_frame_index)

    def overwrite_state(self, frames, durations, current_frame_index):
        self.frames.clear()
        self.durations.clear()
        self.frames = frames
        self.durations = durations
        self.current_frame_index = current_frame_index

class FrameThumbnail(QFrame):
    def start_scroll_timer(self):
        if not hasattr(self, 'drag_scroll_timer'):
            self.drag_scroll_timer = QTimer(self)
            self.drag_scroll_timer.setInterval(50)
            self.drag_scroll_timer.timeout.connect(self.scroll_while_dragging)
        self.drag_scroll_timer.start()

    def stop_scroll_timer(self):
        if hasattr(self, 'drag_scroll_timer'):
            self.drag_scroll_timer.stop()

    def scroll_while_dragging(self):
        scroll_area = self.parent
        cursor_global = QCursor.pos()
        cursor_pos = scroll_area.viewport().mapFromGlobal(cursor_global)
        margin = 40
        scroll_speed = 30
        if cursor_pos.x() < margin:
            scroll_area.horizontalScrollBar().setValue(scroll_area.horizontalScrollBar().value() - scroll_speed)
        elif cursor_pos.x() > scroll_area.viewport().width() - margin:
            scroll_area.horizontalScrollBar().setValue(scroll_area.horizontalScrollBar().value() + scroll_speed)

    def enterEvent(self, event):
        self.duplicate_btn.show()
        self.delete_btn.show()

    def leaveEvent(self, event):
        self.duplicate_btn.hide()
        self.delete_btn.hide()

    def __init__(self, editor, index, pixmap):
        super().__init__()
        self.editor = editor
        self.index = index
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        self.drag_scroll_timer = QTimer(self)
        self.drag_scroll_timer.setInterval(50)
        self.drag_scroll_timer.timeout.connect(self.scroll_while_dragging)

        self.label = QLabel()
        self.label.setPixmap(pixmap.scaledToHeight(60))
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignCenter)

        duration = self.editor.durations[self.index] if hasattr(self.editor, 'durations') else 100
        self.text = QLabel(f"#{index+1} ({duration}ms)")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setStyleSheet("font-size: 10px; color: gray;")  # Style for index/duration label
        layout.addWidget(self.text)

        self.duplicate_btn = QPushButton("D")  # 🔧 Fixed indentation
        self.duplicate_btn.setFixedSize(16, 16)
        self.duplicate_btn.setStyleSheet("background-color: lightblue; border: none; font-weight: bold;")
        self.duplicate_btn.clicked.connect(lambda: self.editor.duplicate_frame(self.index))
        self.duplicate_btn.hide()

        self.delete_btn = QPushButton("X")
        self.delete_btn.setFixedSize(16, 16)
        self.delete_btn.setStyleSheet("background-color: lightcoral; border: none; font-weight: bold;")
        self.delete_btn.clicked.connect(lambda: self.editor.delete_frame(self.index))
        self.delete_btn.hide()

        self.overlay_layout = QHBoxLayout(self.label)
        self.overlay_layout.setContentsMargins(0, 0, 0, 0)
        self.overlay_layout.addWidget(self.duplicate_btn)
        self.overlay_layout.addStretch()
        self.overlay_layout.addWidget(self.delete_btn)

        self.setLayout(layout)
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.start_scroll_timer()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            if (event.pos() - self.drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(str(self.index))
                drag.setMimeData(mime)
                drag.exec()

    def mouseReleaseEvent(self, event):
        self.stop_scroll_timer()
        if event.button() == Qt.MouseButton.LeftButton:
            if (event.pos() - self.drag_start_pos).manhattanLength() <= QApplication.startDragDistance():
                self.editor.frame_clicked(self.index)

    def dragEnterEvent(self, event):
        frame_layout = self.parent.widget().layout()
        MDL_index = int(self.parent.widget().objectName()[-1:])
        insertion_line = self.parent.parent.parent.itemAt(1).itemAt(MDL_index).itemAt(0).widget().insertion_line
        frame_container = self.parent.widget()

        if event.mimeData().hasText():
            event.acceptProposedAction()
            index = self.index
            target_widget = frame_layout.itemAt(index).widget()
            if target_widget:
                geo = target_widget.geometry()
                insertion_line.setGeometry(
                    geo.x() - 1, 0, 2, frame_container.height()
                )
                insertion_line.show()
            #self.setStyleSheet("background-color: #d0f0ff; border: 2px dashed #3399ff;")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        MDL_index = int(self.parent.widget().objectName()[-1:])
        self.parent.parent.parent.itemAt(1).itemAt(MDL_index).itemAt(0).widget().insertion_line.hide()

    def dropEvent(self, event):
        MDL_index = int(self.parent.widget().objectName()[-1:])
        self.parent.parent.parent.itemAt(1).itemAt(MDL_index).itemAt(0).widget().insertion_line.hide()
        source_index = int(event.mimeData().text())
        target_index = self.index
        self.editor.reorder_frames(source_index, target_index)
        event.acceptProposedAction()

class AnimatedImageEditor(QWidget):
    def save_state(self, MDL_index):
        MDL = self.layout().itemAt(1).itemAt(MDL_index).itemAt(0).widget()
        self.undo_stack.append((MDL_index, MDL.frames.copy(), MDL.durations.copy(), MDL.current_frame_index))
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            state = self.undo_stack.pop()
            # if state[0] == 1 and not self.isDualModeOn:
            #     self.enable_dual_mode()

            MDL = self.layout().itemAt(1).itemAt(state[0]).itemAt(0).widget()
            self.redo_stack.append(MDL.get_current_state())
            
            MDL.overwrite_state(state[1].copy(), state[2].copy(), state[3])
            MDL.populate_frame_area()
            MDL.display_frame(state[3])

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            MDL = self.layout().itemAt(1).itemAt(state[0]).itemAt(0).widget()
            self.undo_stack.append(MDL.get_current_state())

            MDL.overwrite_state(state[1].copy(), state[2].copy(), state[3])
            MDL.populate_frame_area()
            MDL.display_frame(state[3])

    def select_all(self):
        return
    
    def keyPressEvent(self, event):
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier

        if ctrl and shift and event.key() == Qt.Key.Key_Z:
            self.redo()
            return
        elif ctrl and event.key() == Qt.Key.Key_Z:
            self.undo()
            return
        elif ctrl and event.key() == Qt.Key.Key_A:
            self.select_all()
            return

        if event.key() == Qt.Key.Key_Delete:
            for idx in range(self.numOfMDL):
                MDL = self.layout().itemAt(1).itemAt(idx).itemAt(0).widget()
                MDL.deleteSelectedFrames()
            return

    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []

        super().__init__()
        self.setObjectName("AIE")
        self.setWindowTitle("Animated Image Editor")
        self.resize(1280, 800)
        self.numOfMDL = 1
        self.isDualModeOn = False

        # TOP LAYOUT
        self.top_layout = QHBoxLayout()
        self.top_layout.setObjectName("top")
        top_sub_layout = QVBoxLayout()
        top_sub_layout.setObjectName("top_sub 0")
        top_sub_layout.parent = self.top_layout

        main_label = MainDropLabel(top_sub_layout, 0)
        main_label.setMinimumHeight(400)
        main_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        frame_info_label = QLabel()
        frame_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_info_label.setStyleSheet("font-size: 14px; color: gray;")

        top_sub_layout.addWidget(main_label)
        top_sub_layout.addWidget(frame_info_label)
        self.top_layout.addLayout(top_sub_layout)


        # MIDDLE LAYOUT
        self.middle_layout = QVBoxLayout()
        self.middle_layout.setObjectName("middle")

        frame_area = QScrollArea()
        frame_area.parent = self.middle_layout
        frame_area.setObjectName("frame_area")
        frame_area.setWidgetResizable(True)
        frame_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frame_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        frame_area.setFixedHeight(120)
        frame_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        frame_container = QWidget()
        frame_container.setObjectName("frame_container 0")
        frame_layout = QHBoxLayout()
        frame_layout.setObjectName("frame_layout")
        frame_container.setLayout(frame_layout)
        frame_container.setMinimumHeight(90)
        frame_area.setWidget(frame_container)

        self.middle_layout.addWidget(frame_area)


        # BOTTOM LAYOUT
        self.bottom_layout = QHBoxLayout()
        self.bottom_layout.setObjectName("btm")

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_play_pause)
        self.bottom_layout.addWidget(self.play_button, alignment=Qt.AlignmentFlag.AlignCenter)
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.export_animation)
        self.bottom_layout.addWidget(export_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # MAIN LAYOUT
        layout = QVBoxLayout()
        layout.setObjectName("main")
        layout.parent = self

        timeline = QLabel("Timeline: Frame preview and edit panel")
        timeline.setStyleSheet("background-color: #eee; padding: 5px; font-size: 12px;")
        timeline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(timeline)

        layout.addLayout(self.top_layout)
        layout.addLayout(self.middle_layout)
        layout.addLayout(self.bottom_layout)
        self.top_layout.parent = layout
        self.middle_layout.parent = layout
        self.bottom_layout.parent = layout

        self.setLayout(layout)

    
    # BUTTON FUNCTIONS
    def toggle_play_pause(self):
        for i in range(self.top_layout.count()):
            MDL = self.top_layout.itemAt(i).itemAt(0).widget()
            if not MDL.frames:
                QMessageBox.warning(self, "Warning", "No frames to play.")
                return
            if MDL.is_playing:
                MDL.timer.stop()
                self.play_button.setText("Play")
            else:
                MDL.timer.start(100)
                self.play_button.setText("Pause")
            MDL.is_playing = not MDL.is_playing

    def export_animation(self):
        if self.isDualModeOn:
            # merge frames from the two MDLs
            frames = []
        else:
            MDL = self.top_layout.itemAt(0).itemAt(0).widget()
            frames = MDL.frames
            
        if not frames:
            QMessageBox.warning(self, "Warning", "No frames to export.")
            return

        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Save Animation", "output"+MDL.ext, "GIF Files (*.gif);;WebP Files (*.webp)" if MDL.ext == ".gif" else "WebP Files (*.webp);;GIF Files (*.gif)")

        if not path:
            return

        ext = os.path.splitext(path)[-1].lower()
        if ext not in [".gif", ".webp"]:
            QMessageBox.warning(self, "Invalid Format", "Only .gif or .webp extensions are supported.")
            return

        try:
            if ext == ".webp":
                frames[0].save(
                    path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=MDL.durations,
                    loop=0,
                    optimize=True,
                    format="GIF" if ext == ".gif" else "WEBP"
                )
            else:
                def chunk_frames(frames, chunk_size=64):
                    for i in range(0, len(frames), chunk_size):
                        yield frames[i:i+chunk_size]

                chunks = list(chunk_frames(frames))
                export_frames = []
                for chunk in chunks:
                    # palette=Image.WEB
                    base_palette = chunk[0].convert("RGB").convert("P", palette=Image.ADAPTIVE, dither=Image.NONE)
                    for frame in chunk:
                        export_frames.append(frame.convert("RGB").quantize(palette=base_palette))

                export_frames[0].save(
                    path,
                    save_all=True,
                    append_images=export_frames[1:],
                    duration=MDL.durations,
                    loop=0,
                    optimize=True,
                    format="GIF" if ext == ".gif" else "WEBP"
                )
            QMessageBox.information(self, "Success", f"Animation saved to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")

    def enable_dual_mode(self, file_path, mode):
        self.numOfMDL = 2
        self.isDualModeOn = True
        
        # TOP LAYOUT
        top_sub_layout = QVBoxLayout()
        top_sub_layout.setObjectName("top_sub 1")
        top_sub_layout.parent = self.top_layout

        main_label = MainDropLabel(top_sub_layout, 1)
        main_label.setMinimumHeight(400)
        main_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        frame_info_label = QLabel()
        frame_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_info_label.setStyleSheet("font-size: 14px; color: gray;")

        top_sub_layout.addWidget(main_label)
        top_sub_layout.addWidget(frame_info_label)

        self.top_layout.addLayout(top_sub_layout)


        # MIDDLE LAYOUT
        frame_area = QScrollArea()
        frame_area.parent = self.middle_layout
        frame_area.setObjectName("frame_area")
        frame_area.setWidgetResizable(True)
        frame_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frame_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        frame_area.setFixedHeight(120)
        frame_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        frame_container = QWidget()
        frame_container.setObjectName("frame_container 1")
        frame_layout = QHBoxLayout()
        frame_layout.setObjectName("frame_layout")
        frame_container.setLayout(frame_layout)
        frame_container.setMinimumHeight(90)
        frame_area.setWidget(frame_container)

        self.middle_layout.addWidget(frame_area)

        main_label.load_animation(file_path)
        self.save_state(1)

        # ADD MERGE or CONCAT BUTTON AT THE BOTTOM LAYOUT
        if mode == MODE_MERGE:
            merge_button = QPushButton("Merge")
            merge_button.clicked.connect(self.handle_merge)
            self.bottom_layout.addWidget(merge_button, alignment=Qt.AlignmentFlag.AlignCenter)
        elif mode == MODE_CONCAT:
            concat_button = QPushButton("Concatenate")
            concat_button.clicked.connect(self.handle_concat)
            self.bottom_layout.addWidget(concat_button, alignment=Qt.AlignmentFlag.AlignCenter)

    def handle_concat(self):
        MDL_1 = self.top_layout.itemAt(0).itemAt(0).widget()
        MDL_2 = self.top_layout.itemAt(1).itemAt(0).widget()

        w1, h1 = MDL_1.frames[0].size
        w2, h2 = MDL_2.frames[0].size

        width1, height1, width2, height2, is_resizing_1 = self.calc_resizing_metrics(w1, h1, w2, h2)
        container_width = max(width1, width2)
        container_height = height1

        # CENTER (container_width - width2) // 2 
        # LEFT 0
        # RIGHT container_width - width2
        if is_resizing_1:
            resized2 = []
            if container_width > width2:
                for f in MDL_2.frames:
                    container = Image.new("RGB", (container_width, container_height), (0, 0, 0))
                    container.paste(f, ((container_width - width2) // 2, 0))
                    resized2.append(container.convert("RGBA"))
                    f.close()
            else:
                resized2 = [f.copy() for f in MDL_2.frames]

            resized1 = []
            MDL_1.resize_frames(height1)
            for f in MDL_1.frames:
                container = Image.new("RGB", (container_width, container_height), (0, 0, 0))
                container.paste(f, ((container_width - width1) // 2, 0))
                resized1.append(container.convert("RGBA"))
                f.close()
        else:
            resized1 = []
            if container_width > width1:
                for f in MDL_1.frames:
                    container = Image.new("RGB", (container_width, container_height), (0, 0, 0))
                    container.paste(f, ((container_width - width1) // 2 , 0))
                    resized1.append(container.convert("RGBA"))
                    f.close()
            else:
                resized1 = MDL_1.frames

            resized2 = []
            MDL_2.resize_frames(height2)
            for f in MDL_2.frames:
                container = Image.new("RGB", (container_width, container_height), (0, 0, 0))
                container.paste(f, ((container_width - width2) // 2 , 0))
                resized2.append(container.convert("RGBA"))
                f.close()

        resized1.extend(resized2)
        d = MDL_1.durations + MDL_2.durations
        
        MDL_1.overwrite_state(resized1.copy(), d.copy(), 0)
        MDL_1.populate_frame_area()
        MDL_1.display_frame(0)
        MDL_2.reset()
        self.enable_single_mode()
    

    def handle_merge(self):
        MDL_1 = self.top_layout.itemAt(0).itemAt(0).widget()
        MDL_2 = self.top_layout.itemAt(1).itemAt(0).widget()
        
        if MDL_1.is_playing:
            self.toggle_play_pause()

        if len(MDL_1.frames) == 1:
            num_of_frames = len(MDL_2.frames)
            MDL_1.frames = MDL_1.frames * num_of_frames
            MDL_1.durations = MDL_2.durations.copy()
        elif len(MDL_2.frames) == 1:
            num_of_frames = len(MDL_1.frames)
            MDL_2.frames = MDL_2.frames * num_of_frames
            MDL_2.durations = MDL_1.durations.copy()

        else:
            self.adjust_frame_durations(MDL_1, MDL_2)

        self.merge_images(MDL_1, MDL_2)
        self.enable_single_mode()
    
    def adjust_frame_durations(self, MDL_1, MDL_2):
        d1 = MDL_1.durations
        d2 = MDL_2.durations

        sum1 = sum(d1)
        sum2 = sum(d2)

        if sum1 > sum2:
            leftover = 0
            for idx, d in enumerate(d2):
                proportion = d / sum2
                int_part, frac_part = custom_round(sum1 * proportion)
                leftover += frac_part
                d2[idx] = int(int_part)
            
            leftover = round(leftover)

            MDL_2.durations = d2

        else:
            leftover = 0
            for idx, d in enumerate(d1):
                proportion = d / sum1
                int_part, frac_part = custom_round(sum2 * proportion)
                leftover += frac_part
                d1[idx] = int(int_part)
            
            leftover = round(leftover)

            MDL_1.durations = d1
    
    def calc_resizing_metrics(self, w1, h1, w2, h2):
        new_height = max(h1, h2)
        if new_height == h1:
            aspect_ratio = h2 / w2
            new_width = int(new_height / aspect_ratio)
            w2 = new_width
            h2 = new_height
            is_resizing_1 = False
        else:
            aspect_ratio = h1 / w1
            new_width = int(new_height / aspect_ratio)
            w1 = new_width
            h1 = new_height
            is_resizing_1 = True

        return w1, h1, w2, h2, is_resizing_1
    
    def merge_images(self, MDL_1, MDL_2):
        concat_frames = []
        concat_durations = []

        w1, h1 = MDL_1.frames[0].size
        w2, h2 = MDL_2.frames[0].size
        width1, height1, width2, height2, is_resizing_1 = self.calc_resizing_metrics(w1, h1, w2, h2)
        combined_width = width1 + width2
        combined_height = height1

        # Pre-resize all frames
        if is_resizing_1:
            MDL_1.resize_frames(height1)
        else:
            MDL_2.resize_frames(height2)
        
        resized1 = MDL_1.frames
        resized2 = MDL_2.frames

        i, j = 0, 0
        durs1 = MDL_1.durations[:]
        durs2 = MDL_2.durations[:]

        while i < len(resized1) and j < len(resized2):
            frame1 = resized1[i]
            frame2 = resized2[j]

            combined_image = Image.new("RGB", (combined_width, combined_height), (0, 0, 0))
            combined_image.paste(frame1, (0, 0))
            combined_image.paste(frame2, (width1, 0))
            combined_image.thumbnail((1920, 1920))

            d1, d2 = durs1[i], durs2[j]
            consumed = min(d1, d2)

            durs1[i] -= consumed
            durs2[j] -= consumed

            if durs1[i] == 0:
                i += 1
            if durs2[j] == 0:
                j += 1

            concat_frames.append(combined_image.convert("RGBA"))
            concat_durations.append(consumed)

        MDL_1.overwrite_state(concat_frames.copy(), concat_durations.copy(), 0)
        MDL_1.populate_frame_area()
        MDL_1.display_frame(0)
        MDL_2.reset()
    
    def enable_single_mode(self):
        self.numOfMDL = 1
        self.isDualModeOn = False

        # TOP LAYOUT
        top_sub_1 = self.top_layout.itemAt(1)
        deleteItemsOfLayout(top_sub_1)
        top_sub_1.parent = None
        top_sub_1.deleteLater()

        # MIDDLE LAYOUT
        frame_area_1 = self.middle_layout.itemAt(1).widget()
        frame_container = frame_area_1.widget()
        frame_layout = frame_container.layout()
        deleteItemsOfLayout(frame_layout)
        frame_layout.parent = None
        frame_layout.deleteLater()
        frame_container.deleteLater()
        frame_area_1.deleteLater()

        # BOTTOM LAYOUT
        merge_button = self.bottom_layout.itemAt(2).widget()
        merge_button.setParent(None)
        merge_button.deleteLater()
    
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = AnimatedImageEditor()
    window.show()
    window.resizeEvent = lambda event: (window.display_frame(window.current_frame_index), QWidget.resizeEvent(window, event))
    sys.exit(app.exec())
