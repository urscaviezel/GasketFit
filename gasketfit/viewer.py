import numpy as np
import time
import weakref
from PySide6 import QtCore, QtGui
import pyqtgraph.opengl as gl
from pyqtgraph.opengl import shaders
from .profile import frame_vertices, weights, full_weights, transform, permanent_features, validate_regions
from .navigation import controls, manager
from .section_view import NO_SECTION, section_mask


LIGHT = shaders.ShaderProgram("gasketfitLight", [
    shaders.VertexShader("""
        uniform mat4 u_mvp; uniform mat3 u_normal;
        attribute vec4 a_position; attribute vec3 a_normal; attribute vec4 a_color;
        varying vec3 v_normal; varying vec4 v_color; varying vec3 v_position;
        void main() { v_position=a_position.xyz; v_normal=normalize(u_normal*a_normal); v_color=a_color; gl_Position=u_mvp*a_position; }
    """),
    shaders.FragmentShader("""
        #ifdef GL_ES
        precision mediump float;
        #endif
        varying vec3 v_normal; varying vec4 v_color; varying vec3 v_position;
        uniform float u_section_plane[4];
        void main() {
            vec4 plane=vec4(u_section_plane[0],u_section_plane[1],u_section_plane[2],u_section_plane[3]);
            if (dot(vec4(v_position,1.0),plane) < -0.0001) discard;
            float light=0.42+0.58*abs(dot(normalize(v_normal), normalize(vec3(-0.3,0.5,1.0))));
            gl_FragColor=vec4(v_color.rgb*light, v_color.a);
        }
    """)], uniforms={'u_section_plane': NO_SECTION})


class SafeMeshData(gl.MeshData):
    def vertexNormals(self, indexed=None):
        if self._vertexNormals is None:
            faces = self.faces()
            normals = self.faceNormals()
            flat = faces.ravel()
            out = np.column_stack([np.bincount(flat, weights=np.repeat(normals[:, k], 3), minlength=len(self.vertexes())) for k in range(3)])
            lengths = np.linalg.norm(out, axis=1)
            out /= np.maximum(lengths[:, None], 1e-20)
            out[lengths < 1e-20] = [0, 0, 1]
            self._vertexNormals = out.astype(np.float32)
        return self._vertexNormals if indexed is None else self._vertexNormals[self.faces()]


class SectionMeshItem(gl.GLMeshItem):
    section_plane = NO_SECTION

    def paint(self):
        # ShaderProgram is shared, so load each item's plane for every draw.
        # Other windows and unclipped items must never inherit this view's cut.
        shader = self.shader()
        shader['u_section_plane'] = self.section_plane
        try:
            super().paint()
        finally:
            shader['u_section_plane'] = NO_SECTION


class ReferenceMeshItem(SectionMeshItem):
    def paint(self):
        from OpenGL import GL
        try:
            super().paint()
        finally:
            # Depth clears in the next frame must not inherit the reference's
            # disabled depth writes.
            GL.glDepthMask(True)


class Viewer(gl.GLViewWidget):
    moved = QtCore.Signal(object)
    protection_marked = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundColor("#0a1025")
        self.setMinimumSize(450, 400)
        self.items_by_name = {}
        self.section_plane = np.array(NO_SECTION)
        self._section_clouds = {}
        manager().views.append(weakref.ref(self))
        self.preview_head = None
        self.pose = np.eye(4)
        self.gasket = None
        self.result = None
        self.show_result = True
        self.head_visible = True
        self.fit_mode = "full_face"
        self.hmd_preview = None
        self.hmd_to_frame = None
        self.hmd_visible = True
        self.hmd_opacity = .18
        self.region_config = validate_regions()
        self.inspect_regions = False
        self.protection_brush = False
        self._pick_mesh = None
        self._pick_source = None
        self._painting_click = False
        self.grid = gl.GLGridItem(color=(75, 91, 145, 130))
        self.grid.setSize(400, 400)
        self.grid.setSpacing(20, 20)
        self.addItem(self.grid)
        self.opts["distance"] = 430
        self.setCameraPosition(elevation=12, azimuth=-65)
        self._drag_last = None
        self.allow_move = False

    def _put(self, name, vertices, faces, colors=None, color=None, *, face_colors=None, smooth=None):
        # CAD contact faces and magnet pockets need hard normals. Smoothing
        # across those edges produces apparent dents absent from the mesh.
        if smooth is None:
            smooth = name != "base"
        data = SafeMeshData(vertexes=vertices.astype(np.float32), faces=faces,
                            vertexColors=colors, faceColors=face_colors)
        if name in self.items_by_name:
            item = self.items_by_name[name]
            item.opts["smooth"] = smooth
            item.setMeshData(meshdata=data)
        else:
            item_class = ReferenceMeshItem if name == "hmd" else SectionMeshItem
            item = item_class(meshdata=data, color=color or (0.55, .67, .79, 1),
                                 smooth=smooth, drawEdges=False, shader=LIGHT, glOptions="opaque")
            self.addItem(item)
            self.items_by_name[name] = item
        item.section_plane = self.section_plane.copy()
        return item

    def set_section_plane(self, plane):
        """Clip only drawing, retaining original mesh data and visibility flags."""
        self.section_plane = np.asarray(plane, dtype=float).copy()
        for item in self.items_by_name.values():
            if isinstance(item, SectionMeshItem):
                item.section_plane = self.section_plane.copy()
        for name in self._section_clouds:
            self._refresh_section_cloud(name)
        self.update()

    def set_section_points(self, name, positions, colors):
        # Collision marks use a separate scatter shader. Filter their display
        # copy too, without altering the complete collision-check result.
        self._section_clouds[name] = (np.asarray(positions), np.asarray(colors))
        if name not in self.items_by_name:
            self.items_by_name[name] = gl.GLScatterPlotItem(size=5, pxMode=True)
            self.addItem(self.items_by_name[name])
        self._refresh_section_cloud(name)
        return self.items_by_name[name]

    def _refresh_section_cloud(self, name):
        points, colors = self._section_clouds[name]
        mask = section_mask(points, self.section_plane)
        self.items_by_name[name].setData(pos=points[mask], color=colors[mask])

    def set_head(self, vertices, faces):
        self.preview_head = (vertices, faces)
        item = self._put("head", vertices, faces, color=(.49, .58, .68, 1))
        item.setVisible(self.head_visible)

    def set_gasket(self, gasket, pose, result=None, show_result=True):
        self.gasket, self.pose, self.result, self.show_result = gasket, pose, result, show_result
        if gasket is None:
            return
        use_result = result is not None and show_result and not self.inspect_regions
        source = result.mesh if use_result else gasket
        frame = frame_vertices(source.vertices)
        vertices = transform(frame, pose)
        reference = result.reference_vertices if use_result and result.reference_vertices is not None else gasket.vertices
        base_frame = frame_vertices(reference)
        weight_function = full_weights if self.fit_mode == "full_face" else weights
        vertex_weights = weight_function(base_frame, self.region_config) if self.fit_mode == "full_face" else weight_function(base_frame)
        colors = np.tile([.19, .53, .77, 1.], (len(reference), 1)).astype(np.float32)
        colors[vertex_weights > 1e-6] = [.98, .64, .25, 1.]
        if result and show_result and not self.inspect_regions:
            change = result.displacement
            colors[change > .01] = [.29, .82, .62, 1.]
        if self.inspect_regions:
            feature = permanent_features(base_frame)
            colors[feature["headband"] | feature["nose_vents"]] = [.70, .43, .90, 1.]
        self._put("gasket", vertices, source.faces, colors=colors)
        self.redraw_hmd()

    def set_hmd(self, vertices, faces, docking):
        self.hmd_preview = (vertices, faces)
        self.hmd_to_frame = docking.copy()
        self.redraw_hmd()

    def redraw_hmd(self):
        if self.hmd_preview is None:
            return
        vertices, faces = self.hmd_preview
        world = transform(vertices, self.pose @ self.hmd_to_frame)
        item = self._put("hmd", world, faces, color=(.46, .75, .84, self.hmd_opacity))
        item.setColor((.46, .75, .84, self.hmd_opacity))
        # Render the transparent reference after opaque head/gasket geometry.
        from OpenGL import GL
        item.setGLOptions({GL.GL_DEPTH_TEST: True, GL.GL_BLEND: True,
                           "glBlendFunc": (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA),
                           "glDepthMask": (False,), GL.GL_CULL_FACE: False})
        item.setDepthValue(10)
        item.setVisible(self.hmd_visible)

    def set_hmd_visible(self, visible):
        self.hmd_visible = visible
        if "hmd" in self.items_by_name:
            self.items_by_name["hmd"].setVisible(visible)

    def set_hmd_opacity(self, value):
        self.hmd_opacity = value
        self.redraw_hmd()

    def fit_view(self):
        chunks = []
        if self.preview_head and self.head_visible:
            chunks.append(self.preview_head[0])
        if self.gasket:
            source = self.result.mesh if self.result and self.show_result and not self.inspect_regions else self.gasket
            chunks.append(transform(frame_vertices(source.vertices), self.pose))
        if self.hmd_preview and self.hmd_visible:
            chunks.append(transform(self.hmd_preview[0], self.pose @ self.hmd_to_frame))
        if chunks:
            lo = np.min([x.min(0) for x in chunks], axis=0)
            hi = np.max([x.max(0) for x in chunks], axis=0)
            self.opts["center"] = QtGui.QVector3D(*((lo + hi) / 2))
            horizontal = np.deg2rad(float(self.opts["fov"]) / 2)
            vertical = np.arctan(np.tan(horizontal) * self.height() / max(1, self.width()))
            radius = max(1., float(np.linalg.norm(hi - lo)) / 2)
            self.opts["distance"] = radius / np.sin(min(horizontal, vertical)) * 1.08
            self.grid.resetTransform()
            self.grid.translate(float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2), float(lo[2] - 2))
            self.update()

    def view(self, name):
        choices = {"front": (-90, 0), "back": (90, 0), "right": (0, 0), "left": (180, 0), "top": (-90, 90), "3d": (-65, 15)}
        azimuth, elevation = choices[name]
        # Canonical views must also reset roll after six-axis navigation.
        manager().reset_motion()
        self.opts['rotationMethod'] = 'euler'
        self.opts.pop('rotation', None)
        self.setCameraPosition(azimuth=azimuth, elevation=elevation)

    def set_head_visible(self, value):
        self.head_visible = value
        if "head" in self.items_by_name:
            self.items_by_name["head"].setVisible(value)

    def mousePressEvent(self, event):
        if self.protection_brush and event.button() == QtCore.Qt.MouseButton.LeftButton and event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            self._painting_click = True
            self.mark_protection(event.position())
            event.accept()
        elif self.allow_move and event.button() == QtCore.Qt.MouseButton.LeftButton and event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
            self._drag_last = event.position()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mark_protection(self, position):
        if self.gasket is None:
            return
        import trimesh
        viewport = (0, 0, self.width(), self.height())
        inverse, ok = (self.projectionMatrix(viewport, viewport) * self.viewMatrix()).inverted()
        if not ok:
            return
        points = []
        for depth in (-1., 1.):
            q = inverse.map(QtGui.QVector3D(2 * position.x() / self.width() - 1,
                                           1 - 2 * position.y() / self.height(), depth))
            points.append(np.array([q.x(), q.y(), q.z()]))
        origin = (points[0] - self.pose[:3, 3]) @ self.pose[:3, :3]
        direction = (points[1] - points[0]) @ self.pose[:3, :3]
        direction /= np.linalg.norm(direction)
        if self._pick_source is not self.gasket:
            self._pick_source = self.gasket
            self._pick_mesh = trimesh.Trimesh(frame_vertices(self.gasket.vertices), self.gasket.faces, process=False)
        hits, _, _ = self._pick_mesh.ray.intersects_location([origin], [direction], multiple_hits=False)
        if len(hits):
            self.protection_marked.emit(hits[0])

    def mouseMoveEvent(self, event):
        if self._painting_click:
            event.accept()
        elif self._drag_last is not None:
            delta = event.position() - self._drag_last
            self._drag_last = event.position()
            az, el = np.deg2rad([self.opts["azimuth"], self.opts["elevation"]])
            right = np.array([-np.sin(az), np.cos(az), 0.])
            up = np.array([-np.cos(az) * np.sin(el), -np.sin(az) * np.sin(el), np.cos(el)])
            if self.opts['rotationMethod'] == 'quaternion':
                inverse = self.opts['rotation'].conjugated()
                r = inverse.rotatedVector(QtGui.QVector3D(1,0,0))
                u = inverse.rotatedVector(QtGui.QVector3D(0,1,0))
                right = np.array([r.x(),r.y(),r.z()])
                up = np.array([u.x(),u.y(),u.z()])
            scale = self.opts["distance"] * 1.15 / max(self.width(), 1)
            self.moved.emit((right * delta.x() - up * delta.y()) * scale)
            event.accept()
        else:
            position = event.position()
            previous = getattr(self, 'mousePos', position)
            delta = position - previous
            self.mousePos = position
            p = controls()
            buttons = {'left': QtCore.Qt.MouseButton.LeftButton,
                       'middle': QtCore.Qt.MouseButton.MiddleButton,
                       'right': QtCore.Qt.MouseButton.RightButton}
            pressed = event.buttons()
            if pressed == buttons[p['pan_button']] or (pressed == buttons[p['rotate_button']] and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
                self.pan(delta.x(), delta.y(), 0, relative='view')
            elif pressed == buttons[p['rotate_button']]:
                self.orbit(-delta.x(), delta.y())
            # Retain middle-button panning when right-button panning is chosen.
            elif pressed == QtCore.Qt.MouseButton.MiddleButton and p['rotate_button'] != 'middle':
                self.pan(delta.x(), delta.y(), 0, relative='view')
            event.accept()

    def wheelEvent(self, event):
        p = controls()
        if p['space_enabled'] and time.monotonic()-manager().last_motion < .15:
            event.accept()
            return
        delta = event.angleDelta().y() or event.angleDelta().x()
        if p['invert_wheel']:
            delta = -delta
        self.opts['distance'] = float(np.clip(self.opts['distance'] * np.exp(-.001*delta), 1, 100000))
        self.update()
        event.accept()

    def space_motion(self, axes, settings=None):
        """Six-axis camera navigation only; never emit model movement signals."""
        p = settings or controls()
        values = np.clip(np.asarray(axes,dtype=float)/350., -2, 2)
        if p['space_pan']:
            tx,ty,tz = values[:3]*p['space_translation_gain']
            self.pan(float(tx*8),float(-tz*8),0,relative='view')
            self.opts['distance'] = float(np.clip(self.opts['distance']*np.exp(-ty*.02),1,100000))
        if p['space_rotate'] and np.any(values[3:]):
            if self.opts['rotationMethod'] != 'quaternion':
                self.opts['rotation'] = (QtGui.QQuaternion.fromAxisAndAngle(1,0,0,self.opts['elevation']-90)
                                         * QtGui.QQuaternion.fromAxisAndAngle(0,0,1,-self.opts['azimuth']-90))
                self.opts['rotationMethod'] = 'quaternion'
            rx,ry,rz = values[3:]*p['space_rotation_gain']*2
            q = QtGui.QQuaternion.fromEulerAngles(float(-rx),float(rz),float(-ry))
            self.opts['rotation'] = (q*self.opts['rotation']).normalized()
        self.update()

    def mouseReleaseEvent(self, event):
        self._painting_click = False
        self._drag_last = None
        super().mouseReleaseEvent(event)
